@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this update into your installed SmartShelf folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\check_bottle_model.py
set "shelf_bottle_exit=%errorlevel%"
pause
exit /b %shelf_bottle_exit%
