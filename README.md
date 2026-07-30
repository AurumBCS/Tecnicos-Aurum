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
| `rm` | Mantenimientos repetidos (`nMant`, `nMantPost` para causa raíz — ver abajo) | Sin caché — supera límite 100KB |
| `cumplimiento` | Visitas cumplidas/no cumplidas (incluye `nmant` por fila) | Sin caché — supera límite 100KB |
| `medalia-coord` | Promedio satisfacción por zona (solo JR) | 5 min |
| `track` | Registra el acceso del usuario (fire-and-forget, sin respuesta) | — |
| `usage` | Devuelve CSV de accesos por matrícula para dashboard coordinadores | — |

### Variables globales clave

| Variable | Tipo | Contenido |
|----------|------|-----------|
| `JERARQUIA` | Object | jeId → array de matrículas. Reconstruido desde cuadrante al login; fallback hardcodeado. |
| `ZONA_DATA` | Object | mat → zona (string, ej. `'04'`). Columna C del cuadrante. |
| `CUENTA_DATA` | Object | mat → `{je: bool\|null, empresa: bool\|null}`. Desde `CuentaJE`/`CuentaEmpresa` del cuadrante. |
| `AUTH_DATA` | Object | mat → DNI. Pre-inicializado con JEs/coordinadores; ampliado al cargar cuadrante. |
| `AUTH_CUADRANTE_LOADED` | bool | `true` cuando `loadAuth()` termina. Evita falso "matrícula no registrada" por timeout. |
| `MEDALIA_COORD_DATA` | Object | mat → `{promedio, cantidad}`. Por técnico, calculado desde sheet publicado. |
| `RM_DATA` | Object | mat → `{visitas[], total, reps, pctRM, topPost, motivosRM, topMotivos}`. Cada visita trae `{nMant, motivo, repetido, motivo_post, nMantPost}`. |
| `CUM_DATA` | Object | mat → `{total, ok, noOk, pct, topRazones, visitas[]}`. Cada visita trae `{nMant, razon, ok}`. |
| `RM_ROW_LOOKUP` | Object | rowId → `{tecId, tipo, motivo}`. Usado por `toggleMantenimientosMotivo()` para saber qué desplegar al hacer click. |

---

## Google Apps Script

**URL del deployment actual:**
```
https://script.google.com/macros/s/AKfycbyPC8I3igKkEZqnnX_MDSKDh7NrvLcuWKaXPb3yG5oEv3Ho_yumQLA2OnmoLeaglsRQ/exec
```

> ⚠️ Cada vez que se genera un **nuevo deployment** (no una nueva versión del mismo), la URL cambia y hay que actualizar las 11 constantes `*_URL` en `index.html` + bump de versión en `sw.js`. Ver sección "Redeploy" más abajo.

El script lee de estos Google Sheets:

| Constante en script | Sheet ID | Contenido |
|---------------------|----------|-----------|
| `SHEET_RM_ID` | `1mdwknpTrcTmDGMnTB-NZQEh0eI5VClo0fsBmk1BLzNM` | Excel mantenimientos repetidos (Hoja 1) |
| `SHEET_CUMPLIMIENTO_ID` | `1UL3XSri6UVsWRfoU94pV1l9falmDmztMKupeE8U2WIw` | Visitas de cumplimiento (hoja `Cumplimiento_Aurum`) |
| `SHEET_CSV_ID` | `1UWfgzyAlu6sK6VLKP0Qoqhs31UfRju1J-zqaR8yuUng` | KPIs resumen técnicos ("Resumen App Claude" + hoja AccesosApp) |
| `SHEET_DOCS_ID` | `1clqnU3UH0ld86UoL4uvwp_ciAcMwRxeAjqDkbH4QZLc` | Documentos pendientes |
| `SHEET_CUADRANTE_ID` | `1HqOI_kN10tAnBmeTrPqAklEa4f-1-DWQ` | Cuadrante (usado por `obtenerNombresTecnicos()`) |
| `SHEET_FLOTA_ID` | `1c990k4SDrPULhP0VQ8xbZunBg7Qo9nhHl2tTDYPxh2s` | Inventario vehículos (hoja INVENTARIO) |
| `SHEET_MEDALIA_ID` | `1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA` | Encuestas de satisfacción |
| `REMITENTE` | `gustavoa.perez@verisure.es` | Correo origen de **todos** los Excel adjuntos (RM, Cumplimiento, Medalia, Resumen, Mtos_Finalizados) |

