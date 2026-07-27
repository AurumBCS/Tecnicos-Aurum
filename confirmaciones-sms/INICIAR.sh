#!/bin/bash
clear
echo ""
echo "=========================================="
echo "  Verisure - Portal + Confirmaciones WA"
echo "=========================================="
echo ""

DIR="$(cd "$(dirname "$0")" && pwd)"

# Cargar nvm si Node fue instalado por esa vía
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo "  [ERROR] Node.js no esta instalado."
    echo "  Ejecuta primero INSTALAR.sh"
    echo ""
    read -p "  Pulsa Enter para cerrar..."
    exit 1
fi

# Verificar dependencias
if [ ! -d "$DIR/node_modules" ] || [ ! -d "$DIR/node_modules/express" ]; then
    echo "  [!] Dependencias no instaladas correctamente."
    echo "  Ejecuta primero INSTALAR.sh"
    echo ""
    read -p "  Pulsa Enter para cerrar..."
    exit 1
fi

# Cerrar instancia anterior en el puerto 3000
OLD_PID=$(lsof -ti:3000 2>/dev/null)
if [ ! -z "$OLD_PID" ]; then
    kill -9 $OLD_PID 2>/dev/null
    sleep 1
fi

echo "  Arrancando servidor..."
echo "  El portal se abrira en el navegador en unos segundos."
echo ""
echo "  NO cierres esta ventana mientras uses la aplicacion."
echo "  Para salir: Cmd+C o cierra esta ventana."
echo ""
echo "=========================================="
echo ""

cd "$DIR"

# Forzar uso del Google Chrome instalado en Mac
if [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    echo "  Chrome: Google Chrome del sistema"
elif [ -f "/Applications/Chromium.app/Contents/MacOS/Chromium" ]; then
    export PUPPETEER_EXECUTABLE_PATH="/Applications/Chromium.app/Contents/MacOS/Chromium"
    echo "  Chrome: Chromium del sistema"
fi

# Esperar a que el servidor esté listo y abrir el portal (en background)
(
  intentos=0
  until curl -s http://localhost:3000/status > /dev/null 2>&1; do
    sleep 1
    intentos=$((intentos+1))
    if [ $intentos -ge 30 ]; then break; fi
  done
  open "http://localhost:3000/portal/"
) &

# Arrancar servidor en primer plano — la Terminal queda abierta con los logs
node server.js
