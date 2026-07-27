#!/bin/bash
echo ""
echo "=========================================="
echo "  Instalacion - Confirmaciones WhatsApp"
echo "  Verisure"
echo "=========================================="
echo ""

# ── 1. Instalar Node.js automáticamente si no está ───────────────────────────
if ! command -v node &> /dev/null; then
    echo "  [!] Node.js no encontrado. Instalando automaticamente..."
    echo ""

    # Instalar via nvm (no requiere contraseña ni permisos de admin)
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

    # Cargar nvm en la sesión actual
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

    # Instalar la versión LTS de Node.js
    nvm install --lts
    nvm use --lts

    if ! command -v node &> /dev/null; then
        echo ""
        echo "  [ERROR] No se pudo instalar Node.js automaticamente."
        echo "  Descargalo manualmente desde: https://nodejs.org"
        open "https://nodejs.org/en/download"
        read -p "  Pulsa Enter para cerrar..."
        exit 1
    fi
fi

echo "  [OK] Node.js: $(node --version)"
echo ""

# ── 2. Limpiar cache de Chromium si está incompleta ──────────────────────────
CHROME_HEADLESS="$HOME/.cache/puppeteer/chrome-headless-shell"
if [ -d "$CHROME_HEADLESS" ]; then
    # Verificar si el ejecutable está realmente ahí; si no, borrar carpeta incompleta
    if ! find "$CHROME_HEADLESS" -name "chrome-headless-shell" -type f 2>/dev/null | grep -q .; then
        echo "  [!] Cache de Chromium incompleta detectada. Limpiando..."
        rm -rf "$CHROME_HEADLESS"
    fi
fi

# ── 3. Instalar dependencias del proyecto ─────────────────────────────────────
echo "  Instalando dependencias (puede tardar 5-10 minutos)..."
echo "  Se descargara el navegador interno necesario (~170 MB)."
echo ""

cd "$(dirname "$0")"
npm install

if [ $? -ne 0 ]; then
    echo ""
    echo "  [ERROR] Fallo la instalacion."
    echo ""
    echo "  Limpiando cache y reintentando..."
    rm -rf "$HOME/.cache/puppeteer"
    npm install
    if [ $? -ne 0 ]; then
        echo ""
        echo "  [ERROR] No se pudo instalar. Comprueba tu conexion a internet."
        read -p "  Pulsa Enter para cerrar..."
        exit 1
    fi
fi

# ── 2b. Verificar que el navegador interno (Chrome) esta completo ─────────────
echo ""
echo "  Verificando navegador interno..."
CHROME_OK=$(node -e "try{const fs=require('fs');const e=require('puppeteer').executablePath();process.stdout.write(fs.existsSync(e)?'1':'0')}catch(e){process.stdout.write('0')}" 2>/dev/null)

if [ "$CHROME_OK" != "1" ]; then
    echo "  [!] El navegador no se descargo completo. Descargandolo aparte..."
    echo ""
    # Limpiar descargas a medias y bajar Chrome explicitamente
    rm -rf "$HOME/.cache/puppeteer/chrome" 2>/dev/null
    rm -rf "$HOME/.cache/puppeteer/chrome-headless-shell" 2>/dev/null
    npx puppeteer browsers install chrome
    if [ $? -ne 0 ]; then
        echo ""
        echo "  [!] No se pudo descargar el navegador interno."
        echo "  IMPORTANTE: instala Google Chrome desde https://www.google.com/chrome/"
        echo "  La app usara ese Chrome del sistema automaticamente."
        open "https://www.google.com/chrome/" 2>/dev/null
        echo ""
    else
        echo "  [OK] Navegador interno descargado."
    fi
else
    echo "  [OK] Navegador interno completo."
fi

# ── 3. Dar permisos y quitar cuarentena de toda la carpeta ───────────────────
echo "  Aplicando permisos..."
APPDIR="$(dirname "$0")"
chmod +x "$APPDIR/INICIAR.sh"
chmod +x "$APPDIR/INSTALAR.sh"
# Quitar atributo de cuarentena de macOS de toda la carpeta
xattr -cr "$APPDIR" 2>/dev/null
echo "  [OK] La proxima vez podras ejecutar INICIAR.sh directamente."

# ── 4. Quitar bloqueo de seguridad de macOS sobre Chromium ───────────────────
echo ""
echo "  Aplicando permisos de seguridad para macOS..."
CHROME_CACHE="$HOME/.cache/puppeteer"
if [ -d "$CHROME_CACHE" ]; then
    xattr -cr "$CHROME_CACHE" 2>/dev/null
fi
# Buscar también en la cache local del proyecto
find "$(dirname "$0")/node_modules/.cache" -name "chrome" -type d 2>/dev/null | while read dir; do
    xattr -cr "$dir" 2>/dev/null
done
CHROME_PATH=$(node -e "try{const {executablePath}=require('puppeteer');console.log(executablePath())}catch(e){}" 2>/dev/null)
if [ ! -z "$CHROME_PATH" ]; then
    xattr -cr "$(dirname "$CHROME_PATH")" 2>/dev/null
    echo "  [OK] Chromium desbloqueado."
fi

echo ""
echo "=========================================="
echo "  Instalacion completada correctamente!"
echo "=========================================="
echo ""
echo "  Desde ahora usa INICIAR.sh para arrancar cada dia."
echo "  Puedes hacer doble clic en el o ejecutarlo desde Terminal."
echo ""
read -p "  Pulsa Enter para cerrar..."