Los sheets publicados como CSV que usa el script directamente (no pasan por `actualizarSheet`):

| Uso | URL publicada |
|-----|---------------|
| Cuadrante (auth + jerarquía) | `https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah_5VokujbrbolwqCAZLRxrDQqrAZiNpgvNZMXeD-KCPLmJqRjIlPGmswlg/pub?output=csv` |
| Medalia CFL | `https://docs.google.com/spreadsheets/d/e/2PACX-1vTIbmLaEbAJoZj7d_lJqtIV-gbx2kTiumryL-Q7fpvkxvCs3PBaMiDCHTYpWHU-SQ1loy9eAT0G1X9n/pub?output=csv` |
| Vacaciones | `https://docs.google.com/spreadsheets/d/e/2PACX-1vR9A0fhBk2ViKKewyKP8rJz364_MsEwi8CD_DEIjokUAeZiJzieR1k3KuZm6Kx9B68YrNTtalq8peFn/pub?output=csv` |

### Columnas del cuadrante publicado usadas por `servirJerarquia()` / `servirAuth()`

⚠️ **Estos índices son frágiles** — ya se rompieron una vez (julio 2026) cuando alguien quitó 2 columnas ("F Baja", "Motivo") del cuadrante y los índices fijos quedaron desalineados. Si vuelve a pasar algo similar (JE viendo "0 cuentan / 0 no cuentan"), es la primera sospecha: contar columnas reales del sheet publicado contra estos índices.

| Columna real (hoy) | Índice | Uso |
|---------------------|--------|-----|
| Territorial | 2 | Zona del técnico → `ZONA_DATA` |
| JDE | 3 | Matrícula del JE → `JERARQUIA` |
| Matricula | 4 | Matrícula del técnico → `JERARQUIA` + `AUTH_DATA` |
| DNI | 8 | DNI del técnico → `AUTH_DATA` |
| Cuenta JDE | **21** | `CuentaJE` — "Si Cuenta" / "No Cuenta" (para el equipo del JE) |
| Cuenta E | **22** | `CuentaEmpresa` — "Si Cuenta" / "No Cuenta" (para KPIs globales) |

Valores posibles: `"Si cuenta"` → `true`, `"No cuenta"` → `false`, vacío → `null` (técnico no iniciado, excluido de ambos grupos).

### Funciones del Apps Script

| Función | Descripción |
|---------|-------------|
| `servirCSV()` | KPIs técnicos desde hoja principal |
| `servirAuth()` | Matrículas + DNI del cuadrante |
| `servirJerarquia()` | CSV con JE, Matricula, Zona, CuentaJE, CuentaEmpresa |
| `servirDocs()` | Documentos pendientes |
| `servirFlota()` | Vehículos asignados |
| `servirVacaciones()` | Días VAC/AP totales + desglose mensual |
| `servirRM()` | Mantenimientos repetidos. Devuelve `nMant,motivo,tecnico,territorial,repetido,motivo_post,averia,nMantPost` — **`nMant` (col E) es de la visita repetida, `nMantPost` (col M) es del post-mantenimiento; son números distintos, no reutilizar uno para el otro.** |
| `servirCumplimiento()` | Visitas de cumplimiento. Devuelve `mat,territorial,averia,cumplido,razon,nmant`. Aplica `fixMojibake_()` a texto con posibles acentos rotos (`Ã¡` → `á`). |
| `servirMedialiaCoordinadores()` | CFL Interacción por técnico |
| `registrarAcceso(mat)` / `servirUsage()` | Tracking de accesos |
| `procesarCorreosAurum()` | Trigger horario — RM/Cumplimiento/Medalia/Resumen (ver abajo) |
| `procesarMtosFinalizados()` | Trigger horario **independiente** — solo Mtos_Finalizados (ver abajo) |
| `limpiarCache()` | Invalida todas las claves de CacheService |
| `archivarSiHuboCambioDeMes_()` / `archivarMtosSiHuboCambioDeMes_()` | Archivado mensual automático (ver sección dedicada) |

### Procesador de correos principal (`procesarCorreosAurum`)

Trigger horario. Busca correos sin leer de `REMITENTE` con adjunto, y los clasifica por asunto/nombre de archivo:
- `repeated maintenance` o archivo `tabla*` → `SHEET_RM_ID`
- `cumplimiento` → `SHEET_CUMPLIMIENTO_ID`
- `notas globales` / `medalia` / `detalle encuestas` → `SHEET_MEDALIA_ID`
- `.csv` / `resumen` → `SHEET_CSV_ID`

