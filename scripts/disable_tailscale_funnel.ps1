$ErrorActionPreference = 'Stop'
$ts = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if (-not $ts) { $ts = Get-Command tailscale -ErrorAction SilentlyContinue }
if (-not $ts) { throw 'Tailscale CLI not found.' }
$exe = if ($ts.Source) { $ts.Source } else { 'tailscale' }
& $exe funnel 8000 off
if ($LASTEXITCODE -ne 0) { throw 'Could not disable Funnel.' }
Write-Host 'Public Funnel access disabled. Local SmartShelf data was not changed.' -ForegroundColor Green
