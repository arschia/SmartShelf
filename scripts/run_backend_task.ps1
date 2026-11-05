# Hidden task runner. Output is kept locally for troubleshooting.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root 'logs\backend.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3
        if ($health.status -eq 'ok') { exit 0 }
    } catch {}
    Add-Content -Path $log -Value "[$(Get-Date -Format s)] Port 8000 is occupied but SmartShelf health check failed; refusing a duplicate start."
    exit 2
}
& $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws websockets-sansio --no-proxy-headers *>> $log
# Scheduled Task recovery depends on receiving the Python process exit code.
exit $LASTEXITCODE
