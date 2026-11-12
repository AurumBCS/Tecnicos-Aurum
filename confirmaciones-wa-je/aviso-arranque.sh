#!/bin/bash
# Lo lanza "Aurum WhatsApp.app": si a los 12 s la app no responde (p. ej. un macOS
# demasiado antiguo para Node), avisa a Render con el sistema y las últimas líneas
# del registro. Sin datos de clientes.
sleep 12
curl -s -m 5 http://127.0.0.1:3131/api/estado >/dev/null 2>&1 && exit 0
limpia() { tr -d '"\\' | tr '\r\n\t' '   ' | cut -c1-380; }
CONF="$HOME/Library/Application Support/AurumWhatsApp/config.json"
MAT=$(sed -n 's/.*"mat" *: *"\([^"]*\)".*/\1/p' "$CONF" 2>/dev/null | head -1 | limpia)
SO="macOS $(sw_vers -productVersion 2>/dev/null)"
CH=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null | limpia)
DET=$(tail -4 "$HOME/Library/Logs/AurumWhatsApp.log" 2>/dev/null | limpia)
curl -s -m 90 -H 'Content-Type: application/json' \
  -d "{\"mat\":\"$MAT\",\"evento\":\"no-arranca\",\"version\":\"$1\",\"so\":\"$SO\",\"arch\":\"$(uname -m)\",\"chrome\":\"${CH:-sin Chrome}\",\"detalle\":\"$DET\"}" \
  https://tecnicos-aurum.onrender.com/wa-diagnostico >/dev/null 2>&1
