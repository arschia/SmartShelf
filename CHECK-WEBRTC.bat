@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this update INSIDE the installed SmartShelf folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\check_webrtc_install.py
set "shelf_rtc_exit=%errorlevel%"
pause
exit /b %shelf_rtc_exit%
