import os, sys, re, json, ssl, zipfile, platform, subprocess, webbrowser
import urllib.request, urllib.error
import bot

REPO = "c4vi4z/pastastrainer"
FROZEN = getattr(sys, "frozen", False)

try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    ctx = ssl.create_default_context()


def num(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "memorybot", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def describe(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return "github 404: repo naam fout, repo is prive, of er is nog geen release"
        if e.code == 403:
            return "github 403: te veel checks, probeer later"
        return "github fout " + str(e.code)
    if isinstance(e, urllib.error.URLError):
        return "geen internet of certificaat probleem: " + str(e.reason)
    return type(e).__name__ + ": " + str(e)

def latest_release():
    rel = get_json("https://api.github.com/repos/" + REPO + "/releases/latest")
    if num(rel.get("tag_name", "")) > num(bot.APP_VERSION):
        return rel
    return None


def fetch(url, dest, log=None):
    req = urllib.request.Request(url, headers={"User-Agent": "memorybot"})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        mark = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if log and total:
                pct = done * 100 // total
                if pct >= mark + 25:
                    mark = pct - pct % 25
                    log("  " + str(pct) + "%")


def find_asset(rel, name):
    for a in rel.get("assets", []):
        if a.get("name") == name:
            return a
    return None


def installer_name():
    s = platform.system()
    if s == "Windows":
        return "MemoryBot-Setup.exe"
    if s == "Darwin":
        return "MemoryBot-" + platform.machine() + ".dmg"
    return None


def apply_update(rel, log):
    zasset = find_asset(rel, "code.zip")
    if zasset is not None:
        tmp = os.path.join(bot.PARENT, "update.zip")
        log("update downloaden...")
        fetch(zasset["browser_download_url"], tmp, log)
        try:
            with zipfile.ZipFile(tmp) as zf:
                names = zf.namelist()
                meta = {}
                if "meta.json" in names:
                    meta = json.loads(zf.read("meta.json").decode("utf-8"))
                if int(meta.get("installer_version", 1)) <= bot.INSTALLER_API:
                    files = ["app.py", "bot.py", "updater.py"]
                    for n in files:
                        if n not in names:
                            raise RuntimeError(n + " ontbreekt in de update")
                        compile(zf.read(n), n, "exec")
                    if FROZEN:
                        target = os.path.join(bot.PARENT, "code")
                    else:
                        target = bot.BASE
                    os.makedirs(target, exist_ok=True)
                    for n in files:
                        with open(os.path.join(target, n + ".new"), "wb") as f:
                            f.write(zf.read(n))
                    for n in files:
                        os.replace(os.path.join(target, n + ".new"), os.path.join(target, n))
                    log("update klaar")
                    return "restart"
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    name = installer_name()
    asset = None
    if name:
        asset = find_asset(rel, name)
    if asset is not None and FROZEN:
        folder = os.path.join(bot.PARENT, "downloads")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        log("installer downloaden (" + name + ")...")
        fetch(asset["browser_download_url"], path, log)
        if platform.system() == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["open", path])
        return "installer"

    webbrowser.open(rel.get("html_url", "https://github.com/" + REPO + "/releases"))
    return "page"
