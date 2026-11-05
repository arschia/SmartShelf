@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   Starting SMARTSHELF Local Server
echo ========================================================

cd /d "%~dp0\.."

if exist ".venv\Scripts\activate.bat" (
    echo Activating .venv...
    call .venv\Scripts\activate.bat
)

set HOST=0.0.0.0
set PORT=8000
set USE_SSL=false
set SSL_CERT_FILE=certs\cert.pem
set SSL_KEY_FILE=certs\key.pem

if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        set "key=%%a"
        set "val=%%b"
        if "!key!"=="HOST" set HOST=!val!
        if "!key!"=="PORT" set PORT=!val!
        if "!key!"=="USE_SSL" set USE_SSL=!val!
        if "!key!"=="SSL_CERT_FILE" set SSL_CERT_FILE=!val!
        if "!key!"=="SSL_KEY_FILE" set SSL_KEY_FILE=!val!
    )
)

set PROTO=http
set SSL_ARGS=

if /i "%USE_SSL%"=="true" (
    if exist "%SSL_CERT_FILE%" (
        set PROTO=https
        set SSL_ARGS=--ssl-certfile %SSL_CERT_FILE% --ssl-keyfile %SSL_KEY_FILE%
        echo [INFO] SSL Enabled: Using certificates %SSL_CERT_FILE%
    ) else (
        echo [WARNING] SSL requested but cert file not found (%SSL_CERT_FILE%).
        echo Run 'scripts\make_cert.bat' first to generate certificates. Falling back to HTTP.
    )
)

echo.
echo ========================================================
echo   SMARTSHELF Endpoints:
echo   - Laptop (Admin Dashboard): %PROTO%://localhost:%PORT%/admin
echo   - Tablet (Camera Sensor):  %PROTO%://<LAPTOP-IP>:%PORT%/camera
echo   - Phone (Customer):        Scan Entry QR code from Admin Dashboard
echo   - Health Check:            %PROTO%://localhost:%PORT%/api/health
echo ========================================================
echo.

python -m uvicorn backend.app.main:app --host %HOST% --port %PORT% %SSL_ARGS%
