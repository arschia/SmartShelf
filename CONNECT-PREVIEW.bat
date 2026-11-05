@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this patch into the installed SmartShelf folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\connect_vercel_preview.py
set "shelf_preview_exit=%errorlevel%"
pause
exit /b %shelf_preview_exit%
