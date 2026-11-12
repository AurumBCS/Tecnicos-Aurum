#!/bin/bash
# Abre la app. Deja esta ventana abierta mientras haya envíos o se esperen respuestas.
cd "$(dirname "$0")"
PORT=3131
if curl -s "http://localhost:$PORT/api/estado" >/dev/null 2>&1; then
  open "http://localhost:$PORT"; exit 0
fi
[ -d node_modules ] || { echo "  Primero abre INSTALAR.command"; read -p "  Pulsa Enter..."; exit 1; }
( sleep 3; open "http://localhost:$PORT" ) &
echo ""; echo "  Confirmaciones WhatsApp · Aurum"
echo "  No cierres esta ventana: si la cierras se para el envío y no se leen las respuestas."; echo ""
node server.js