Cada adjunto (Excel o CSV) se convierte a CSV vía exportación temporal de Drive y **sobrescribe por completo** la hoja destino (`sheet.clearContents()` + `setValues()`). Después llama a `limpiarCache()`.

### Procesador de Mtos_Finalizados (`procesarMtosFinalizados`) — automatización separada

A diferencia de RM/Cumplimiento/Medalia/Resumen (que van a un Google Sheet), **Mtos_Finalizados_Aurum llega como Excel crudo y se guarda tal cual en Drive** (no se convierte a Sheet, todavía no hay un endpoint `?type=` que lo sirva — es la base para migrar el cálculo de KPIs fuera de "Resumen App Claude", ver sección "Plan de migración").

- Busca correos de `MTOS_REMITENTE` con adjunto que empiece con `Mtos_Finalizados_Aurum`, sin la etiqueta `Procesado-MtosFinalizados`
- Guarda el adjunto en la carpeta de Drive **"Mtos Finalizados Aurum"** como `Mtos_Finalizados_Aurum.xlsx`, **borrando la versión anterior** (siempre queda solo la más reciente)
- Etiqueta el correo como procesado
- Trigger horario instalado vía `instalarTriggerMtosFinalizados()` (ejecutar una sola vez manualmente tras pegar el código)

Funciones auxiliares: `getOrCreateCarpeta_(nombre)`, `getOrCreateLabel_(nombre)`.

### Archivado mensual automático (histórico)

Ninguna de las hojas anteriores guardaba histórico — cada correo nuevo sobrescribía el mes anterior sin dejar rastro. Para no perder datos al cambiar de mes, `actualizarSheet()` y `guardarEnDrive_()` ahora archivan **antes** de sobrescribir:

- `archivarSiHuboCambioDeMes_(ss, tipo)` — para RM/Cumplimiento/Medalia/Resumen (Google Sheets). Detecta cambio de mes (usando la fecha real de la columna A para "CSV"/Resumen vía `detectarMesReal_()`, o el reloj del sistema como respaldo para los demás) y, si cambió, copia el sheet completo a la carpeta **"Historico {Tipo} Aurum"** con nombre **"{Tipo} {Mes} Aurum"** (ej. `Cumplimiento Junio 2026 Aurum`).
- `archivarMtosSiHuboCambioDeMes_(carpeta, nombreArchivo)` — mismo concepto para el Excel crudo de Mtos_Finalizados, copiándolo a **"Historico Mtos Finalizados Aurum"** como `Mtos_Finalizados {Mes} Aurum.xlsx`.
- El checkpoint de "qué mes ya se archivó" se guarda en `PropertiesService.getScriptProperties()` (`ultimoMesArchivado_{tipo}`), así que solo archiva **una vez por mes real**, sin importar cuántos correos lleguen ese mes.
- La **primera vez** que corre no archiva nada (no sabe si el contenido actual es de un mes ya cerrado o no) — solo registra el mes actual como checkpoint. El archivado real empieza a partir del **segundo** cambio de mes detectado.

**Para el histórico retroactivo (febrero–junio 2026):** el usuario coloca manualmente los Excel de esos meses en las mismas carpetas `Historico {Tipo} Aurum`, con el mismo formato de nombre `{Tipo} {Mes} Aurum` (ej. `Resumen Febrero Aurum`, `RM Marzo Aurum`), para que quede compatible con lo que el sistema genera automáticamente hacia adelante.

**Pendiente (no implementado aún):** endpoint para leer un mes histórico específico + selector de mes en la vista de coordinador (`GD5381`) + agregación trimestral/semestral por técnico.

### Redeploy del Apps Script
Cada cambio en el script requiere nueva versión:
1. Deploy → Manage deployments → ✏️ → New version → Deploy
2. Si Google genera una **URL nueva** (deployment nuevo, no versión), copiarla y actualizar las 11 constantes `*_URL` en `index.html`
3. Bump de versión en `sw.js` (fuerza actualización de caché del Service Worker en los clientes)
4. Commit + push a `main` → GitHub Pages publica automáticamente (~1-2 min)
5. Ejecutar `limpiarCache()` en el editor del script si el cambio no involucra `doGet`

