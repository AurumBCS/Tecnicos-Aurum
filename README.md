# Aurum BC Security — Portal Técnico

Portal interno mobile-first para técnicos, jefes de equipo y coordinadores de **Aurum BC Security**. SPA de un solo archivo HTML/CSS/JS sin frameworks ni build step.

---

## Acceso

**URL en producción:** https://aurumbcs.github.io/Tecnicos-Aurum/

**Login:**
- Todos los usuarios: matrícula + DNI (contraseña)
- Sin DNI, el acceso es denegado con mensaje de error explicativo

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
| `je` | Jefe de equipo (ej. `239831`) | `mainPanel` + `equipoPanel` + pestaña Confirmaciones |
| `jr` | Coordinadores: `JR9426`, `CM9651`, `JN4767`, `GD5381`, `BLAS.ALVAREZ` | `jrPanel` + pestaña Uso de la app |

### Flujo de datos al login

Al hacer login la app lanza en paralelo:

| Endpoint `?type=` | Datos | Caché Apps Script |
|-------------------|-------|-------------------|
| `csv` | KPIs principales por técnico (incluye columna A = Fecha de actualización) | 5 min |
| `auth` | Matrículas + DNI válidos (columnas `Matric` / `DNI` del cuadrante) | 5 min |
| `jerarquia` | JE→técnicos + zona + CuentaJE + CuentaEmpresa por técnico | Sin caché |
| `docs` | Documentos pendientes por técnico | 5 min |
| `flota` | Matrícula del coche asignado | 5 min |
| `vacaciones` | Días disfrutados / restantes / AP + desglose mensual (VAC+AP por mes) | 5 min |
| `rm` | Mantenimientos repetidos (~1000 filas, ~500KB) | Sin caché — supera límite 100KB |
| `cumplimiento` | Visitas cumplidas/no cumplidas (~2000 filas) | Sin caché — supera límite 100KB |
| `medalia-coord` | Promedio satisfacción por zona (solo JR) | 5 min |
| `track` | Registra el acceso del usuario (fire-and-forget, sin respuesta) | — |
| `usage` | Devuelve CSV de accesos por matrícula para dashboard coordinadores | — |

### Variables globales clave

| Variable | Tipo | Contenido |
|----------|------|-----------|
| `JERARQUIA` | Object | jeId → array de matrículas. Reconstruido desde cuadrante al login; fallback hardcodeado. |
| `ZONA_DATA` | Object | mat → zona (string, ej. `'04'`). Columna C del cuadrante. |
| `CUENTA_DATA` | Object | mat → `{je: bool\|null, empresa: bool\|null}`. Columnas X e Y del cuadrante. |
| `AUTH_DATA` | Object | mat → DNI. Pre-inicializado con JEs/coordinadores; ampliado al cargar cuadrante. |
| `AUTH_CUADRANTE_LOADED` | bool | `true` cuando `loadAuth()` termina. Evita falso "matrícula no registrada" por timeout. |
| `MEDALIA_COORD_DATA` | Object | mat → `{promedio, cantidad}`. Por técnico, calculado desde sheet publicado. |

---

## Google Apps Script

**URL del deployment actual:**
```
https://script.google.com/macros/s/AKfycbwGzgQeBM9sTXQax8l8faPxguPR8sYpUu0OU-GScMSXJrRvSOWcACAnVV1GSdH_3bqE/exec
```

El script lee de estos Google Sheets:

| Constante en script | Sheet ID | Contenido |
|---------------------|----------|-----------|
| `SHEET_RM_ID` | `1mdwknpTrcTmDGMnTB-NZQEh0eI5VClo0fsBmk1BLzNM` | Excel mantenimientos (Hoja 1, ~5100 filas) |
| `SHEET_CUMPLIMIENTO_ID` | `1UL3XSri6UVsWRfoU94pV1l9falmDmztMKupeE8U2WIw` | Visitas de cumplimiento |
| `SHEET_CSV_ID` | `1UWfgzyAlu6sK6VLKP0Qoqhs31UfRju1J-zqaR8yuUng` | KPIs resumen técnicos (+ hoja AccesosApp para tracking) |
| `SHEET_DOCS_ID` | `1clqnU3UH0ld86UoL4uvwp_ciAcMwRxeAjqDkbH4QZLc` | Documentos pendientes |
| `SHEET_FLOTA_ID` | `1c990k4SDrPULhP0VQ8xbZunBg7Qo9nhHl2tTDYPxh2s` | Inventario vehículos (hoja INVENTARIO) |
| `SHEET_MEDALIA_ID` | `1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA` | Encuestas de satisfacción (col A = tipo, col E = mat, col P = score CFL Interacción) |
| `REMITENTE` | `gustavoa.perez@verisure.es` | Correo origen de los Excel |

