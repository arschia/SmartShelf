@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   SMARTSHELF - Generate Local SSL Certificate
echo ========================================================

cd /d "%~dp0\.."

if not exist "certs" mkdir certs

where mkcert >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [INFO] mkcert found in PATH. Using mkcert to issue trusted certificate...
    mkcert -install
    mkcert -cert-file certs\cert.pem -key-file certs\key.pem localhost 127.0.0.1
    echo [SUCCESS] Trusted certificate generated with mkcert.
) else (
    echo [INFO] mkcert not found. Generating self-signed certificate with Python cryptography...
    python scripts\generate_cert.py
)

echo.
echo ========================================================
echo Certificates are ready in 'certs\' directory.
echo To run server with HTTPS, ensure USE_SSL=true in .env
echo ========================================================