**Nota sobre fallos de GitHub Pages:** el workflow "pages build and deployment" a veces falla de forma transitoria con el error genérico de GitHub `"Deployment failed, try again later."` (el build en sí siempre tuvo éxito, solo falla el paso de deploy). No es un problema de nuestro código — basta con hacer un nuevo commit/push (ej. bump de versión de `sw.js`) para reintentar. Si falla 2-3 veces seguidas en poco tiempo, esperar ~10 min antes de reintentar (parece estar relacionado con la frecuencia de despliegues).

---

## Funcionalidades

### Autenticación

- **Todos los usuarios** (técnicos, JEs y coordinadores) deben introducir matrícula + DNI.
- `AUTH_DATA` está pre-inicializado con las credenciales de JEs y coordinadores para que un timeout en la carga del cuadrante no bloquee a esos usuarios.
- Flag `AUTH_CUADRANTE_LOADED`: si el cuadrante aún no ha cargado cuando alguien intenta entrar, muestra "⏳ Datos de acceso aún cargando" en vez de "matrícula no registrada".

### Jerarquía dinámica desde cuadrante

`loadJerarquia()` reconstruye `JERARQUIA`, `ZONA_DATA` y `CUENTA_DATA` al login. Si el endpoint no responde, se usa el `JERARQUIA` hardcodeado como fallback.

### Panel del JE — lista de técnicos con separación cuentan/no cuentan

Cabecera: `👥 Técnicos · X cuentan / Y no cuentan`. Técnicos sin valor en la columna correspondiente (no han empezado) no aparecen en ningún grupo.

### Panel del coordinador — bloques de zona con split empresa

Cada bloque de zona agrega KPIs solo de técnicos con `CuentaEmpresa = true`. La asignación por zona usa `ZONA_DATA`, no la pertenencia al JE.

### Dashboards de ranking (JE y coordinador)

En la vista de equipo del JE, los 4 KPIs (`%RM`, `%Cumplimiento`, `Conversión`, `PPA`) abren un dashboard con ranking de todos los técnicos del equipo, ordenado de mayor a menor, vía `showEquipoDash(type, jeId)`.

**Sección "Rankings"** (separada de los KPIs con objetivo, arriba): 4 rankings puramente comparativos (sin umbral de aprobado/reprobado) — Mantenimientos realizados (`palito`), Números de ventas (`uven`), Conversión (`conv`) y 20% en € (`ventas`). Disponibles en dos alcances:
- **Equipo** (vista JE, `equipoPanel`) — `showEquipoDash(type, jeId)`, solo los técnicos de ese jefe de equipo.
- **Empresa** (vista coordinador, `jrPanel` — usuarios `GD5381`/`JN4767`/`CM9651`/`JR9426`/`BLAS.ALVAREZ`/`BA8006`) — `showJRDash(type)`, todos los técnicos de la empresa (incluye los marcados "No cuentan").

Ambos alcances comparten el mismo render (`_renderDashRanking(type, tecs)`) para no duplicar la lógica de tabla/ranking. Cada dashboard de ranking tiene su **propio selector de mes** (`mesSelectorDash`, muestra el mes actual primero) que permite ver el ranking de un mes histórico sin salir de la pantalla — reutiliza `cambiarMes()` y vuelve a abrir el mismo ranking (`cambiarMesDash()`). El botón "← Volver" regresa al panel correcto (`equipoPanel` o `jrPanel`) según de dónde se abrió, vía la variable `_dashBackPanel`.

**Desde el ranking de RM y Cumplimiento**, el nombre de cada técnico es clickeable y abre su dashboard individual (`showRMDashFromEquipoDash` / `showCumDashFromEquipoDash`) — **solo si el técnico tiene datos** en `RM_DATA`/`CUM_DATA` respectivamente (algunos técnicos aparecen en el ranking general pero no en el Excel detallado de RM/Cumplimiento de ese mes; en ese caso el nombre no es clickeable, para evitar un callejón sin salida).

### Dashboard individual de RM — motivos y causa raíz con detalle de mantenimientos

El dashboard individual (`_openRMDash`) tiene 3 secciones:
- **Top motivos de todas las visitas** — no clickeable, solo informativo
- **Motivo de las visitas repetidas (RM)** — clickeable, despliega los números de mantenimiento (`nMant`, columna E del sheet)
- **Causa raíz del post-mantenimiento** — clickeable, despliega los números de mantenimiento (`nMantPost`, columna M del sheet — **distinta** de la anterior)

Al hacer click en el nombre de un motivo/razón se despliegan chips con los números de mantenimiento, **deduplicados** y con texto seleccionable/copiable. El click está restringido solo al texto del nombre (no a toda la fila), para poder seleccionar el número sin que la lista se colapse accidentalmente.

