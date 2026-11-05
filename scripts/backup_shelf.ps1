$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run scripts\install_windows_local.ps1 first.' }
& $python scripts\backup_windows_data.py
if ($LASTEXITCODE -ne 0) { throw 'Backup failed.' }
