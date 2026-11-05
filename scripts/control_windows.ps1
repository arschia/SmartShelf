# Each action is explicit; installation never enables public access by itself.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'

function Invoke-ElevatedStep([string]$Step) {
    $runner = Join-Path $PSScriptRoot 'invoke_windows_step.ps1'
    Start-Process -FilePath $ps -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Step $Step"
}

while ($true) {
    Write-Host ''
    Write-Host 'SMARTSHELF - WINDOWS CONTROL v1.1' -ForegroundColor Cyan
    Write-Host '1  Install / update dependencies (preserves data and credentials)'
    Write-Host '2  Open official Tailscale download (install and sign in)'
    Write-Host '3  Start backend in a separate window (keep it open)'
    Write-Host '4  Enable public HTTPS Funnel (Administrator prompt)'
    Write-Host '5  Check connection and create diagnostic report'
    Write-Host '6  Register backend autostart after Windows sign-in'
    Write-Host '7  Back up database and uploaded images'
    Write-Host '8  Open local admin panel'
    Write-Host '0  Exit'
    $choice = Read-Host 'Choose a step'
    if ($choice -eq '0') { break }
    try {
        switch ($choice) {
            '1' { & (Join-Path $PSScriptRoot 'install_windows_local.ps1') }
            '2' { Start-Process 'https://tailscale.com/download/windows/' }
            '3' {
                $runner = Join-Path $PSScriptRoot 'start_backend.ps1'
                Start-Process -FilePath $ps -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$runner`""
            }
            '4' { Invoke-ElevatedStep 'Funnel' }
            '5' {
                if (-not (Test-Path $python)) { throw 'Complete installation first; if installation failed, send a screenshot of that error.' }
                & $python (Join-Path $PSScriptRoot 'diagnose_windows.py')
                if ($LASTEXITCODE -ne 0) { Write-Host 'Some checks need attention. Send logs\diagnostics-latest.json to continue.' -ForegroundColor Yellow }
            }
            '6' { Invoke-ElevatedStep 'Autostart' }
            '7' { & (Join-Path $PSScriptRoot 'backup_shelf.ps1') }
            '8' { Start-Process 'http://127.0.0.1:8000/admin/' }
            default { Write-Host 'Choose one of the numbered steps.' -ForegroundColor Yellow }
        }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-Host 'Send a screenshot of this error. Never send .env or your admin PIN.' -ForegroundColor Yellow
    }
}
