#!/bin/bash
# Empaqueta "Aurum WhatsApp" para Mac (.app, Apple Silicon + Intel) y Windows (carpeta con node.exe).
# Uso: ./empaquetar.sh <carpeta con node-vX-darwin-arm64.tar.gz, -darwin-x64.tar.gz y -win-x64.zip> <carpeta de salida>
# Los .zip de Node se descargan de nodejs.org/dist y se comprueban con SHASUMS256.txt antes.
set -euo pipefail
NODE_DL="$1"; OUT="$2"
APP_SRC="$(cd "$(dirname "$0")" && pwd)"
V=$(ls "$NODE_DL" | sed -n 's/^node-\(v[0-9.]*\)-darwin-arm64\.tar\.gz$/\1/p' | head -1)
[ -n "$V" ] || { echo "No encuentro node-vX-darwin-arm64.tar.gz en $NODE_DL"; exit 1; }
TMP="$OUT/.tmp"; rm -rf "$OUT"; mkdir -p "$TMP"

# 1) Código de la app con sus librerías de producción (sin descargar Chromium: usa el Chrome del equipo)
mkdir -p "$TMP/app"
cp "$APP_SRC/server.js" "$APP_SRC/package.json" "$APP_SRC/package-lock.json" "$APP_SRC/aviso-arranque.sh" "$APP_SRC/aviso-arranque.ps1" "$TMP/app/"
VAPP=$(sed -n "s/^const VERSION = '\([^']*\)';/\1/p" "$APP_SRC/server.js")
cp -R "$APP_SRC/public" "$TMP/app/"
( cd "$TMP/app" && PUPPETEER_SKIP_DOWNLOAD=1 npm ci --omit=dev --no-audit --no-fund --ignore-scripts >/dev/null )

# 2) Node de cada sistema
for a in arm64 x64; do
  mkdir -p "$TMP/n-$a" && tar -xzf "$NODE_DL/node-$V-darwin-$a.tar.gz" -C "$TMP/n-$a" --strip-components=2 "node-$V-darwin-$a/bin/node"
done
( cd "$TMP" && unzip -q "$NODE_DL/node-$V-win-x64.zip" "node-$V-win-x64/node.exe" && mv "node-$V-win-x64/node.exe" node.exe )

# 3) Mac: Aurum WhatsApp.app
MAC="$TMP/mac/Aurum WhatsApp.app/Contents"
mkdir -p "$MAC/MacOS" "$MAC/Resources"
cp -R "$TMP/app" "$MAC/Resources/app"
cp "$TMP/n-arm64/node" "$MAC/Resources/node-arm64"; cp "$TMP/n-x64/node" "$MAC/Resources/node-x64"
cat > "$MAC/MacOS/AurumWhatsApp" <<'EOF'
#!/bin/bash
# Arranca el servidor de la app en segundo plano y abre el navegador (lo hace el propio servidor).
R="$(cd "$(dirname "$0")/../Resources" && pwd)"
[ "$(uname -m)" = "arm64" ] && N="$R/node-arm64" || N="$R/node-x64"
mkdir -p "$HOME/Library/Logs"
cd "$R/app"
nohup "$N" server.js >> "$HOME/Library/Logs/AurumWhatsApp.log" 2>&1 &
nohup /bin/bash "$R/app/aviso-arranque.sh" "__VAPP__" >/dev/null 2>&1 &
exit 0
EOF
sed -i '' "s/__VAPP__/$VAPP/" "$MAC/MacOS/AurumWhatsApp"
chmod +x "$MAC/MacOS/AurumWhatsApp"
cat > "$MAC/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Aurum WhatsApp</string>
  <key>CFBundleDisplayName</key><string>Aurum WhatsApp</string>
  <key>CFBundleIdentifier</key><string>com.aurumbcs.whatsapp</string>
  <key>CFBundleExecutable</key><string>AurumWhatsApp</string>
  <key>CFBundleIconFile</key><string>icono</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$(date +%Y.%m.%d)</string>
  <key>CFBundleVersion</key><string>$(date +%Y%m%d%H%M)</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF
LOGO="$APP_SRC/../confirmaciones-sms/public/logo.png"
if [ -f "$LOGO" ]; then
  IS="$TMP/icono.iconset"; mkdir -p "$IS"
  for s in 16 32 64 128 256 512; do sips -z $s $s "$LOGO" --out "$IS/icon_${s}x${s}.png" >/dev/null; done
  for s in 16 32 128 256; do cp "$IS/icon_$((s*2))x$((s*2)).png" "$IS/icon_${s}x${s}@2x.png"; done
  iconutil -c icns "$IS" -o "$MAC/Resources/icono.icns"
fi
codesign --force --deep -s - "$TMP/mac/Aurum WhatsApp.app" 2>/dev/null || true
( cd "$TMP/mac" && ditto -c -k --sequesterRsrc --keepParent "Aurum WhatsApp.app" "$OUT/Aurum-WhatsApp-Mac.zip" )

# 4) Windows: carpeta "Aurum WhatsApp" con node.exe y un lanzador
WIN="$TMP/win/Aurum WhatsApp"
mkdir -p "$WIN/node"
cp -R "$TMP/app" "$WIN/app"; cp "$TMP/node.exe" "$WIN/node/node.exe"
printf '@echo off\r\nrem Abre Aurum WhatsApp. La ventana minimizada es la app: no la cierres mientras haya envios.\r\ncd /d "%%~dp0app"\r\nstart "Aurum WhatsApp (no cerrar)" /min "%%~dp0node\\node.exe" server.js\r\nstart "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%%~dp0app\\aviso-arranque.ps1" -Version %s\r\n' "$VAPP" > "$WIN/Aurum WhatsApp.cmd"
printf '@echo off\r\nrem Crea un acceso directo en el Escritorio y en Inicio (para que se abra al encender el PC).\r\nset "D=%%~dp0"\r\npowershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; foreach($p in @([Environment]::GetFolderPath(\x27Desktop\x27),[Environment]::GetFolderPath(\x27Startup\x27))){ $l=$s.CreateShortcut($p+\x27\\Aurum WhatsApp.lnk\x27); $l.TargetPath=$env:D+\x27Aurum WhatsApp.cmd\x27; $l.WorkingDirectory=$env:D; $l.WindowStyle=7; $l.Save() }"\r\necho Accesos directos creados en el Escritorio y en Inicio.\r\npause\r\n' > "$WIN/Crear accesos directos.cmd"
( cd "$TMP/win" && zip -qr "$OUT/Aurum-WhatsApp-Windows.zip" "Aurum WhatsApp" )

rm -rf "$TMP"
ls -lh "$OUT"
