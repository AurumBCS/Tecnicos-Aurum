"""
Lectura de la ficha "Detalles de actividad" de Oracle Field Service a partir
de su texto visible (page.locator("body").inner_text()).

Solo se sacan los datos que sirven para entender POR QUE se repitio un
mantenimiento (tipo, observaciones del tecnico, codificaciones, zonas e
historico). Los datos del cliente (nombre, telefonos, email, direccion,
personas de contacto) NO se guardan: se ignoran las secciones de contacto y
se borran telefonos/emails que aparezcan dentro de los textos libres.

Estructura vista en la prueba del 2026-10-19 (mantenimiento 136293991):
  - Etiqueta en una linea y valor en la siguiente ("Tipo de Mantenimiento" /
    "Pilas Bajas Elemento").
  - Tablas con columnas separadas por tabuladores, debajo de su titulo
    ("Información de Zonas", "Codificaciones", "Histórico de Mantenimientos").
"""

import re

CAMPOS = {
    "Número de Mantenimiento": "numero",
    "Tipo de Mantenimiento": "tipo",
    "Estado de la Actividad": "estado",
    "Duración de la Actividad": "duracion",
    "Cita": "cita",
    "Inicio - Fin": "inicio_fin",
    "Fecha apertura mto": "apertura",
    "Grupo de Panel": "grupo_panel",
    "Panel": "panel",
    "Versión": "version_panel",
    "Historial atípico": "historial_atipico",
    "Tipología de visita": "tipologia",
    "Fecha de la Instalación": "fecha_instalacion",
}

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TELEFONO = re.compile(r"(?<!\d)(?:\+?34[ -]?)?[6789]\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)")
_RE_NOMBRE = re.compile(r"Nombre:.*?(?=Tlf:|$)", re.IGNORECASE)
_RE_TLF = re.compile(r"Tlf:\s*\S*", re.IGNORECASE)


def limpiar(texto):
    """Quita telefonos, emails y 'Nombre:' de un texto libre."""
    texto = _RE_NOMBRE.sub("Nombre:[omitido] ", texto or "")
    texto = _RE_TLF.sub("Tlf:[omitido]", texto)
    texto = _RE_EMAIL.sub("[email omitido]", texto)
    texto = _RE_TELEFONO.sub("[tel omitido]", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _valor(lineas, etiqueta):
    for i, l in enumerate(lineas[:-1]):
        if l.strip() == etiqueta:
            return lineas[i + 1].strip()
    return ""


def _tabla(lineas, titulo, primera_columna):
    """Filas (dict) de la PRIMERA tabla bajo `titulo` cuya cabecera empieza por `primera_columna`."""
    for i, l in enumerate(lineas):
        if l.strip() != titulo:
            continue
        for j in range(i + 1, min(i + 4, len(lineas))):
            cab = [c.strip() for c in lineas[j].split("\t")]
            if primera_columna in cab[:2]:
                cab = [c for c in cab]
                filas = []
                for fila in lineas[j + 1:]:
                    if "\t" not in fila:
                        break
                    celdas = [c.strip() for c in fila.split("\t")]
                    filas.append(dict(zip(cab, celdas)))
                return filas
    return []


def extraer_ficha(texto):
    """dict con lo util de la ficha, o None si el texto no es una ficha abierta."""
    if "Detalles de actividad" not in texto or "DETALLES MANTENIMIENTO" not in texto:
        return None
    lineas = texto.splitlines()
    ficha = {clave: _valor(lineas, etiqueta) for etiqueta, clave in CAMPOS.items()}

    # Cabecera "E-GI-361439- Nombre Apellidos, 05/08/26": solo la matricula del tecnico
    m = re.search(r"^E-[A-Z]+-([A-Z0-9]+)-", texto, re.MULTILINE)
    ficha["tecnico"] = m.group(1) if m else ""

    # Texto de la actividad (bajo NOTAS): motivo de apertura + trabajos + observaciones del tecnico
    actividad = ""
    for i, l in enumerate(lineas[:-1]):
        if l.strip() == "Texto de la Actividad":
            actividad = lineas[i + 1]
    actividad = limpiar(actividad)
    ficha["texto_actividad"] = actividad
    obs = re.search(r"Observaciones:\s*(.*?)(?:\*{4}|$)", actividad)
    ficha["observaciones_tecnico"] = obs.group(1).strip() if obs else ""

    ficha["zonas"] = [
        {k: f.get(k, "") for k in ("ID", "TIPO", "DETECTOR", "DESCRIPCION")}
        for f in _tabla(lineas, "Información de Zonas", "ID")
    ]
    ficha["codificaciones"] = [
        {k: f.get(k, "") for k in ("RAZON", "PROBLEMA", "CAUSA", "RESOLUCION", "ID ITEM", "NUMERO ITEMS", "ZONA RESOLUCION")}
        for f in _tabla(lineas, "Codificaciones", "INDICE")
    ]
    ficha["historico"] = [
        {"razon": f.get("RAZON", ""), "texto": limpiar(f.get("TEXTO", "")), "apertura": f.get("APERTURA", ""),
         "cierre": f.get("CIERRE", ""), "tecnico": f.get("TECNICO", ""), "estado": f.get("ESTADO", "")}
        for f in _tabla(lineas, "Histórico de Mantenimientos", "RAZON")
    ]
    return ficha


def resumen_legible(ficha):
    """Texto corto de una ficha para el correo / revisar a mano."""
    l = [
        f"Mantenimiento {ficha['numero']} · {ficha['tipo']} · técnico {ficha['tecnico']}",
        f"Cita {ficha['cita']} {ficha['inicio_fin']} · duración {ficha['duracion']} · estado {ficha['estado']}",
        f"Panel {ficha['panel']} ({ficha['grupo_panel']}) · historial atípico: {ficha['historial_atipico']}",
        f"Texto de la actividad: {ficha['texto_actividad']}",
        f"Observaciones del técnico: {ficha['observaciones_tecnico'] or '(ninguna)'}",
    ]
    if ficha["codificaciones"]:
        l.append("Codificaciones (causa/resolución/zona): " + "; ".join(
            f"{c['CAUSA']}/{c['RESOLUCION']}/{c['ZONA RESOLUCION'] or '-'}" for c in ficha["codificaciones"]))
    if ficha["historico"]:
        l.append("Histórico (últimos 5):")
        for h in ficha["historico"][:5]:
            l.append(f"  {h['apertura']}→{h['cierre']} {h['razon']} [{h['tecnico']}]: {h['texto'][:300]}")
    return "\n".join(l)
