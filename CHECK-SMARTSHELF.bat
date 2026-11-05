@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install SmartShelf first. If installation failed, send a screenshot of the error.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\diagnose_windows.py
pause
