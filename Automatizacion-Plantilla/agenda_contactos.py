"""
Primer contacto de cada mantenimiento de HOY, para el apartado "Cumplimiento de hoy" de la
vista del JE en la app.

Lo usa mac_tarde.py --manana (8:00) con los CSV de la consola de Oracle que ya descarga para
la ruta: no se hace ninguna lectura más. Los contactos solo pasan por memoria y se suben al
Apps Script (type=agenda-contactos), que los guarda en las propiedades del script hasta las
18:05, cuando mac_tarde.py (sin --manana) los borra. No se escriben en disco ni en el log.

Primer contacto = la primera persona de "Personas de Contacto"; si no hay ninguna, el
"Nombre del Cliente" con el móvil (o el fijo).
"""

import csv
import html
import io
import json
import os
import re
import urllib.request
from pathlib import Path

EXEC = ("https://script.google.com/macros/s/AKfycbxotyAfeX08YR-Sx4QuYCt41SOwmfVX5ltxq4n0L2-"
        "XVJoahUkdlo4_EY8-SCDfVgR7/exec")
CLAVE_FICHERO = Path("/Users/gustavoperez/Correo Recuentos/recuentos_clave.txt")

_PERSONA = re.compile(r"<PERSON\b([^>]*)>", re.I)
_ATRIB = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def _limpiar_tel(t):
    t = re.sub(r"[^\d+]", "", str(t or ""))
    return t if len(re.sub(r"\D", "", t)) >= 6 else ""


def primer_contacto(fila):
    """(nombre, telefono) de una fila del CSV de la consola, o None."""
    for m in _PERSONA.finditer(str(fila.get("Personas de Contacto") or "")):
        a = {k.upper(): html.unescape(v).strip() for k, v in _ATRIB.findall(m.group(1))}
        tel = _limpiar_tel(a.get("PHONE")) or _limpiar_tel(a.get("PHONE2"))
        if a.get("NAME") or tel:
            return a.get("NAME", ""), tel
    tel = _limpiar_tel(fila.get("Teléfono Móvil")) or _limpiar_tel(fila.get("Teléfono Fijo"))
    nombre = str(fila.get("Nombre del Cliente") or "").strip()
    return (nombre, tel) if (nombre or tel) else None


def contactos_de_csvs(csvs):
    """{numero: [nombre, telefono]} de los CSV [(grupo, texto)] de la consola."""
    out = {}
    for _, texto in csvs:
        for r in csv.DictReader(io.StringIO(texto)):
            n = str(r.get("Número de Mantenimiento") or "").strip()
            c = primer_contacto(r) if n else None
            if c:
                out[n] = list(c)
    return out


def subir(dia_iso, contactos):
    """Sube los contactos del día (vacío = borrar). Devuelve la respuesta del Apps Script."""
    url = os.environ.get("RECUENTOS_SCRIPT_URL", EXEC).strip() + "?type=agenda-contactos"
    key = os.environ.get("RECUENTOS_KEY", "").strip() or CLAVE_FICHERO.read_text().strip()
    datos = json.dumps({"key": key, "dia": dia_iso, "contactos": contactos}).encode()
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError("el Apps Script no guardó los contactos: " + str(res.get("error")))
    return res


def borrar():
    return subir("", {})