Los sheets publicados como CSV que usa el script:

| Uso | URL publicada |
|-----|---------------|
| Cuadrante (auth + jerarquía) | `https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah_5VokujbrbolwqCAZLRxrDQqrAZiNpgvNZMXeD-KCPLmJqRjIlPGmswlg/pub?output=csv` |
| Medalia CFL | `https://docs.google.com/spreadsheets/d/e/2PACX-1vTIbmLaEbAJoZj7d_lJqtIV-gbx2kTiumryL-Q7fpvkxvCs3PBaMiDCHTYpWHU-SQ1loy9eAT0G1X9n/pub?output=csv` |

### Columnas del cuadrante usadas

| Columna | Índice | Uso |
|---------|--------|-----|
| A | 0 | — |
| C | 2 | Zona del técnico → `ZONA_DATA` |
| D | 3 | Matrícula del JE → `JERARQUIA` |
| E | 4 | Matrícula del técnico → `JERARQUIA` + `AUTH_DATA` |
| I | 8 | DNI del técnico → `AUTH_DATA` |
| X | 23 | `CuentaJE` — "Si cuenta" / "No cuenta" (para el equipo del JE) |
| Y | 24 | `CuentaEmpresa` — "Si cuenta" / "No cuenta" (para KPIs globales) |

Valores posibles en columnas X e Y: `"Si cuenta"` → `true`, `"No cuenta"` → `false`, vacío → `null` (técnico no iniciado, excluido de ambos grupos).

### Funciones del Apps Script

| Función | Descripción |
|---------|-------------|
| `servirCSV()` | KPIs técnicos desde hoja principal |
| `servirAuth()` | Matrículas + DNI del cuadrante. Usa `Utilities.parseCsv()` (maneja comas en nombres de ciudad). Sin filtro de fecha de baja. |
| `servirJerarquia()` | CSV con JE, Matricula, Zona, CuentaJE, CuentaEmpresa. Excluye director (CM9651). |
| `servirDocs()` | Documentos pendientes |
| `servirFlota()` | Vehículos asignados |
| `servirVacaciones()` | Días VAC/AP totales + desglose mensual (claves `feb26_vac`, `feb26_ap`, …) |
| `servirRM()` | Mantenimientos repetidos |
| `servirCumplimiento()` | Visitas de cumplimiento |
| `servirMedialiaCoordinadores()` | CFL Interacción por técnico (`mat, promedio, cantidad`). Lee desde sheet publicado con detección de columnas por nombre de cabecera. |
| `registrarAcceso(mat)` | Escribe fila en hoja AccesosApp con timestamp + matrícula |
| `servirUsage()` | Agrega AccesosApp → CSV con count + último acceso por matrícula |
| `procesarCorreosAurum()` | Trigger horario: detecta adjuntos por asunto y actualiza sheets |
| `limpiarCache()` | Invalida todas las claves de CacheService |

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
3. Actualizar las constantes `*_URL` en `index.html`
4. Ejecutar `limpiarCache()` en el editor del script

---

## Funcionalidades

### Autenticación

