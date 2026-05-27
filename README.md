# Aurum BC Security — Portal Técnico

Portal interno mobile-first para técnicos, jefes de equipo y coordinadores de **Aurum BC Security**. SPA de un solo archivo HTML/CSS/JS sin frameworks ni build step.

---

## Acceso

**URL en producción:** https://aurumbcs.github.io/Tecnicos-Aurum/

**Login:**
- Técnicos: matrícula (sin DNI)
- Jefes de equipo y coordinadores: matrícula + DNI

---

## Arquitectura

### Archivo principal
Todo el código vive en `index.html`. No hay dependencias npm, ni compilación, ni servidor. Se puede abrir directamente en el navegador o servir con cualquier servidor estático.

```
python -m http.server 8080
# abrir http://localhost:8080/index.html
```

### Roles de usuario

| Rol | IDs | Panel |
|-----|-----|-------|
| `tecnico` | ID numérico/alfanumérico | `mainPanel` — KPIs propios |
| `je` | Jefe de equipo (ej. `239831`) | `mainPanel` + `equipoPanel` — equipo completo |
| `jr` | Coordinadores: `JR9426`, `CM9651`, `JN4767`, `GD5381`, `BLAS.ALVAREZ` | `jrPanel` — vista global todos los JE |

### Flujo de datos al login

Al hacer login la app lanza en paralelo:

| Endpoint `?type=` | Datos | Caché Apps Script |
|-------------------|-------|-------------------|
| `csv` | KPIs principales por técnico | 5 min |
| `auth` | Matrículas + DNI válidos | 5 min |
| `docs` | Documentos pendientes por técnico | 5 min |
| `flota` | Matrícula del coche asignado | 5 min |
| `vacaciones` | Días disfrutados / restantes | 5 min |
| `rm` | Mantenimientos repetidos (~1000 filas, ~500KB) | Sin caché — supera límite 100KB |
| `cumplimiento` | Visitas cumplidas/no cumplidas (~2000 filas) | Sin caché — supera límite 100KB |
| `medalia-coord` | Promedio satisfacción por zona (solo JR) | 5 min |

---

## Google Apps Script

**URL del deployment actual:**
```
https://script.google.com/macros/s/AKfycbwVkRQOuB0VO112pPtMr8ovKcSDMrPKd6S28IhAjqDFKgNAwcVJPN4g-My6PxZ_rud2/exec
```

El script lee de estos Google Sheets:

| Constante en script | Sheet ID | Contenido |
|---------------------|----------|-----------|
| `SHEET_RM_ID` | `1mdwknpTrcTmDGMnTB-NZQEh0eI5VClo0fsBmk1BLzNM` | Excel mantenimientos (Hoja 1, ~5100 filas) |
| `SHEET_CUMPLIMIENTO_ID` | `1UL3XSri6UVsWRfoU94pV1l9falmDmztMKupeE8U2WIw` | Visitas de cumplimiento |
| `SHEET_CSV_ID` | `1UWfgzyAlu6sK6VLKP0Qoqhs31UfRju1J-zqaR8yuUng` | KPIs resumen técnicos |
| `SHEET_DOCS_ID` | `1clqnU3UH0ld86UoL4uvwp_ciAcMwRxeAjqDkbH4QZLc` | Documentos pendientes |
| `SHEET_FLOTA_ID` | `1c990k4SDrPULhP0VQ8xbZunBg7Qo9nhHl2tTDYPxh2s` | Inventario vehículos (hoja INVENTARIO) |
| `SHEET_MEDALIA_ID` | `1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA` | Encuestas de satisfacción |
| `REMITENTE` | `gustavoa.perez@verisure.es` | Correo origen de los Excel |

### Procesador de correos
El trigger `procesarCorreosAurum` corre cada hora. Detecta adjuntos por asunto del correo:
- `repeated maintenance` o archivo `tabla*` → Sheet RM
- `cumplimiento` → Sheet Cumplimiento
- `notas globales` / `medalia` / `detalle encuestas` → Sheet Medalia
- `.csv` / `resumen` → Sheet CSV principal

Tras cada actualización llama a `limpiarCache()` automáticamente.

### Columnas reales del Sheet RM (Hoja 1)
`Año | Mes | Finalización | Instalación | Mantenimiento(4) | Av/NoAv(5) | Motivo(6) | Técnico(7) | Territorial(8) | ... | ¿Repetido?(11) | ... | Motivo Post(14) | ...`

El script detecta columnas por nombre (no por índice fijo) con fallback a los índices indicados entre paréntesis.

### Columnas reales del Sheet Cumplimiento
`mat(0) | territorial(1) | averia(2) | cumplido(3) | razon(4)`

### Redeploy del Apps Script
Cada cambio en el script requiere nueva versión:
1. Deploy → Manage deployments → ✏️ → New version → Deploy
2. Copiar la nueva URL
3. Actualizar las 8 constantes `*_URL` en `index.html` (líneas 492-499)
4. Ejecutar `limpiarCache()` en el editor del script

