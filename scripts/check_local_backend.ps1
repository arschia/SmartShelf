$ErrorActionPreference = 'Stop'
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
    if ($health.status -ne 'ok') { throw 'Unexpected health response.' }
    Write-Host '[PASS] Local backend health: HTTP 200 / status=ok' -ForegroundColor Green
} catch { throw "[FAIL] Local backend is unavailable: $($_.Exception.Message)" }
$listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if (-not $listeners) { throw '[FAIL] Port 8000 is not listening.' }
foreach ($listener in $listeners) {
    if ($listener.LocalAddress -notin @('127.0.0.1','::1')) {
        throw "[FAIL] Backend is listening on $($listener.LocalAddress), not loopback. Stop it and use scripts\start_backend.ps1."
    }
}
Write-Host '[PASS] All port 8000 listeners are bound only to loopback.' -ForegroundColor Green