- **Todos los usuarios** (técnicos, JEs y coordinadores) deben introducir matrícula + DNI.
- `AUTH_DATA` está pre-inicializado con las credenciales de JEs y coordinadores para que un timeout en la carga del cuadrante no bloquee a esos usuarios.
- Flag `AUTH_CUADRANTE_LOADED`: si el cuadrante aún no ha cargado cuando alguien intenta entrar, muestra "⏳ Datos de acceso aún cargando" en vez de "matrícula no registrada".
- `loadAuth()` acepta el nombre de columna `Matric` (sin tilde), `Matrícula` o `Matricula` para mayor compatibilidad.
- `servirAuth()` usa `Utilities.parseCsv()` (parser RFC 4180 nativo de GAS) para manejar comas dentro de celdas (p.ej. nombres de ciudad como "Santa Cruz de Tenerife, S/C").
- Sin filtro de fecha de baja — pueden entrar todos los que tengan matrícula + DNI en el cuadrante.

### Jerarquía dinámica desde cuadrante

`loadJerarquia()` reconstruye `JERARQUIA`, `ZONA_DATA` y `CUENTA_DATA` al login leyendo el cuadrante:
- Columna D → JE (jefe de equipo)
- Columna E → Matrícula del técnico
- Columna C → Zona del técnico
- Columna X → CuentaJE ("Si cuenta" / "No cuenta")
- Columna Y → CuentaEmpresa ("Si cuenta" / "No cuenta")

Si el endpoint no responde, se usa el `JERARQUIA` hardcodeado como fallback.

### Panel del JE — lista de técnicos con separación cuentan/no cuentan

La lista de técnicos en el panel del JE se divide en dos grupos según columna X del cuadrante:
- **Cuentan para el equipo** — mostrados con opacidad normal, ordenados por ML-V
- **No cuentan** — separados con un divisor y opacidad reducida (0.45)
- Técnicos sin valor en columna X (no han empezado) → no aparecen en ningún grupo

Cabecera: `👥 Técnicos · X cuentan / Y no cuentan`

### Panel del coordinador — bloques de zona con split empresa

Cada bloque de zona (Zonas 4 y 5 / Zonas 6 y 7) agrega KPIs **solo de los técnicos con `CuentaEmpresa = true`** (columna Y). Debajo aparece un cuadro "No cuentan · N" con sus propios promedios (opacidad 0.65), solo si hay técnicos en ese grupo.

Los técnicos sin valor en columna Y (no iniciados) quedan fuera de ambos grupos.

La asignación por zona usa `ZONA_DATA` (columna C del cuadrante), no la pertenencia al JE. Esto permite que un JE con técnicos en zonas distintas (ej. 274629 con técnicos en zonas 04 y 06) contribuya correctamente a cada bloque.

### Dashboard RM (técnico)

El panel de mantenimientos repetidos muestra:
- **Sección superior** — todos los motivos de todas las visitas del técnico (sin límite de top 5)
- **Sección inferior** — motivos específicos de las visitas marcadas como RM repetido (`isRep = true`), usando `rmOnlyMap` separado de `rmMap`

### Banner de actualización

El banner de la app muestra la fecha real de los datos del Sheet (columna A del CSV):
```
Actualizado al 1 de junio de 2026
```

### Vacaciones con desglose mensual

La vista de vacaciones muestra tres indicadores:
- **Disfrutados** — días ya tomados
- **Restantes** — días pendientes
- **As. Propios** — días de asuntos propios

Y un desglose mensual con píldoras de colores:
- Azul → días de vacaciones ese mes
- Naranja → días de asuntos propios ese mes

### Confirmaciones WhatsApp (JEs)

Los jefes de equipo tienen una pestaña **📲 Confirmaciones** que abre una herramienta local de confirmaciones por WhatsApp en `http://localhost:3000`. Si el servidor local no está corriendo, muestra un aviso con instrucciones para arrancarlo (`INICIAR.bat` / `INICIAR.sh`).

### Dashboard "Uso de la app" (coordinadores)

Los coordinadores (`jr`) tienen una pestaña **Uso de la app** que muestra cuántas veces se ha conectado cada matrícula y cuándo fue el último acceso. Los datos se almacenan automáticamente en la hoja `AccesosApp` cada vez que alguien hace login con éxito.

---

## PWA (Progressive Web App)

| Archivo | Descripción |
|---------|-------------|
| `manifest.json` | Nombre "Aurum", color dorado `#c9a84c`, display standalone |
| `sw.js` | Service Worker Network First, versión `v20260626e` |
| `icon-192.png` | Icono 192×192 (logo empresa, PNG real) |
| `icon-512.png` | Icono 512×512 (logo empresa, PNG real) |
| `favicon.ico` | Favicon 32×32 |

