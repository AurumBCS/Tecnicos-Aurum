# Automatizaciones diarias · Consola de despacho (OFS)

Tres scripts que automatizan tareas diarias contra la consola de despacho
de Oracle Field Service (`https://securitasdirect.etadirect.com/`), usando
**dos usuarios distintos** de esa consola:

- **Usuario "mantenimientos"** (`ETADIRECT_USER` / `ETADIRECT_PASS`): el que
  ya tenías configurado. Exporta el Excel de mantenimientos y el de ruta.
- **Usuario "capturas"** (`ETADIRECT_USER_CAPTURAS` / `ETADIRECT_PASS_CAPTURAS`):
  uno distinto, solo para tomar las capturas de pantalla.

## Modo de ejecución: PC local (Task Scheduler) vs GitHub Actions (en prueba)

Estos mismos 3 scripts se pueden correr de dos formas:

1. **PC local con el Programador de tareas de Windows** — la forma original, documentada más abajo. Depende de que la PC esté encendida (o se active con temporizador) a la hora programada.
2. **GitHub Actions** (`.github/workflows/ofs-automation.yml`, en la raíz del repo) — corre en la nube, sin depender de esta PC. **En fase de prueba**: no se sabe todavía si la consola de OFS bloquea el tráfico desde las IPs de GitHub Actions (son IPs de centro de datos conocidas, algunos sistemas anti-bot las bloquean por defecto).

### Configurar los Secrets para GitHub Actions

En el repositorio de GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, crea estos 6 (mismos nombres y valores que las variables de entorno locales — nunca se escriben en el código):

- `ETADIRECT_USER`
- `ETADIRECT_PASS`
- `ETADIRECT_USER_CAPTURAS`
- `ETADIRECT_PASS_CAPTURAS`
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`

### Probar manualmente el workflow

1. Pestaña **Actions** del repositorio → workflow **"Automatizacion OFS"** → **"Run workflow"**.
2. Elige qué tarea correr (`manana`, `mediodia` o `tarde`) y dale a **Run workflow**.
3. Cuando termine, revisa los logs de cada paso, y descarga el artefacto **"resultado-N"** (capturas, Excel, `automatizacion.log`) para ver qué pasó — especialmente si falla, para confirmar si es el bloqueo de IP u otra cosa.

### Diferencia clave vs la versión local

En GitHub Actions **cada ejecución programada es un entorno nuevo y aislado** — no hay archivo de sesión guardado entre corridas (cada vez hace login completo desde cero, lo cual es más lento pero más simple/seguro que guardar cookies de sesión en el repositorio). Por eso la tarea de la mañana corre `tomar_capturas.py` y `enviar_correo_matutino.py` **en el mismo job, uno después del otro** (no en jobs/horarios separados como en Task Scheduler), para que el segundo script sí encuentre las capturas que dejó el primero.

## Los 3 scripts

1. **`tomar_capturas.py`** (~7:15am, usuario capturas) — entra a la
   consola (este usuario ya ve solo AURUM por defecto, no hace falta
   filtro), hace clic en cada uno de los 9 equipos del panel izquierdo
   (de Ezequiel Pugliese a Jose Luis Osorio) y toma una captura de
   pantalla completa por cada uno, dejándolas guardadas en `capturas/`.
   No envía correo.
2. **`enviar_correo_matutino.py`** (7:30am, usuario mantenimientos) — entra
   a la consola, exporta el Excel de mantenimientos del día
   (`Acciones → Exportar`), junta las capturas que ya dejó guardadas
   `tomar_capturas.py`, y envía todo por correo a
   `mercedes.savarino@aurumbcs.com`.
3. **`descargar_ruta_y_subir.py`** (2pm y 6pm, usuario mantenimientos) —
   entra a la consola, navega a la fecha del día siguiente (saltando
   domingos), descarga el Excel de la ruta (`Acciones → Exportar`), y lo
   sube a la app de confirmaciones
   (`https://tecnicos-aurum.onrender.com/upload`) para que salgan las citas
   a confirmar. Se corre **dos veces al día** (2pm y 6pm) con el mismo
   script sin cambios — el servidor de confirmaciones-sms ya se encarga de
   no reenviar SMS duplicados a citas que ya se subieron antes, así que
   volver a subir el Excel completo cada vez es seguro.

Los tres comparten el login a la consola (`comun_ofs.py`), pero cada
usuario guarda su propia sesión (`sesion_ofs_mantenimientos.json` /
`sesion_ofs_capturas.json`) para no pisarse entre sí.