### Dashboard individual de Cumplimiento — razones con detalle de mantenimientos

Mismo patrón: "Razones de incumplimiento" es clickeable y despliega los `nmant` asociados a cada razón, deduplicados.

### Vacaciones con desglose mensual

Tres indicadores: Disfrutados, Restantes, As. Propios + desglose mensual con píldoras de colores (azul = vacaciones, naranja = asuntos propios).

### Confirmaciones SMS/WhatsApp (JEs)

Pestaña **📲 Confirmaciones** que abre `confirmaciones-sms` (ver sección dedicada abajo — subproyecto separado desplegado en Render, no es `localhost`).

### Dashboard "Uso de la app" (coordinadores)

Pestaña **Uso de la app** con conteo de conexiones y último acceso por matrícula.

---

## confirmaciones-sms (subproyecto)

App Node/Express **separada** del portal principal, en la subcarpeta `confirmaciones-sms/`, desplegada en Render: **https://tecnicos-aurum.onrender.com**. Gestiona la confirmación de citas por SMS (y WhatsApp para envío en lote desde el panel admin). El botón "📂 Cargar Excel" / "📲 Confirmaciones" del portal principal simplemente abre esta URL con `?je=<matricula>`.

### Flujo

1. Se sube un Excel de actividades/citas (`POST /upload`, campo `excel` + `matricula`) — matrículas en `UPLOADERS_PERMITIDOS` (`262876`, `CM9651`, `GD5381`, `EQ5303`) suben todo sin filtrar; un JE (matrícula en `JERARQUIA`) sube solo su equipo; cualquier otra matrícula sube solo lo suyo.
2. Cada fila nueva queda en estado `pendiente` (filas ya existentes con la misma clave — nº de mantenimiento, o cliente+fecha+timeslot+técnico si no hay nº — se ignoran: **volver a subir el mismo Excel no duplica**).
3. Nadie recibe el SMS automáticamente al subir — un humano tiene que entrar y mandar:
   - **`je.html`** (coordinador, matrícula+DNI de JE) — ve las citas de todo su equipo agrupadas por técnico. Puede enviar una por una (📱 Enviar SMS) o **en lote**: checkbox por cita + "☑️ Seleccionar todos los pendientes" + barra inferior "📤 Enviar", que abre los SMS nativos uno detrás de otro (detecta cuándo el usuario vuelve de la app de mensajes — `visibilitychange` — y abre el siguiente automáticamente).
   - **`tecnico.html`** (técnico individual, matrícula+DNI propios) — mismo patrón, solo sus propias citas, sin envío en lote.
   - Panel admin (`index.html` de este subproyecto, sin login) — conectado a un número de WhatsApp real vía QR, con envío en lote automatizado (`client.sendMessage`) y control de tope diario.
4. Mensaje SMS (igual en `je.html` y `tecnico.html`, sin acentos para que cuente como SMS simple):
   > `Hola {nombre}! Le recordamos su cita de {tipo} el {fecha}, tramo {timeslot}h. Nos confirma si le viene bien? Responda SI o NO. Gracias, Verisure`
5. Las citas sin enviar/confirmar se limpian automáticamente a **medianoche** (`programarLimpiezaMedianoche()`), junto con el contador diario de envíos.

### Persistencia en Google Sheets (evita perder citas en cada despliegue de Render)

Render no tiene disco persistente en este servicio — cada `git push` que dispara un redeploy crea un contenedor nuevo, y el archivo local `sesion.json` (con las citas del día) se pierde. Para que sobreviva:

- Hoja de Google **"Citas Confirmaciones SMS - Aurum"** (pestaña `Citas`), con Apps Script desplegado como Aplicación Web (código en `confirmaciones-sms/apps-script-citas.gs`, ejecutar como el dueño de la hoja, acceso "Cualquier usuario").
- `CITAS_SHEET_URL` en `server.js` apunta a ese Apps Script. Endpoints: `?action=cargar` (GET, trae todas las citas), `guardarTodo` (POST, reemplaza todas las citas — se llama automáticamente dentro de `guardarSesion()`, fire-and-forget), `borrarTodo` (POST, limpia todo).
- Al arrancar, `iniciarPersistencia()` intenta cargar desde la Hoja primero; si está vacía o falla, cae al respaldo local (`sesion.json`).
- El Apps Script fuerza formato de texto plano (`setNumberFormat('@')`) en las columnas antes de escribir — si no, Google Sheets convierte matrícula/teléfono en número y la fecha en un objeto `Date`, rompiendo el formato esperado (ej. `31/07/2026` → timestamp ISO).
- **Si se edita `apps-script-citas.gs`**, hay que pegar el cambio en el editor de Apps Script de la Hoja y volver a implementar (Implementar → Gestionar implementaciones → ✏️ → Nueva versión → Implementar) para que el cambio tome efecto en la URL ya desplegada.

