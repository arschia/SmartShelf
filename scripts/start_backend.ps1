$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'SmartShelf is not installed. Run scripts\install_windows_local.ps1 first.' }
if (-not (Test-Path (Join-Path $root '.env'))) { throw '.env is missing. Run scripts\install_windows_local.ps1 first.' }
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3
        if ($health.status -eq 'ok') { Write-Host 'SmartShelf backend is already running at http://127.0.0.1:8000'; exit 0 }
    } catch {}
    throw 'Port 8000 is already occupied by another process. Do not start a second copy.'
}
Write-Host 'Starting SmartShelf backend on 127.0.0.1:8000. Press Ctrl+C to stop.' -ForegroundColor Cyan
& $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws websockets-sansio --no-proxy-headers
exit $LASTEXITCODE
