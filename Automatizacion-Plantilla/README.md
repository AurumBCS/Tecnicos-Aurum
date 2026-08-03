# Automatizaciones diarias · Consola de despacho (OFS)

Tres scripts que automatizan tareas diarias contra la consola de despacho
de Oracle Field Service (`https://securitasdirect.etadirect.com/`), usando
**dos usuarios distintos** de esa consola:

- **Usuario "mantenimientos"** (`ETADIRECT_USER` / `ETADIRECT_PASS`): el que
  ya tenías configurado. Exporta el Excel de mantenimientos y el de ruta.
- **Usuario "capturas"** (`ETADIRECT_USER_CAPTURAS` / `ETADIRECT_PASS_CAPTURAS`):
  uno distinto, solo para tomar las capturas de pantalla.

## Modo de ejecución: GitHub Actions (activo) — PC local queda como respaldo

Estos mismos 3 scripts se pueden correr de dos formas. **Desde el 31/07/2026, GitHub Actions es el sistema activo** — se probaron los 3 (`manana`, `mediodia`, `tarde`) y corrieron sin problema, confirmando que la consola de OFS **no bloquea** el tráfico desde las IPs de GitHub Actions.

1. **GitHub Actions** (`.github/workflows/ofs-automation.yml`, en la raíz del repo) — corre en la nube por horario, sin depender de que ninguna PC esté encendida. **Es el sistema en uso actualmente.** Horarios (hora Madrid), **de lunes a sábado** (domingo no corre nada, no hay ruta ni actividad de técnicos ese día): **6:03am** (capturas + correo — adelantado desde 7:03am para dar margen al retraso típico de GitHub y que llegue como tarde ~8:30am), **1:58pm** y **5:53pm** (ruta). Las horas NO son redondas a propósito — GitHub retrasa más los horarios en punto/cuartos exactos por alta demanda (confirmado en vivo: retrasos de 1h45 a 2h20+ son normales en el plan gratuito, sin garantía de hora exacta).
2. **PC local con el Programador de tareas de Windows** — la forma original, documentada más abajo. Las 4 tareas quedaron **deshabilitadas** (no borradas) en el Programador de tareas de esta PC, como respaldo por si hiciera falta volver a activarlas.

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
3. Cuando termine, revisa los logs de cada paso, y descarga el artefacto **"resultado-N"** (capturas, Excel, `automatizacion.log`) si falla, para diagnosticar qué pasó.

### Diferencia clave vs la versión local

En GitHub Actions **cada ejecución programada es un entorno nuevo y aislado** — no hay archivo de sesión guardado entre corridas (cada vez hace login completo desde cero, lo cual es más lento pero más simple/seguro que guardar cookies de sesión en el repositorio). Por eso la tarea de la mañana corre `tomar_capturas.py` y `enviar_correo_matutino.py` **en el mismo job, uno después del otro** (no en jobs/horarios separados como en Task Scheduler), para que el segundo script sí encuentre las capturas que dejó el primero.

## Migración a AWS Lambda + EventBridge Scheduler (en progreso)

**Por qué:** el plan gratuito de GitHub Actions no garantiza hora exacta para
triggers `schedule:` — retrasos de 1h45 a 2h20+ son normales, y no se
arregla pagando GitHub Pro/Team. AWS Lambda + EventBridge Scheduler son
**gratis para siempre** (no solo los 6 meses de crédito nuevo-cliente) para
este volumen de uso, y EventBridge Scheduler sí ejecuta a la hora exacta.
El código ya está listo en este repo:

- `lambda_handler.py` — punto de entrada; recibe `{"tarea": "manana"}` /
  `{"tarea": "mediodia"}` / `{"tarea": "tarde"}` y llama a los mismos
  `main()` de siempre. `"manana"` corre `tomar_capturas` + `enviar_correo_matutino`
  **en la misma invocación** (comparten el `/tmp` de esa ejecución).
- `Dockerfile` — imagen de contenedor para Lambda (Playwright + Chromium ya
  vienen incluidos en la imagen base).
- `comun_ofs.py` — ahora detecta si corre dentro de Lambda
  (`AWS_LAMBDA_FUNCTION_NAME`) y usa `/tmp` en vez de la carpeta del script
  (en Lambda todo excepto `/tmp` es de solo lectura).
