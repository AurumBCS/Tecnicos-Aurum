#!/bin/bash
# Instala la app de confirmaciones por WhatsApp (una sola vez por Mac).
cd "$(dirname "$0")"
echo ""; echo "  Instalando Confirmaciones WhatsApp · Aurum"; echo ""
if ! command -v node >/dev/null 2>&1; then
  echo "  Falta Node.js. Se abre la página de descarga: instala la versión LTS y vuelve a abrir este archivo."
  open "https://nodejs.org/es/download"; read -p "  Pulsa Enter para cerrar..."; exit 1
fi
if [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "  Aviso: no está Google Chrome. Se descargará un navegador interno (~170 MB)."
  export PUPPETEER_SKIP_DOWNLOAD=
else
  export PUPPETEER_SKIP_DOWNLOAD=1
fi
npm install --no-audit --no-fund || { echo "  [ERROR] Falló la instalación."; read -p "  Pulsa Enter..."; exit 1; }
echo ""; echo "  ✅ Instalado. Abre «Abrir Confirmaciones WhatsApp.command»."; read -p "  Pulsa Enter para cerrar..."
