@echo off
chcp 65001 >nul
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting Administrator permission...
  powershell.exe -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'powershell.exe' -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File `"%~dp0scripts\enable_tailscale_funnel.ps1`"'"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\enable_tailscale_funnel.ps1"
pause