- `.github/workflows/deploy-lambda-ofs.yml` — construye la imagen y
  actualiza la función Lambda automáticamente en cada push a
  `Automatizacion-Plantilla/`. Usa un rol de AWS vía OIDC, **nunca** un
  Access Key guardado en GitHub.

Lo que falta es **crear los recursos en la consola de AWS** (esto lo tienes
que hacer tú — nunca con tus credenciales de AWS pasando por este chat).
Región: **eu-south-2** (España, Aragón). Sigue estos pasos en orden.

### Paso 1 — Crear el repositorio en ECR

Consola de AWS → busca **"ECR"** (Elastic Container Registry) → asegúrate
que la región arriba a la derecha sea **eu-south-2** → **Create repository**:

- Visibility: **Private**
- Repository name: `aurum-ofs-automatizacion`
- Deja el resto por defecto → **Create**

### Paso 2 — Permitir que GitHub Actions despliegue solo (OIDC, sin Access Keys)

**2a. Proveedor de identidad OIDC** (una sola vez por cuenta de AWS) — IAM →
**Identity providers** → si ya existe uno con URL
`token.actions.githubusercontent.com`, sáltate este paso. Si no:
**Add provider** → OpenID Connect → Provider URL:
`https://token.actions.githubusercontent.com` → Audience: `sts.amazonaws.com`
→ **Add provider**.

