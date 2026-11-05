# SmartShelf local Windows installation. Run from the extracted project folder.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' SMARTSHELF - WINDOWS LOCAL SERVER INSTALLATION' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan

$pythonArgs = @()
$pythonCommand = $null
$pythonOk = $false

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.14 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = 'py'
        $pythonArgs = @('-3.14')
        $pythonOk = $true
    }
}
if (-not $pythonOk -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $v = (& python --version 2>&1 | Out-String).Trim()
    if ($v -match 'Python 3\.14\.') {
        $pythonCommand = 'python'
        $pythonArgs = @()
        $pythonOk = $true
    }
}

if (-not $pythonOk) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'Python 3.14 was not found. Installing Python 3.14 using winget...' -ForegroundColor Yellow
        winget install --id Python.Python.3.14 --exact --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation did not complete. Install Python 3.14 from https://www.python.org/downloads/windows/ and rerun this script.' }
        # Refresh common PATH locations for this PowerShell process.
        $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.14 --version *> $null
            if ($LASTEXITCODE -eq 0) { $pythonCommand = 'py'; $pythonArgs = @('-3.14'); $pythonOk = $true }
        }
        if (-not $pythonOk -and (Get-Command python -ErrorAction SilentlyContinue)) {
            $v = (& python --version 2>&1 | Out-String).Trim()
            if ($v -match 'Python 3\.14\.') { $pythonCommand = 'python'; $pythonArgs = @(); $pythonOk = $true }
        }
    }
}
if (-not $pythonOk) {
    throw 'Python 3.14 is required. Install it from https://www.python.org/downloads/windows/ (include the Python Launcher), then rerun this script.'
}

Write-Host '[1/5] Creating persistent data folders...' -ForegroundColor Green
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data\uploads'), (Join-Path $root 'logs'), (Join-Path $root 'backups') | Out-Null

Write-Host '[2/5] Creating Python virtual environment...' -ForegroundColor Green
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    & $pythonCommand @pythonArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
}
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
& $venvPython -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv must use standard 64-bit Python 3.14. Rename .venv and rerun installation; leave .env and data intact.' }

Write-Host '[3/5] Installing pinned Python dependencies (this may take several minutes)...' -ForegroundColor Green
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check internet access and rerun.' }

Write-Host '[4/5] Creating local production configuration and unique credentials...' -ForegroundColor Green
& $venvPython scripts\prepare_windows_env.py
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare .env.' }

Write-Host '[5/5] Checking Python modules and compiling backend...' -ForegroundColor Green
& $venvPython -c "import fastapi, uvicorn, sqlalchemy, cv2, numpy, onnxruntime, zxingcpp, websockets; print('All runtime modules, including WebSocket transport, imported successfully.')"
if ($LASTEXITCODE -ne 0) { throw 'One or more runtime modules failed to import.' }
& $venvPython -m compileall -q backend
if ($LASTEXITCODE -ne 0) { throw 'Backend compile check failed.' }

Write-Host ''
Write-Host 'INSTALLATION READY.' -ForegroundColor Green
Write-Host 'Next: install/sign in to Tailscale, start the backend, then enable Funnel.'
Write-Host 'Backend will bind ONLY to 127.0.0.1:8000; do not open port 8000 on the router/firewall.'
Write-Host 'The store remains closed (STORE_OPEN=false).' -ForegroundColor Yellow