---

## PWA (Progressive Web App)

| Archivo | Descripción |
|---------|-------------|
| `manifest.json` | Nombre "Aurum", color dorado `#c9a84c`, display standalone |
| `sw.js` | Service Worker Network First, versión `v20260527` |
| `icon-192.png` | Icono 192×192 (logo empresa, PNG real) |
| `icon-512.png` | Icono 512×512 (logo empresa, PNG real) |
| `favicon.ico` | Favicon 32×32 |

Al instalar en pantalla de inicio aparece como **"Aurum"** con el logo de la empresa en Android e iOS.

---

## Estado actual de endpoints verificados

| Endpoint | Estado | Muestra |
|----------|--------|---------|
| `?type=csv` | ✅ OK | KPIs de técnicos |
| `?type=auth` | ✅ OK | Matrículas válidas |
| `?type=docs` | ✅ OK | Documentos pendientes |
| `?type=flota` | ✅ OK | Matrícula coche |
| `?type=vacaciones` | ✅ OK | Días disfrutados / restantes |
| `?type=rm` | ✅ OK | ~1000 registros, %RM con 2 decimales |
| `?type=cumplimiento` | ✅ OK | ~1999 registros, %Cum con 2 decimales |
| `?type=medalia-coord` | ✅ OK | Zonas 4-5: 9.77 · Zonas 6-7: 9.42 (188 y 147 encuestas) |

---

## Bugs resueltos

### Datos no actualizaban desde Sheets
- Apps Script cacheaba 1-6 horas → reducido a 5 min
- `limpiarCache()` llamado tras cada `actualizarSheet()`
- `&t=Date.now()` añadido a todas las URLs de fetch

### %RM mostraba valor incorrecto
- `loadRM()` guardaba registros sin agregar
- Usaba índices numéricos `row[0]` en vez de `row['tecnico']`
- Fix: agregación correcta + uso de nombres de columna

### RM y Cumplimiento devolvían solo cabeceras
- **Causa real:** `cache.put()` lanza excepción cuando el valor supera 100KB. El `catch` externo atrapaba el error y devolvía solo la línea de cabecera hardcodeada.
- Fix: `cache.put()` en su propio try/catch interno. El `return` movido fuera del bloque try para que siempre devuelva datos aunque la caché falle.

### Detección de columnas por índice hardcodeado
- Sheet RM tiene 41 columnas reales (no 7). Los índices 4 y 7 para nMant/tecnico eran correctos pero frágiles.
- Fix: detección dinámica por nombre de columna normalizado, con fallback a índice.

### Flota/vacaciones/docs no aparecían al entrar
- Race condition: datos cargaban antes de que `CURRENT_TEC` estuviera asignado
- Fix: `renderFlota()` llamado directamente en `renderMain()` con retry pattern

### Dashboard Cumplimiento no abría desde tarjeta KPI
- Click handler evaluado al renderizar; si `CUM_DATA` no cargó aún, apuntaba a `showDetail('cum')`
- Fix: click siempre apunta a `showCumDash()`; fallback silencioso si no hay datos

### Porcentajes con demasiados decimales
- `cum.pct` usaba `Math.round` → entero sin decimales
- Fix: sin redondeo + `.toFixed(2)` en renderizado

### Medalia coordinadores no actualizaba al refrescar
- `doRefreshData()` llamaba `renderJRPanel()` pero no `renderMedialiaCoord()`
- Fix: añadido `renderMedialiaCoord()` tras `renderJRPanel()` en el flujo de refresco

---

## Notas técnicas

### parseCSV (cliente vs. script)
- `parseCSV()` en `index.html` devuelve **objetos con claves por nombre de columna**. Usar siempre `row['nombreColumna']`, nunca `row[0]`.
- `parseCSV()` en Apps Script devuelve arrays de arrays. Son funciones distintas.

### Formato numérico europeo
Datos del CSV principal en formato europeo (`1.234,56`). Usar siempre `parseNum()`, `parsePct()`, `parseMoney()`. Nunca `parseFloat()` directamente sobre valores raw del CSV.

### Límite caché Apps Script
`CacheService.getScriptCache()` → **máximo 100KB por clave**. RM y Cumplimiento superan este límite. Si se intenta cachear y falla, el dato se devuelve igual (sin cachear).

### KPI_CONFIG
Array que controla qué KPIs aparecen en la cuadrícula principal. `OTHER_KEYS` controla el bloque secundario "Resto de indicadores". Umbrales de color en `getGrade()` y `getStatus()`.

---

## Archivos del proyecto

```
index.html      ← Toda la app (HTML + CSS + JS, ~2600 líneas)
manifest.json   ← PWA manifest
sw.js           ← Service Worker (Network First, caché por versión)
icon-192.png    ← Icono PWA 192×192
icon-512.png    ← Icono PWA 512×512
favicon.ico     ← Favicon navegador 32×32
CLAUDE.md       ← Instrucciones para Claude Code
README.md       ← Este archivo
```