**Importante:** `tomar_capturas.py` debe correr **antes** que
`enviar_correo_matutino.py` (unos 10-15 minutos de margen), porque este
último busca las capturas del día ya guardadas en disco — si no las
encuentra, avisa con un error claro en vez de enviar un correo incompleto.

## 1. Instalar dependencias

```powershell
cd "C:\Users\Viatek\Desktop\Automatizacion-Plantilla"
pip install -r requirements.txt
playwright install chromium
```

## 2. Configurar credenciales (variables de entorno)

**Nunca se escriben contraseñas dentro de los scripts.** Configúralas como
variables de entorno de usuario en Windows:

1. Busca "Editar las variables de entorno del sistema" en el menú de Inicio.
2. Click en "Variables de entorno...".
3. En "Variables de usuario", crea:
   - `ETADIRECT_USER` → usuario de mantenimientos (el que ya tenías)
   - `ETADIRECT_PASS` → su contraseña
   - `ETADIRECT_USER_CAPTURAS` → el otro usuario, solo para capturas
   - `ETADIRECT_PASS_CAPTURAS` → su contraseña
   - `GMAIL_USER` → `gustavo.perez@aurumbcs.com`
   - `GMAIL_APP_PASSWORD` → una **contraseña de aplicación** de Gmail (no tu contraseña normal — ver paso 3)

## 3. Generar una contraseña de aplicación de Gmail

1. Entra a https://myaccount.google.com/security con la cuenta `gustavo.perez@aurumbcs.com`.
2. Activa la verificación en dos pasos si no la tienes activada.
3. Busca "Contraseñas de aplicaciones" (App passwords).
4. Genera una nueva, ponle un nombre como "Automatizacion Plantilla", y copia el código de 16 caracteres.
5. Usa ese código como valor de `GMAIL_APP_PASSWORD`.

## 4. Probar manualmente

```powershell
python tomar_capturas.py
python enviar_correo_matutino.py
python descargar_ruta_y_subir.py
```

La primera vez conviene correr cada script con `headless=False` (cambia la
línea `browser = p.chromium.launch(headless=True)` en el script
correspondiente) para ver visualmente si funciona bien.

## 5. Verificar selectores (importante antes de dejarlo en automático)

**Los 3 scripts ya estan verificados contra la consola real y funcionando
de punta a punta:**
- `tomar_capturas.py` — login del usuario de capturas, clic en los 9
  equipos, capturas guardadas correctamente.
- `enviar_correo_matutino.py` — login del usuario de mantenimientos,
  filtro Vista→Empresa Contratista→AURUM, Acciones→Exportar, correo
  recibido con las 9 capturas + Excel.
- `descargar_ruta_y_subir.py` — filtro AURUM, navegación al día
  siguiente, Acciones→Exportar de la ruta, y subida real confirmada
  (respuesta 200 del servidor de confirmaciones).

## 6. Regla de fecha del script de la ruta

`descargar_ruta_y_subir.py` siempre navega al **día siguiente** a hoy,
excepto que ese día siguiente sea **domingo**, en cuyo caso salta al
**lunes** — usando las flechas de fecha de la consola.

## 7. Programar la ejecución diaria (Task Scheduler)

Crea 4 tareas básicas en el "Programador de tareas" de Windows. Para cada
una: "Iniciar un programa", programa = tu `python.exe`
(`C:\Users\Viatek\AppData\Local\Programs\Python\Python314\python.exe`),
"Iniciar en" = `C:\Users\Viatek\Desktop\Automatizacion-Plantilla`, y en la
pestaña "General" marca "Ejecutar tanto si el usuario inició sesión como
si no".

| Tarea | Hora | Argumentos |
|---|---|---|
| Capturas plantilla OFS | 7:15am | `tomar_capturas.py` |
| Correo matutino OFS | 7:30am | `enviar_correo_matutino.py` |
| Ruta OFS mediodia | 2:00pm | `descargar_ruta_y_subir.py` |
| Ruta OFS tarde | 6:00pm | `descargar_ruta_y_subir.py` |

## Archivos que generan los scripts

- `capturas/plantilla_YYYY-MM-DD_N.png` — capturas diarias de la plantilla
  (una por cada tanda de técnicos, N varía según cuántos haya ese día).
- `descargas/mantenimientos_YYYY-MM-DD.xlsx` — Excel de mantenimientos del día.
- `descargas/ruta_YYYY-MM-DD.xlsx` — Excel de la ruta del día siguiente.
- `sesion_ofs_mantenimientos.json` / `sesion_ofs_capturas.json` — sesión
  guardada del navegador (cookies) por usuario. **No compartas estos
  archivos** — permiten entrar a la consola sin contraseña mientras la
  sesión esté activa.