**2b. Rol IAM que GitHub Actions puede asumir** — IAM → **Roles** →
**Create role** → **Web identity** → Identity provider: el que acabas de
crear → Audience: `sts.amazonaws.com` → GitHub organization: `AurumBCS` →
GitHub repository: `Tecnicos-Aurum` → **Next**. En permisos, **Create
policy** (pestaña JSON) y pega esto (ya con tu ID de cuenta):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:eu-south-2:289076681164:repository/aurum-ofs-automatizacion"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"],
      "Resource": "arn:aws:lambda:eu-south-2:289076681164:function:aurum-ofs-automatizacion"
    }
  ]
}
```

Nómbrala `deploy-ofs-lambda` y adjúntala al rol. Nombra el rol
`github-actions-deploy-ofs-lambda` → **Create role**.

Por seguridad extra, entra al rol recién creado → pestaña **Trust
relationships** → **Edit trust policy** y cambia la condición
`"...:sub"` para que sea exactamente:
`"repo:AurumBCS/Tecnicos-Aurum:ref:refs/heads/main"` (así solo pushes a
`main` de ese repo pueden usarlo, no cualquier PR).

**2c. Copiar el Role ARN** (arriba en la página del rol, algo como
`arn:aws:iam::289076681164:role/github-actions-deploy-ofs-lambda`) y
crear el secret `AWS_ROLE_ARN` en GitHub → **Settings** → **Secrets and
variables** → **Actions** con ese valor.

### Paso 3 — Construir y subir la primera imagen (desde GitHub Actions, no CloudShell)

Lambda exige que ya exista **al menos una imagen** en ECR antes de poder
crear la función. AWS CloudShell no tiene disco suficiente para construir
esta imagen (Chromium + Playwright pesan casi 1GB solo la capa base — un
intento real se quedó sin espacio a mitad del `pip install`), así que en
vez de eso usamos el propio workflow de GitHub Actions, que corre en un
runner con mucho más disco:

1. Repositorio en GitHub → pestaña **Actions** → workflow **"Deploy Lambda
   OFS"** en la barra izquierda → **Run workflow** → **Run workflow**
   (rama `main`).
2. Va a construir la imagen y subirla a ECR sin problema. **Va a fallar en
   el último paso** ("Actualizar la función Lambda") con un error de que
   la función no existe todavía — es esperado, la creamos en el Paso 4.
   Lo que importa es que el paso anterior ("Construir y subir la imagen")
   haya quedado en verde.

### Paso 4 — Crear la función Lambda

Consola de AWS → **Lambda** → **Create function**:

- Elige **Container image**
- Function name: `aurum-ofs-automatizacion`
- Container image URI → **Browse images** → repositorio
  `aurum-ofs-automatizacion` → tag `latest`
- **Create function**

Después de creada, en la pestaña **Configuration**:

- **General configuration** → Edit → **Memory** = `2048 MB`, **Timeout** =
  `5 min 0 sec` (el flujo de la mañana hace login en dos consolas distintas
  + 9 capturas + envío de correo; 5 min da margen).
- **Environment variables** → Edit → agrega estas 6 (mismos nombres y
  valores que los GitHub Secrets — **nunca los escribas en un chat
  conmigo**, cópialos directo desde tu gestor de contraseñas o desde donde
  los tengas guardados):
  - `ETADIRECT_USER`, `ETADIRECT_PASS`
  - `ETADIRECT_USER_CAPTURAS`, `ETADIRECT_PASS_CAPTURAS`
  - `GMAIL_USER`, `GMAIL_APP_PASSWORD`
- **Asynchronous invocation** → Edit → **Retry attempts** = **0**.
  Importante: por defecto Lambda reintenta 2 veces una invocación asíncrona
  que falla — un reintento de la tarea de la mañana volvería a **enviar el
  correo a Mercedes de nuevo**, y uno de mediodía/tarde volvería a subir el
  Excel. Dejarlo en 0 evita eso.

Con la función ya creada, vuelve a la pestaña **Actions** de GitHub y
corre **"Deploy Lambda OFS"** una vez más (o simplemente el próximo push
a `main` lo hará solo) — esta vez el paso "Actualizar la función Lambda"
sí debería quedar en verde.

### Paso 5 — Crear los 3 horarios en EventBridge Scheduler

Consola de AWS → **EventBridge** → **Scheduler** → **Create schedule**,
uno por cada fila (región eu-south-2):

| Nombre | Cron (UTC no — usa el campo Timezone) | Timezone | Input |
|---|---|---|---|
| `ofs-manana` | `cron(30 7 ? * MON-SAT *)` | `Europe/Madrid` | `{"tarea": "manana"}` |
| `ofs-mediodia` | `cron(0 14 ? * MON-SAT *)` | `Europe/Madrid` | `{"tarea": "mediodia"}` |
| `ofs-tarde` | `cron(30 17 ? * MON-SAT *)` | `Europe/Madrid` | `{"tarea": "tarde"}` |

`ofs-manana` vuelve a la hora original que pediste (7:30am) en vez del
6:03am al que se había adelantado en GitHub Actions — ese adelanto era
para absorber el retraso típico del plan gratuito (hasta 2h+), algo que
EventBridge Scheduler no tiene: dispara a la hora exacta, con margen de
segundos. Ya no hace falta usar horas "no redondas" como 6:03/1:58/5:53
tampoco, esas eran para esquivar la congestión de GitHub Actions en horas
en punto/cuartos exactos. Si prefieres otro horario, ajusta el cron.

Para cada uno, en el asistente:

- **Schedule pattern**: Recurring schedule → Cron-based → pega el cron de
  la tabla → **Timezone**: `Europe/Madrid` (así el horario de verano/invierno
  se ajusta solo, igual que con GitHub Actions).
- **Target**: AWS Lambda → **Invoke** → función `aurum-ofs-automatizacion`.
- **Input**: pega el JSON de la columna "Input" de la tabla.
- **Retry policy**: **Maximum retry attempts = 0** (mismo motivo que en el
  Paso 4 — evitar correos/subidas duplicadas si algo falla a mitad de
  camino). Deja **Maximum age of event** en su valor por defecto.
- **Flexible time window**: Off (para que dispare exactamente a la hora).
- Crea un rol de ejecución nuevo si te lo pide (permiso para invocar esa
  Lambda específica).

### Paso 6 — Probar antes de confiar en el horario

1. En Lambda → pestaña **Test** → crea un evento de prueba con
   `{"tarea": "manana"}` (o `"mediodia"`/`"tarde"`) → **Test** → revisa
   los logs (CloudWatch Logs, enlazado desde el resultado) para confirmar
   que corrió de punta a punta.
2. Cuando las 3 pruebas manuales funcionen, deja correr los horarios reales
   1-2 días y compara con lo que llega por correo/confirmaciones-sms.
3. **Recién ahí**, para no tener doble ejecución, avísame y quitamos los
   triggers `schedule:` de `.github/workflows/ofs-automation.yml` (dejando
   solo `workflow_dispatch` como respaldo manual).

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
