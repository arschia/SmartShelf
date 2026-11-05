param([string]$PublicUrl = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$tailscale = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if (-not $tailscale) { $tailscale = Get-Command tailscale -ErrorAction SilentlyContinue }
if (-not $tailscale) {
    $candidates = @(
        "$env:ProgramFiles\Tailscale IPN\tailscale.exe",
        "$env:ProgramFiles\Tailscale\tailscale.exe",
        "${env:ProgramFiles(x86)}\Tailscale IPN\tailscale.exe"
    )
    foreach ($candidate in $candidates) { if (Test-Path $candidate) { $tailscale = Get-Item $candidate; break } }
}
if (-not $tailscale) { throw 'Tailscale CLI not found. Install Tailscale for Windows from https://tailscale.com/download/windows/ and sign in first.' }
$ts = if ($tailscale.Source) { $tailscale.Source } elseif ($tailscale.FullName) { $tailscale.FullName } else { 'tailscale' }

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 4
} catch { throw 'Local backend is not responding. Run scripts\start_backend.ps1 first and keep it running.' }
if ($health.status -ne 'ok') { throw 'Local backend health check did not return status=ok.' }

Write-Host 'Checking Tailscale login...' -ForegroundColor Cyan
$statusBefore = (& $ts status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $statusBefore -match '(?i)logged out|needs login|not logged in') {
    Write-Host 'A Tailscale sign-in is required. Complete the browser sign-in, then rerun this script.' -ForegroundColor Yellow
    & $ts up
    if ($LASTEXITCODE -ne 0) { throw 'Tailscale sign-in/setup did not complete.' }
}

Write-Host 'Enabling persistent public HTTPS Funnel for local port 8000...' -ForegroundColor Cyan
Write-Host 'If Tailscale prints an approval URL, open that exact URL in your browser and approve Funnel.' -ForegroundColor Yellow
Write-Host 'Approval is on the Tailscale website; this script does not wait for a Gmail message.' -ForegroundColor Yellow
# Keep native stdout/stderr attached to the console. Capturing this command with
# Out-String hides its approval link while it waits for the user to approve it.
& $ts funnel --bg 8000
if ($LASTEXITCODE -ne 0) {
    throw 'Funnel could not be enabled. Follow any Tailscale browser consent prompt, check Funnel is enabled in the tailnet policy, then rerun.'
}
$statusOutput = (& $ts funnel status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'Could not read Funnel status. Run tailscale funnel status directly to inspect the result.' }
Write-Host $statusOutput

if (-not $PublicUrl) {
    $match = [regex]::Match($statusOutput, 'https://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.ts\.net')
    if ($match.Success) { $PublicUrl = $match.Value }
}
if (-not $PublicUrl) { $PublicUrl = Read-Host 'Copy the HTTPS Funnel URL shown above (https://...ts.net)' }
$PublicUrl = $PublicUrl.Trim().TrimEnd('/')
if ($PublicUrl -notmatch '^https://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.ts\.net$') {
    throw 'Invalid URL. Enter the exact HTTPS Funnel origin ending in .ts.net, with no path or query.'
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
& $venvPython scripts\set_public_backend.py $PublicUrl
if ($LASTEXITCODE -ne 0) { throw 'Could not write the Funnel URL into .env and frontend/config.js.' }

Write-Host ''
Write-Host 'FUNNEL CONFIGURED.' -ForegroundColor Green
Write-Host "Backend URL: $PublicUrl"
Write-Host 'The URL is now in .env and frontend/config.js in this local project copy.'
Write-Host 'IMPORTANT: stop the current backend with Ctrl+C and start it again so the new PUBLIC_BASE_URL is loaded.' -ForegroundColor Yellow
Write-Host 'The frontend/config.js change must still be deployed to the existing Vercel project, or entered in each browser through Server Settings.'
Write-Host 'STORE_OPEN remains false.' -ForegroundColor Yellow