### Archivos

```
confirmaciones-sms/
  server.js               ← Express + WebSocket + whatsapp-web.js (opcional, WHATSAPP_ENABLED)
  apps-script-citas.gs    ← Código a pegar en el Apps Script de la Hoja de citas (persistencia)
  public/
    index.html             ← Panel admin (WhatsApp QR, envío en lote)
    je.html                ← Vista de coordinador/JE (matrícula+DNI), envío individual y en lote
    tecnico.html            ← Vista de técnico individual (matrícula+DNI)
```

---

## PWA (Progressive Web App)

| Archivo | Descripción |
|---------|-------------|
| `manifest.json` | Nombre "Aurum", color dorado `#c9a84c`, display standalone |
| `sw.js` | Service Worker Network First, versión `v20260703a` |
| `icon-192.png` / `icon-512.png` | Iconos PWA |
| `favicon.ico` | Favicon 32×32 |

Cada nuevo deployment del Apps Script debe ir acompañado de un bump de versión en `sw.js` para que los usuarios reciban la versión actualizada de `index.html`.

---

## Plan de migración: dejar de depender de "Resumen App Claude"

**Dirección acordada:** eventualmente todos los KPIs se calcularán directo desde los Excel que llegan por correo (Mtos_Finalizados, Cumplimiento, RM) en vez de depender del sheet manual "Resumen App Claude". Mientras tanto, la app **sigue mostrando datos de Resumen App Claude** — este cambio no se ha hecho todavía.

### Fórmula de KPIs validada contra Mtos_Finalizados_Aurum.xlsx

Columnas usadas: A=Nº instalación, B=Nº mantenimiento, C=fecha, D=matrícula, L=Tipo Actividad (ojo: encoding roto por acentos, ej. `Revisiï¿½n`), M=Tipología (A/B).

| KPI | Fórmula |
|---|---|
| **Palito** | Conteo bruto de filas del técnico (sin deduplicar) |
| **Lab** | Nº de fechas distintas (lunes-viernes) donde el técnico tiene ≥1 fila (no es fijo por mes, varía por técnico según vacaciones/ausencias) |
| **NEC** | `Lab × 7` |
| **A+B** | Suma ponderada: tipología A=1, B=2.2, blanco/otro=1 — **deduplicando** cuando se repite instalación+fecha el mismo día (ampliación posterior no cuenta aparte) |
| **Faltantes** | `max(0, NEC − A+B)` |
| **MPal** | `Palito ÷ Lab` |
| **ML-V** | Suma ponderada (dedup) solo de filas lunes-viernes ÷ `Lab` |
| **MA+B** | `A+B ÷ Lab` (ambos, ML-V y MA+B, dividen por Lab — no por días naturales) |

**Tabla de clasificación Tipo Actividad → A/B:** existe una tabla de referencia (ver conversación) para los casos donde la columna M viene mal o el texto de columna L tiene variantes (plurales "Ampliaciones" vs "Ampliación", prefijos "Avería - X" vs "X", etc.) — con alias ya resueltos para las variantes encontradas en los archivos reales.

### Pendiente para completar la migración
- Endpoint(s) que lean directo de los Excel archivados (o del "Historico" cuando aplique) y calculen los KPIs con la fórmula de arriba
- Reemplazar `loadSheets()` / `SHEETS_CSV_URL` en el cliente
- Estadísticas trimestrales/semestrales para coordinador (`GD5381`) — el selector de mes histórico ya está implementado (ver "Dashboards de ranking" arriba)

---

## Archivos del proyecto

```
index.html          ← Toda la app (HTML + CSS + JS)
manifest.json       ← PWA manifest
sw.js               ← Service Worker (Network First, caché por versión)
icon-192.png        ← Icono PWA 192×192
icon-512.png        ← Icono PWA 512×512
favicon.ico         ← Favicon navegador 32×32
CLAUDE.md           ← Instrucciones para Claude Code
README.md           ← Este archivo
confirmaciones-sms/ ← Subproyecto separado (Node/Express, desplegado en Render) — ver sección dedicada arriba
```
