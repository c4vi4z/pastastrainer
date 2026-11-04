#!/usr/bin/env bash
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
  DEST="$HOME/Library/Application Support/MemoryBot"
  if [ -w "/Applications" ]; then
    APP="/Applications/Memory Bot.app"
  else
    mkdir -p "$HOME/Applications"
    APP="$HOME/Applications/Memory Bot.app"
  fi
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/memorybot"
  DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/memorybot.desktop"
fi

if [ "$1" = "--uninstall" ]; then
  rm -rf "$DEST"
  if [ "$OS" = "Darwin" ]; then rm -rf "/Applications/Memory Bot.app" "$HOME/Applications/Memory Bot.app"; else rm -f "$DESKTOP_FILE"; fi
  echo "verwijderd (inclusief je lijsten en login)."
  exit 0
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3 niet gevonden."
  if [ "$OS" = "Darwin" ]; then
    echo "installeer python van https://www.python.org/downloads/macos/ en start dit opnieuw."
  else
    echo "installeer python3 met je pakketbeheerder en start dit opnieuw."
  fi
  exit 1
fi

if ! TKV="$("$PY" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null)"; then
  echo "tkinter ontbreekt."
  if [ "$OS" = "Darwin" ]; then
    echo "installeer python van https://www.python.org/downloads/macos/ (of: brew install python-tk) en start dit opnieuw."
    exit 1
  fi
  CMD=""
  if command -v apt >/dev/null 2>&1; then CMD="sudo apt install -y python3-tk python3-venv"
  elif command -v dnf >/dev/null 2>&1; then CMD="sudo dnf install -y python3-tkinter"
  elif command -v pacman >/dev/null 2>&1; then CMD="sudo pacman -S --noconfirm tk"
  elif command -v zypper >/dev/null 2>&1; then CMD="sudo zypper install -y python3-tk"
  fi
  if [ -z "$CMD" ]; then echo "installeer het tkinter pakket van je distro en start opnieuw."; exit 1; fi
  echo "commando: $CMD"
  read -r -p "nu uitvoeren? (j/n) " A
  [ "$A" = "j" ] || exit 1
  $CMD
  exec bash "$0" "$@"
fi

if [ "$OS" = "Linux" ]; then
  case "$(uname -m)" in
    aarch64|arm*)
      if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
        echo "arm: chrome for testing bestaat niet voor arm, ik gebruik chromium van je systeem."
        if command -v apt >/dev/null 2>&1; then
          echo "commando: sudo apt install -y chromium chromium-driver"
          read -r -p "nu uitvoeren? (j/n) " A
          if [ "$A" = "j" ]; then
            sudo apt install -y chromium chromium-driver || sudo apt install -y chromium-browser chromium-chromedriver
          fi
        else
          echo "installeer chromium en chromedriver met je pakketbeheerder en start dit opnieuw."
          exit 1
        fi
      fi
      ;;
  esac
fi

if [ "$OS" = "Darwin" ] && ! awk "BEGIN{exit !($TKV >= 8.6)}"; then
  echo "je python heeft een te oude Tk ($TKV). installeer python van https://www.python.org/downloads/macos/"
  exit 1
fi

mkdir -p "$DEST/app/lists"
cp "$SRC/app.py" "$SRC/bot.py" "$SRC/updater.py" "$DEST/app/"
[ -f "$SRC/icon.png" ] && cp "$SRC/icon.png" "$DEST/app/icon.png"
[ -d "$SRC/lists" ] && cp -rn "$SRC/lists/." "$DEST/app/lists/" 2>/dev/null || true

VPY="$DEST/.venv-memory/bin/python"
if [ ! -x "$VPY" ]; then
  "$PY" -m venv "$DEST/.venv-memory" || { echo "venv maken mislukt (debian/ubuntu: sudo apt install python3-venv)"; exit 1; }
fi
"$VPY" -m pip install --quiet selenium

echo "chrome downloaden..."
"$VPY" "$DEST/app/app.py" --setup

if [ "$OS" = "Linux" ] && command -v ldd >/dev/null 2>&1; then
  MISSING="$(ldd "$DEST/chrome-linux64/chrome" 2>/dev/null | grep 'not found' || true)"
  if [ -n "$MISSING" ]; then
    echo "chrome mist libraries:"
    echo "$MISSING"
    echo "debian/ubuntu: sudo apt install libnss3 libgbm1 libgtk-3-0 libxkbcommon0 libasound2 (of libasound2t64)"
  fi
fi

LAUNCH="$DEST/memorybot"
cat > "$LAUNCH" <<EOF
#!/usr/bin/env bash
exec "$VPY" "$DEST/app/app.py" "\$@"
EOF
chmod +x "$LAUNCH"

if [ "$OS" = "Darwin" ]; then
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Memory Bot</string>
  <key>CFBundleDisplayName</key><string>Memory Bot</string>
  <key>CFBundleIdentifier</key><string>local.memorybot</string>
  <key>CFBundleExecutable</key><string>MemoryBot</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
  cp "$LAUNCH" "$APP/Contents/MacOS/MemoryBot"
  chmod +x "$APP/Contents/MacOS/MemoryBot"

  if [ -f "$SRC/icon.png" ]; then
    ICONSET="$(mktemp -d)/icon.iconset"
    mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
      sips -z $s $s "$SRC/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
      sips -z $((s * 2)) $((s * 2)) "$SRC/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns" || echo "icoon maken mislukt"
    rm -rf "$(dirname "$ICONSET")"
  fi
  touch "$APP"

  echo
  echo "klaar. 'Memory Bot' staat in je Apps (Programma's) map."
else
  mkdir -p "$(dirname "$DESKTOP_FILE")"
  if [ -f "$DEST/app/icon.png" ]; then
    ICON_LINE="$DEST/app/icon.png"
  else
    ICON_LINE="applications-education"
  fi
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Memory Bot
Comment=Memorylab helper
Exec="$LAUNCH"
Terminal=false
Categories=Education;
Icon=$ICON_LINE
EOF
  chmod +x "$DESKTOP_FILE"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname "$DESKTOP_FILE")" || true
  echo
  echo "klaar. zoek 'Memory Bot' in je applicatiemenu."
fi
echo "lijsten zetten in: $DEST/app/lists"
