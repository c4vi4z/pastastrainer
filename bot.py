import os, sys, re, time, stat, platform, zipfile, shutil, ssl, subprocess, random, threading, traceback
import urllib.request, urllib.error
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

try:
    import certifi
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    ssl_ctx = ssl.create_default_context()

FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    RES = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if sys.platform.startswith("win"):
        PARENT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MemoryBot")
    elif sys.platform == "darwin":
        PARENT = os.path.expanduser("~/Library/Application Support/MemoryBot")
    else:
        PARENT = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "memorybot")
    BASE = os.path.join(PARENT, "app")
else:
    RES = os.path.dirname(os.path.abspath(__file__))
    BASE = RES
    PARENT = os.path.dirname(BASE)
LISTS_DIR = os.path.join(BASE, "lists")
PROFILE = os.path.join(PARENT, "chrome-profile")
LOG_PATH = os.path.join(PARENT, "memorybot.log")
os.makedirs(LISTS_DIR, exist_ok=True)

SKIP = "-- sla kaart over --"
APP_VERSION = "1.0.7"
INSTALLER_API = 99

DELAY_MIN = 1
DELAY_MAX = 10
KNOW_DELAY = 0.2
WRONG_MIN = 1
WRONG_MAX = 10


def seed_lists():
    src = os.path.join(RES, "lists")
    if src == LISTS_DIR or not os.path.isdir(src):
        return
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = os.path.join(LISTS_DIR, rel)
        os.makedirs(out, exist_ok=True)
        for f in files:
            dst = os.path.join(out, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(root, f), dst)


seed_lists()

VERSION = "153.0.8010.52"
DL_URL = "https://storage.googleapis.com/chrome-for-testing-public/{v}/{p}/{name}-{p}.zip"

log = print
ask_open = None
ask_mc = None
stop = None
driver = None
all_words = {}

SYSTEM_BROWSER = False
system = platform.system()
machine = platform.machine().lower()
arm = machine in ("arm64", "aarch64")
if system == "Linux":
    if arm or machine.startswith("arm"):
        SYSTEM_BROWSER = True
        PLAT = "linux-arm"
    else:
        PLAT = "linux64"
elif system == "Darwin":
    PLAT = "mac-arm64" if arm else "mac-x64"
elif system == "Windows":
    PLAT = "win64" if sys.maxsize > 2**32 else "win32"
else:
    raise RuntimeError("niet ondersteund os: " + system)

IS_WIN = PLAT.startswith("win")
NOWIN = subprocess.CREATE_NO_WINDOW if IS_WIN else 0

if PLAT.startswith("mac"):
    CHROME_REL = os.path.join("Google Chrome for Testing.app", "Contents", "MacOS", "Google Chrome for Testing")
elif IS_WIN:
    CHROME_REL = "chrome.exe"
else:
    CHROME_REL = "chrome"

CHROME_DIR = os.path.join(PARENT, "chrome-" + PLAT)
DRIVER_DIR = os.path.join(PARENT, "chromedriver-" + PLAT)
CHROME_BIN = os.path.join(CHROME_DIR, CHROME_REL)
DRIVER_BIN = os.path.join(DRIVER_DIR, "chromedriver.exe" if IS_WIN else "chromedriver")


class Stopped(Exception):
    pass


def file_log(text):
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1000000:
            old = LOG_PATH + ".old"
            if os.path.exists(old):
                os.remove(old)
            os.replace(LOG_PATH, old)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(text) + "\n")
    except Exception:
        pass


dbg = file_log