Al instalar en pantalla de inicio aparece como **"Aurum"** con el logo de la empresa en Android e iOS.

Cada nuevo deployment del Apps Script debe ir acompañado de un bump de versión en `sw.js` para que los usuarios reciban la versión actualizada de `index.html`.

---

## Estado actual de endpoints verificados

| Endpoint | Estado | Muestra |
|----------|--------|---------|
| `?type=csv` | ✅ OK | KPIs de técnicos + fecha columna A |
| `?type=auth` | ✅ OK | Matrículas válidas (sin filtro fecha baja, Utilities.parseCsv) |
| `?type=jerarquia` | ✅ OK | JE→técnicos + zona + CuentaJE + CuentaEmpresa |
| `?type=docs` | ✅ OK | Documentos pendientes |
| `?type=flota` | ✅ OK | Matrícula coche |
| `?type=vacaciones` | ✅ OK | Días totales + desglose mensual VAC/AP |
| `?type=rm` | ✅ OK | ~1000 registros, %RM con 2 decimales |
| `?type=cumplimiento` | ✅ OK | ~1999 registros, %Cum con 2 decimales |
| `?type=medalia-coord` | ✅ OK | 101 técnicos con CFL Interacción · split cuentan/no cuentan por zona |
| `?type=track` | ✅ OK | Registra acceso (fire-and-forget, no-cors) |
| `?type=usage` | ✅ OK | CSV accesos por matrícula para coordinadores |

---

## Bugs resueltos

### JE 286800 no podía entrar
- La columna de matrícula en el cuadrante se llama `Matric` (sin tilde), no `Matrícula`.
- Fix: `loadAuth()` acepta `row['Matric']||row['Matrícula']||row['Matricula']`.

### Técnicos podían entrar sin DNI
- El check de DNI solo aplicaba a un conjunto fijo `REQUIEREN_DNI`; los técnicos lo saltaban.
- Fix: DNI requerido para todos los usuarios sin excepción.

### Bypass de autenticación por timeout
- Si `loadAuth()` tardaba más de 8s, `AUTH_DATA` era `{}` y la validación se omitía.
- Fix: `AUTH_DATA` pre-inicializado con las credenciales de JEs y coordinadores antes del primer login.

### Matrículas válidas marcadas como "no registradas"
- Técnicos con fecha de baja en columna T del cuadrante quedaban excluidos de `servirAuth()`.
- Fix: eliminado el filtro `!fechaBaja`; puede entrar cualquiera con matrícula + DNI en el cuadrante.

### CSV de auth roto por comas en nombres de ciudad
- `parseCSV()` del Apps Script no manejaba comas dentro de celdas (ej. "Santa Cruz de Tenerife, S/C").
- Fix: reemplazado por `Utilities.parseCsv()` (parser RFC 4180 nativo de GAS).

### Race condition al login — "matrícula no registrada" en carga lenta
- `AUTH_DATA` pre-inicializado con JEs/coordinadores → validación siempre corría, pero técnicos del cuadrante aún no habían cargado.
- Fix: flag `AUTH_CUADRANTE_LOADED`; si es `false` al login, muestra "⏳ Datos aún cargando".

### JERARQUIA hardcodeado — JEs faltantes o con técnicos incorrectos
- JERARQUIA estaba hardcodeado con 6 JEs y listas fijas de técnicos; no reflejaba cambios del cuadrante.
- Fix: `loadJerarquia()` reconstruye JERARQUIA dinámicamente desde cuadrante (col D=JE, E=técnico). Fallback al hardcodeado si falla el endpoint.

### JE 274629 con técnicos en zonas 04 y 06 — contabilizados solo en una zona
- La asignación de zona se hacía por JE (pertenencia al equipo), no por zona real del técnico.
- Fix: `ZONA_DATA` (col C del cuadrante) se usa para filtrar técnicos por zona real; `renderJRPanel()` usa `getTecsPorZona()`.

