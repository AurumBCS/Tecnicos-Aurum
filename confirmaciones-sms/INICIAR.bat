@echo off
:: Reabrir en cmd /k para que la ventana nunca se cierre sola
if not "%1"=="keepopen" (
    cmd /k "%~f0" keepopen
    exit
)
title Verisure - Confirmaciones WhatsApp
echo.
echo  ==========================================
echo   Verisure - Portal + Confirmaciones WA
echo  ==========================================
echo.

:: Verificar Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Node.js no esta instalado.
    echo  Ejecuta INSTALAR.bat primero.
    echo.
    pause & exit /b 1
)

:: Instalar dependencias si no estan
if not exist "%~dp0node_modules\express" (
    echo  [!] Instalando dependencias por primera vez...
    cd /d "%~dp0"
    npm install
    if %errorlevel% neq 0 (
        echo  [ERROR] Fallo la instalacion de dependencias.
        pause & exit /b 1
    )
    echo.
)

:: Cerrar instancia anterior en el puerto 3000
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":3000 "') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

cd /d "%~dp0"

:: Abrir el navegador en segundo plano cuando el servidor responda
start /b powershell -WindowStyle Hidden -Command "for($i=0;$i-lt40;$i++){Start-Sleep 1;try{Invoke-WebRequest http://localhost:3000/status -UseBasicParsing -TimeoutSec 1 | Out-Null;Start-Process 'http://localhost:3000/portal/';break}catch{}}"

echo  Servidor iniciando...
echo  El navegador se abrira automaticamente en unos segundos.
echo.
echo  NO cierres esta ventana mientras uses la aplicacion.
echo  Para salir pulsa Ctrl+C
echo.
echo  ==========================================
echo.

:: Arrancar servidor en esta misma ventana — los errores son visibles aqui
node server.js

echo.
echo  El servidor se ha cerrado.
pause
