$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $root 'scripts\run_backend_task.ps1'
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) { throw 'Run install_windows_local.ps1 first.' }
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $root
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'SmartShelf Backend' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Starts the local SmartShelf FastAPI backend after this Windows user signs in.' -Force | Out-Null
Write-Host 'Autostart registered. SmartShelf starts when this Windows account signs in.' -ForegroundColor Green
Write-Host 'Keep this account signed in; the backend task runs under this account.'
