@echo off
:: Reabrir en cmd /k para que la ventana nunca se cierre sola
if not "%1"=="keepopen" (
    cmd /k "%~f0" keepopen
    exit
)

title Instalacion - Confirmaciones WhatsApp Verisure
color 0A
echo.
echo  ==========================================
echo   Instalacion - Confirmaciones WhatsApp
echo   Verisure
echo  ==========================================
echo.

:: Verificar si Node.js esta instalado
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Node.js no esta instalado en este ordenador.
    echo.
    echo  Abriendo la pagina de descarga de Node.js...
    echo  Descarga la version "LTS" e instalala con todas las
    echo  opciones por defecto. Cuando termines, vuelve a
    echo  ejecutar este archivo.
    echo.
    start https://nodejs.org/en/download
    echo  Pulsa cualquier tecla para cerrar...
    pause >nul
    exit /b 1
)

echo  [OK] Node.js:
node --version
echo.

:: Limpiar instalaciones previas corruptas
echo  Limpiando instalaciones previas...

if exist "%~dp0node_modules" (
    echo  Borrando node_modules anterior...
    rmdir /s /q "%~dp0node_modules" >nul 2>&1
)

if exist "%USERPROFILE%\.cache\puppeteer" (
    echo  Borrando cache de Chrome descargado...
    rmdir /s /q "%USERPROFILE%\.cache\puppeteer" >nul 2>&1
)

echo  [OK] Limpieza completada.
echo.

:: Instalar paquetes SIN descargar Chrome todavia
echo  Instalando paquetes (sin Chrome, paso 1 de 2)...
echo.
cd /d "%~dp0"
set PUPPETEER_SKIP_DOWNLOAD=true
npm install
set PUPPETEER_SKIP_DOWNLOAD=

if %errorlevel% neq 0 (
    echo.
    echo  ==========================================
    echo  [ERROR] Fallo la instalacion de paquetes.
    echo  ==========================================
    echo  Comprueba tu conexion a internet e intentalo de nuevo.
    echo.
    pause >nul
    exit /b 1
)

echo.
echo  [OK] Paquetes instalados.
echo.

:: Descargar Chrome por separado (paso 2 de 2)
echo  Descargando Chrome interno (paso 2 de 2, ~170 MB)...
echo  Esto puede tardar varios minutos segun la conexion.
echo.
npx puppeteer browsers install chrome

if %errorlevel% neq 0 (
    echo.
    echo  [!] No se pudo descargar Chrome automaticamente.
    echo.
    echo  Si tienes Google Chrome instalado en este PC,
    echo  la aplicacion lo usara y puedes continuar igualmente.
    echo.
    echo  Si no tienes Chrome instalado, instalalo desde:
    echo  https://www.google.com/chrome/
    echo.
) else (
    echo.
    echo  [OK] Chrome listo.
    echo.
)

echo  ==========================================
echo   Instalacion completada!
echo  ==========================================
echo.
echo  Ahora cierra esta ventana y abre INICIAR.bat
echo.
pause >nul