### Dashboard RM — sección inferior repetía datos de la superior
- Ambas secciones usaban `rmMap` (todos los motivos de todas las visitas).
- Fix: añadido `rmOnlyMap` que solo acumula motivos de visitas con `isRep = true`.

### Dashboard RM — motivos limitados a top 5
- `slice(0,5)` cortaba la lista.
- Fix: eliminado el slice; se muestran todos los motivos.

### Clasificación cuentan/no cuentan — técnicos sin valor contaban como "no cuentan"
- Valor vacío en columna X o Y → `''.includes('si')` → `false` → clasificado como "no cuenta".
- Fix: valor vacío → `null`; solo "No cuenta" explícito → `false`. Técnicos con `null` (no iniciados) excluidos de ambos grupos.

### Corrección de encoding UTF-8
- Usar `Set-Content -Encoding UTF8` en PowerShell escribe UTF-8 con BOM, corrompiendo los caracteres españoles y emojis en el navegador.
- Fix: ediciones en el archivo siempre vía herramienta Edit o `sed` (Bash), nunca `Set-Content` de PowerShell.

### Datos no actualizaban desde Sheets
- Apps Script cacheaba 1-6 horas → reducido a 5 min.
- `limpiarCache()` llamado tras cada `actualizarSheet()`.
- `&t=Date.now()` añadido a todas las URLs de fetch.

### %RM mostraba valor incorrecto
- `loadRM()` guardaba registros sin agregar y usaba índices numéricos en vez de nombres de columna.
- Fix: agregación correcta + detección dinámica de columnas por nombre.

### RM y Cumplimiento devolvían solo cabeceras
- `cache.put()` lanza excepción cuando el valor supera 100KB; el `catch` externo devolvía solo la cabecera hardcodeada.
- Fix: `cache.put()` en su propio try/catch interno; el `return` fuera del bloque try.

### Flota/vacaciones/docs no aparecían al entrar
- Race condition: datos cargaban antes de que `CURRENT_TEC` estuviera asignado.
- Fix: `renderFlota()` llamado directamente en `renderMain()` con retry pattern.

---

## Notas técnicas

### parseCSV (cliente vs. script)
- `parseCSV()` en `index.html` devuelve **objetos con claves por nombre de columna**. Usar siempre `row['nombreColumna']`, nunca `row[0]`.
- En el Apps Script usar `Utilities.parseCsv()` (devuelve arrays de arrays) para datos con comas en celdas.

### Formato numérico europeo
Datos del CSV principal en formato europeo (`1.234,56`). Usar siempre `parseNum()`, `parsePct()`, `parseMoney()`. Nunca `parseFloat()` directamente sobre valores raw del CSV.

### Límite caché Apps Script
`CacheService.getScriptCache()` → **máximo 100KB por clave**. RM y Cumplimiento superan este límite. Si se intenta cachear y falla, el dato se devuelve igual (sin cachear).

### KPI_CONFIG
Array que controla qué KPIs aparecen en la cuadrícula principal. `OTHER_KEYS` controla el bloque secundario "Resto de indicadores". Umbrales de color en `getGrade()` y `getStatus()`.

### Medalia CFL — cómo funciona

`servirMedialiaCoordinadores()` lee un sheet publicado con datos de encuestas. Detecta columnas por nombre de cabecera (no por índice fijo):
- Columna con "tipo" → filtra filas `CFL Interacción`
- Columna con "matricula"/"técnico" → matrícula del técnico
- Columna con "satisfac" → puntuación (0–10, se omiten vacíos)

Devuelve `mat, promedio, cantidad` por técnico. El cliente agrupa por zona usando `ZONA_DATA` y separa cuentan/no cuentan usando `CUENTA_DATA.empresa`.

---

## Archivos del proyecto

```
index.html      ← Toda la app (HTML + CSS + JS, ~2800 líneas)
manifest.json   ← PWA manifest
sw.js           ← Service Worker (Network First, caché por versión)
icon-192.png    ← Icono PWA 192×192
icon-512.png    ← Icono PWA 512×512
favicon.ico     ← Favicon navegador 32×32
CLAUDE.md       ← Instrucciones para Claude Code
README.md       ← Este archivo
```
