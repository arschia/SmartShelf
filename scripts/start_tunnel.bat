@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo مسیر منتخب SmartShelf فقط Tailscale Funnel است.
call "%~dp0..\ENABLE-FUNNEL.bat"
