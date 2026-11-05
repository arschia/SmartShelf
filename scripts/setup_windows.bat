@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   SMARTSHELF - Windows Setup Script
echo ========================================================

cd /d "%~dp0\.."

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.12 or newer.
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment (.venv)...
if not exist ".venv" (
    python -m venv .venv
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

echo [2/3] Activating virtual environment and upgrading pip...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo [3/3] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt

echo.
echo ========================================================
echo   Setup completed successfully!
echo   Run 'scripts\run.bat' to start the server.
echo ========================================================
