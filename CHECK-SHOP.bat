@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this update inside the installed SmartShelf folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\check_shop_install.py
set "shelf_shop_exit=%errorlevel%"
pause
exit /b %shelf_shop_exit%
