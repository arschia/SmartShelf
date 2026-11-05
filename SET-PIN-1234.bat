@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this patch into the installed SmartShelf folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\set_test_pin_1234.py
set "shelf_pin_exit=%errorlevel%"
pause
exit /b %shelf_pin_exit%