def tail_file(path, n):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def hook_threads():
    def hook(args):
        file_log("thread fout: " + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = hook


def debug_info():
    try:
        file_log("==== sessie start ====")
        file_log("versie " + APP_VERSION + ", installer api " + str(INSTALLER_API))
        file_log("os " + platform.platform() + ", machine " + platform.machine())
        if system == "Darwin":
            file_log("macos " + platform.mac_ver()[0])
        file_log("python " + sys.version.split()[0] + ", frozen " + str(FROZEN))
        file_log("plat " + PLAT + ", systeem browser " + str(SYSTEM_BROWSER))
        file_log("BASE " + BASE)
        file_log("PARENT " + PARENT)
        file_log("chrome " + CHROME_BIN + " bestaat " + str(os.path.exists(CHROME_BIN)))
        file_log("driver " + DRIVER_BIN + " bestaat " + str(os.path.exists(DRIVER_BIN)))
        file_log("profiel " + PROFILE + " bestaat " + str(os.path.isdir(PROFILE)))
        file_log("lijsten " + str(len(find_lists())))
        file_log("wachttijd " + str(DELAY_MIN) + "-" + str(DELAY_MAX) + "s, ik ken het " + str(KNOW_DELAY) + "s, fout per kaart " + str(WRONG_MIN) + "-" + str(WRONG_MAX))
    except Exception as e:
        file_log("debug info mislukt: " + type(e).__name__)


def log_versions():
    for path in (CHROME_BIN, DRIVER_BIN):
        if IS_WIN and path == CHROME_BIN:
            continue
        name = os.path.basename(path)
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL, creationflags=NOWIN)
            file_log("versie " + name + ": " + (out.stdout.strip() or out.stderr.strip()))
        except subprocess.TimeoutExpired:
            file_log("versie " + name + ": timeout na 15s")
        except Exception as e:
            file_log("versie " + name + " fout: " + type(e).__name__ + " " + str(e))
    if not IS_WIN:
        try:
            out = subprocess.run(["file", CHROME_BIN], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
            file_log("file: " + out.stdout.strip())
        except Exception:
            pass


def check():
    if stop.is_set():
        raise Stopped()


def pause(secs):
    end = time.time() + secs
    while time.time() < end:
        check()
        time.sleep(0.1)


def word_delay():
    lo = min(DELAY_MIN, DELAY_MAX)
    hi = max(DELAY_MIN, DELAY_MAX)
    pause(random.uniform(lo, hi))


def extract_zip(zip_path, dest):
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = os.path.join(dest, info.filename)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                if os.path.lexists(target):
                    os.remove(target)
                os.symlink(zf.read(info).decode(), target)
                continue
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            if mode:
                os.chmod(target, stat.S_IMODE(mode) | stat.S_IRUSR | stat.S_IWUSR)


def download(name, check_path):
    if os.path.exists(check_path):
        return
    url = DL_URL.format(v=VERSION, p=PLAT, name=name)
    zip_path = os.path.join(PARENT, name + "-" + PLAT + ".zip")
    log(name + " downloaden (eenmalig)...")

    try:
        resp = urllib.request.urlopen(url, context=ssl_ctx, timeout=60)
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            "download mislukt (" + str(e.code) + "). versie " + VERSION + " bestaat misschien niet meer. "
            "zoek een nieuwe op https://googlechromelabs.github.io/chrome-for-testing/"
            "known-good-versions-with-downloads.json en pas VERSION aan in bot.py"
        )
    except urllib.error.URLError as e:
        raise RuntimeError("geen verbinding of certificaat probleem: " + str(e.reason))

    total = int(resp.headers.get("Content-Length") or 0)
    done = 0
    mark = 0
    with open(zip_path, "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total > 0:
                pct = done * 100 // total
                if pct >= mark + 20:
                    mark = pct - pct % 20
                    log("  " + str(pct) + "%")
    resp.close()

    log(name + " uitpakken...")
    extract_zip(zip_path, PARENT)
    os.remove(zip_path)


def find_system_browser():
    browser = None
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        p = shutil.which(name)
        if p:
            browser = p
            break
    drv = None
    for name in ("chromedriver", "chromium-chromedriver"):
        p = shutil.which(name)
        if p:
            drv = p
            break
    if drv is None:
        for p in ("/usr/lib/chromium/chromedriver", "/usr/lib/chromium-browser/chromedriver", "/usr/lib64/chromium/chromedriver"):
            if os.path.exists(p):
                drv = p
                break
    return browser, drv


def ensure_browser():
    global CHROME_BIN, DRIVER_BIN
    if SYSTEM_BROWSER:
        browser, drv = find_system_browser()
        if not browser or not drv:
            raise RuntimeError(
                "chromium of chromedriver ontbreekt. installeer met: sudo apt install chromium chromium-driver "
                "(of: sudo apt install chromium-browser chromium-chromedriver)"
            )
        CHROME_BIN = browser
        DRIVER_BIN = drv
        return
    download("chrome", CHROME_BIN)
    download("chromedriver", DRIVER_BIN)
    if not IS_WIN:
        os.chmod(CHROME_BIN, 0o755)
        os.chmod(DRIVER_BIN, 0o755)
        helper = os.path.join(CHROME_DIR, "chrome_crashpad_handler")
        if os.path.exists(helper):
            os.chmod(helper, 0o755)


def norm(s):
    return " ".join(s.strip().lower().split())


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def load_list(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                cue, ans = line.rsplit("=", 1)
                out[norm(cue)] = ans.strip()
    return out


def find_lists():
    found = []
    for root, dirs, files in os.walk(LISTS_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.endswith(".txt"):
                rel = os.path.relpath(os.path.join(root, f), LISTS_DIR)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found, key=natural)


def build_steps(names, start=1):
    steps = []
    for k in range(len(names)):
        name = names[k]
        card = start - 1 + k
        if name == SKIP:
            log("  kaart " + str(card + 1) + ": overgeslagen")
            continue
        words = load_list(os.path.join(LISTS_DIR, *name.split("/")))
        label = os.path.splitext(os.path.basename(name))[0]
        steps.append({"label": label, "card": card, "files": [name], "words": words})
        log("  kaart " + str(card + 1) + ": " + name + " (" + str(len(words)) + " woorden)")
    return steps


def variants(s):
    s = norm(s)
    strip = lambda x: norm(re.sub(r"\([^)]*\)", "", x))
    out = {s, strip(s)}
    for part in re.split(r"[;,]", s):
        p = norm(part)
        out.add(p)
        out.add(strip(p))
    out.discard("")
    return out


def correct_targets(cue, d):
    targets = set()
    for k, v in d.items():
        if cue in variants(k):
            targets |= variants(v)
        if cue in variants(v):
            targets |= variants(k)
    targets.discard(cue)
    return targets


def full_targets(cue, d):
    out = set()
    for k, v in d.items():
        if cue in variants(k):
            out.add(norm(v))
        if cue in variants(v):
            out.add(norm(k))
    out.discard(cue)
    return out


def lookup(cue, dicts):
    for d in dicts:
        if cue in d:
            return d[cue]
    return None


CUE = (By.CSS_SELECTOR, "h2#cue-text")
ANSWER = (By.CSS_SELECTOR, ".answer-section input, .answer-section textarea")
KNOW_BTN = (By.CSS_SELECTOR, "ion-button[data-test='register-study-trial']")
NEXT_BTN = (By.CSS_SELECTOR, "ion-button[data-test='next-button']")
MC_BTN = (By.CSS_SELECTOR, "ion-button[data-test^='multiple-choice-answer-']")
MC_TEXT = (By.CSS_SELECTOR, "[data-test='mc-answer-text']")
STOP_BTN = (By.CSS_SELECTOR, "ion-button[data-test='return-to-lesson']")
BACK_BTN = (By.CSS_SELECTOR, "ion-back-button")
LESSON_CARD = (By.CSS_SELECTOR, "app-lesson-card")
CARD_INNER = (By.CSS_SELECTOR, "ion-card[data-test='lesson-card']")
START_BTN = (By.CSS_SELECTOR, "app-split-button[data-test='start-button'] ion-button.main-button")


def alive():
    if driver is None:
        return False
    try:
        driver.title
        return True
    except Exception:
        return False


def clean_locks():
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        p = os.path.join(PROFILE, name)
        try:
            if os.path.lexists(p):
                os.remove(p)
        except OSError:
            pass


def kill_old_chrome():
    try:
        if IS_WIN:
            ps = (
                "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
                "Where-Object { $_.ExecutablePath -like '" + CHROME_DIR + "*' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=NOWIN, timeout=20,
            )
        else:
            subprocess.run(["pkill", "-f", PROFILE], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception as e:
        file_log("oude chrome opruimen mislukt: " + type(e).__name__)


def open_browser(url):
    global driver
    if not alive():
        ensure_browser()
        file_log("browser start, chrome " + CHROME_BIN)
        log_versions()
        opts = Options()
        opts.binary_location = CHROME_BIN
        opts.add_argument("--user-data-dir=" + PROFILE)
        opts.add_argument("--lang=nl")
        opts.add_argument("--force-device-scale-factor=1")
        opts.add_argument("--start-maximized")
        if SYSTEM_BROWSER:
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
        opts.add_experimental_option("prefs", {"intl.accept_languages": "nl,nl-NL,en"})
        last_err = None
        for attempt in range(2):
            file_log("poging " + str(attempt + 1))
            kill_old_chrome()
            clean_locks()
            time.sleep(1)
            service = Service(DRIVER_BIN, log_output=os.path.join(BASE, "chromedriver.log"))
            try:
                driver = webdriver.Chrome(service=service, options=opts)
                last_err = None
                break
            except Exception as e:
                driver = None
                last_err = e
                file_log("chrome start fout: " + type(e).__name__ + " " + str(e)[:600])
                for line in tail_file(os.path.join(BASE, "chromedriver.log"), 25):
                    file_log("  chromedriver.log: " + line.rstrip())
                log("chrome start mislukt, opnieuw proberen...")
        if last_err is not None:
            raise RuntimeError(
                "chrome starten mislukt. details in memorybot.log (" + type(last_err).__name__ + ")"
            )
        try:
            driver.maximize_window()
        except Exception:
            pass
        file_log("browser open")
    driver.get(url)


def close():
    global driver
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None


def click(el):
    try:
        el.click()
    except StaleElementReferenceException:
        raise
    except Exception:
        driver.execute_script("arguments[0].click();", el)


def first_visible(locator):
    for el in driver.find_elements(*locator):
        try:
            if el.is_displayed():
                return el
        except Exception:
            continue
    return None


def know_button():
    for b in driver.find_elements(*KNOW_BTN):
        if b.is_displayed() and "ik ken het" in b.text.lower():
            return b
    return None


def next_button():
    for b in driver.find_elements(*NEXT_BTN):
        try:
            if not b.is_displayed():
                continue
            if b.get_attribute("disabled") is not None:
                continue
            if "button-disabled" in (b.get_attribute("class") or ""):
                continue
            return b
        except StaleElementReferenceException:
            continue
    return None


def stop_button():
    return first_visible(STOP_BTN)


def get_cue():
    return driver.find_element(*CUE).text


def in_exercise():
    return bool(know_button()) or first_visible(CUE) is not None


def mc_options():
    out = []
    for b in driver.find_elements(*MC_BTN):
        try:
            if not b.is_displayed():
                continue
            inner = b.find_elements(*MC_TEXT)
            src = inner[0] if inner else b
            text = src.text.strip() or (src.get_attribute("textContent") or "").strip()
            out.append((b, text))
        except StaleElementReferenceException:
            continue
    return out


def pick_option(cue, options, dicts):
    for d in dicts:
        full = full_targets(cue, d)
        for i in range(len(options)):
            if norm(options[i][1]) in full:
                return i
    for d in dicts:
        targets = correct_targets(cue, d)
        best = None
        best_score = 0
        for i in range(len(options)):
            score = len(variants(options[i][1]) & targets)
            if score > best_score:
                best = i
                best_score = score
        if best is not None:
            return best
    return None


def visible_cards():
    out = []
    for loc in (LESSON_CARD, CARD_INNER):
        for card in driver.find_elements(*loc):
            try:
                if card.is_displayed():
                    out.append(card)
            except StaleElementReferenceException:
                continue
        if out:
            break
    return out


def card_title(card):
    try:
        t = card.find_element(By.CSS_SELECTOR, "h2").get_attribute("textContent").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        return " ".join((card.get_attribute("textContent") or "").split())[:40] or "?"
    except Exception:
        return "?"


def get_card(index, timeout=60):
    end = time.time() + timeout
    stuck = 0
    count = -1
    while time.time() < end:
        check()
        cards = visible_cards()
        if len(cards) > index:
            return cards[index], len(cards)
        if len(cards) == count:
            stuck += 1
            if stuck >= 12:
                break
        else:
            stuck = 0
        count = len(cards)
        if cards:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'end'});", cards[-1])
            except Exception:
                pass
        pause(0.7)
    return None, len(visible_cards())


def back_to_cards(timeout=40):
    start = time.time()
    end = start + timeout
    while time.time() < end:
        check()
        if visible_cards():
            return True
        if time.time() - start < 8:
            pause(0.5)
            continue
        back = first_visible(BACK_BTN)
        if back:
            click(back)
            log("terug")
            pause(2.5)
        else:
            pause(0.5)
    return False


def wait_for_exercise(timeout=25):
    end = time.time() + timeout
    last_start = 0
    while time.time() < end:
        check()
        if in_exercise():
            return True
        start = first_visible(START_BTN)
        if start and time.time() - last_start > 5:
            click(start)
            log("start")
            last_start = time.time()
            pause(1)
            continue
        pause(0.5)
    return False


def dump_debug(why):
    try:
        log("debug: " + why)
        log("  url: " + driver.current_url)
        log("  titel: " + driver.title)
        size = driver.get_window_size()
        log("  venster: " + str(size["width"]) + "x" + str(size["height"]))
        log("  taal: " + str(driver.execute_script("return navigator.language")))
        log("  app-lesson-card in pagina: " + str(len(driver.find_elements(*LESSON_CARD))))
        log("  ion-card lesson-card in pagina: " + str(len(driver.find_elements(*CARD_INNER))))
        log("  zichtbaar: " + str(len(visible_cards())))
        driver.save_screenshot(os.path.join(BASE, "debug.png"))
        with open(os.path.join(BASE, "debug.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log("  debug.png en debug.html staan in " + BASE)
    except Exception as e:
        log("debug mislukt: " + type(e).__name__)


def enter_lesson(step, first):
    if first and in_exercise():
        dbg("al in een oefening, kaart openen overgeslagen")
        return True
    if not back_to_cards():
        log("geen kaarten gevonden. ga in chrome naar de pagina met de lessenkaarten (open eerst een unit) en klik Start opnieuw")
        dump_debug("geen kaarten na terug klikken")
        return False

    card, total = get_card(step["card"])
    if card is None:
        log("kaart " + str(step["card"] + 1) + " bestaat niet (" + str(total) + " zichtbaar), stop")
        dump_debug("kaart " + str(step["card"] + 1) + " niet gevonden")
        return False

    log("open kaart " + str(step["card"] + 1) + " van " + str(total) + ": " + card_title(card))
    try:
        target = card.find_element(*CARD_INNER)
    except NoSuchElementException:
        target = card
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
    click(target)
    pause(1)
    ok = wait_for_exercise()
    dbg("oefening gestart: " + str(ok))
    return ok


def advance(cue):
    end = time.time() + 4
    while time.time() < end:
        nb = next_button()
        if nb:
            click(nb)
            log("volgende")
            break
        pause(0.3)
    for t in range(10):
        pause(0.3)
        try:
            if norm(get_cue()) != cue:
                return
        except Exception:
            return


def pick_wrong_count():
    lo = int(min(WRONG_MIN, WRONG_MAX))
    hi = int(max(WRONG_MIN, WRONG_MAX))
    if hi <= 0:
        return 0
    return random.randint(max(lo, 0), hi)


def wrong_answers(count, dicts):
    done = 0
    tries = 0
    while done < count and tries < count * 4 + 8:
        tries += 1
        check()
        try:
            if stop_button():
                return
            kb = know_button()
            if kb:
                click(kb)
                log("ik ken het")
                pause(KNOW_DELAY)
                continue
            try:
                cue = norm(get_cue())
            except StaleElementReferenceException:
                raise
            except Exception:
                cue = ""
            if not cue:
                pause(0.5)
                continue
            options = mc_options()
            if options:
                good = pick_option(cue, options, dicts)
                choices = [i for i in range(len(options)) if i != good]
                if not choices:
                    return
                idx = random.choice(choices)
                click(options[idx][0])
                log(cue + " -> " + options[idx][1] + " (bewust fout, mc)")
            else:
                box = driver.find_element(*ANSWER)
                box.click()
                box.send_keys(Keys.ENTER)
                pause(1)
                if not next_button():
                    try:
                        same = norm(get_cue()) == cue
                    except Exception:
                        same = False
                    if same:
                        dbg("enter zonder tekst deed niks, x typen")
                        box.send_keys("x")
                        box.send_keys(Keys.ENTER)
                log(cue + " (bewust fout)")
            done += 1
            word_delay()
            advance(cue)
        except (StaleElementReferenceException, NoSuchElementException):
            nb = next_button()
            if nb:
                click(nb)
                done += 1
            pause(0.3)
            continue
    dbg("bewust fout klaar: " + str(done) + " van " + str(count))


def run_lesson(step):
    dicts = [step["words"], all_words]
    wait = WebDriverWait(driver, 15)
    last = None
    idle = 0

    n = pick_wrong_count()
    dbg("kaart " + step["label"] + ": " + str(n) + " keer bewust fout")
    if n > 0:
        wrong_answers(n, dicts)

    while idle < 30:
        check()
        try:
            sb = stop_button()
            if sb:
                log("stop met oefenen: " + sb.text.strip())
                click(sb)
                pause(1)
                return "finished"

            btn = know_button()
            if btn:
                click(btn)
                log("ik ken het")
                last = None
                idle = 0
                pause(KNOW_DELAY)
                continue

            try:
                cue = norm(get_cue())
            except StaleElementReferenceException:
                raise
            except Exception:
                cue = ""

            if cue and cue != last:
                options = mc_options()
                if options:
                    idx = pick_option(cue, options, dicts)
                    if idx is None:
                        dbg("geen match voor '" + cue + "', opties: " + " | ".join(o[1] for o in options))
                        idx = ask_mc(cue, [o[1] for o in options])
                        if idx is None:
                            return "quit"
                        if idx < 0:
                            last = cue
                            idle = -40
                            continue
                    click(options[idx][0])
                    log(cue + " -> " + options[idx][1] + " (mc)")
                    last = cue
                    idle = 0
                    word_delay()
                    continue

                answer = lookup(cue, dicts)
                if answer is None:
                    dbg("'" + cue + "' niet in lijst")
                    answer = ask_open(cue)
                    if answer is None:
                        return "quit"
                    if answer == "":
                        last = cue
                        idle = -40
                        continue
                box = wait.until(lambda d: d.find_element(*ANSWER))
                box.click()
                box.clear()
                box.send_keys(answer)
                box.send_keys(Keys.ENTER)
                log(cue + " = " + answer)
                last = cue
                idle = 0
                word_delay()
                continue

            if cue and cue == last:
                nb = next_button()
                if nb:
                    click(nb)
                    log("volgende")
                    idle = 0
                    for t in range(10):
                        pause(0.3)
                        try:
                            if norm(get_cue()) != cue:
                                break
                        except Exception:
                            break
                    continue
        except StaleElementReferenceException:
            pause(0.3)
            continue

        idle += 1
        if idle % 10 == 0:
            dbg("niks te doen, idle " + str(idle) + ", cue '" + str(last) + "'")
        pause(0.5)
    return "idle"


def dbg_page():
    try:
        dbg("url " + driver.current_url)
        dbg("titel " + driver.title)
        size = driver.get_window_size()
        dbg("venster " + str(size["width"]) + "x" + str(size["height"]) + ", taal " + str(driver.execute_script("return navigator.language")))
        dbg("kaarten zichtbaar " + str(len(visible_cards())))
    except Exception as e:
        dbg("pagina info mislukt: " + type(e).__name__)


def run(steps):
    global all_words
    if not alive():
        raise RuntimeError("browser is niet open")
    all_words = {}
    for s in steps:
        for k, v in s["words"].items():
            all_words.setdefault(k, v)
    dbg("run start, " + str(len(steps)) + " kaarten, " + str(len(all_words)) + " woorden")
    dbg_page()
    try:
        for n in range(len(steps)):
            step = steps[n]
            log("=== " + step["label"] + " (" + str(n + 1) + "/" + str(len(steps)) + ") ===")
            if not enter_lesson(step, n == 0):
                log("kaart openen mislukt, stop")
                return "error"
            result = run_lesson(step)
            dbg("resultaat " + step["label"] + ": " + result)
            if result == "finished":
                log(step["label"] + " klaar")
                continue
            if result == "idle":
                log("niks meer gezien, stop")
                dbg_page()
            else:
                log("gestopt")
            return result
        log("alle lijsten klaar")
        return "done"
    except Stopped:
        log("gestopt")
        return "stopped"
