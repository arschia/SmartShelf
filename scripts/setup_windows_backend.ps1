# Run in PowerShell from the project root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_backend.ps1
# Secrets are generated locally; do not send the .env file to anyone.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw 'Python 3.13 or a compatible version must be installed first.'
}
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
& $python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies installation failed.' }
if (-not (Test-Path '.env')) {
  $template = Get-Content '.env.example' -Raw -Encoding UTF8
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes = New-Object byte[] 32
  $rng.GetBytes($bytes)
  $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
  $rng.GetBytes($bytes)
  $pin = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','A').Replace('/','B').Substring(0,16)
  $template = $template.Replace('change-me-to-a-secure-random-32-byte-hex-string', $secret)
  $template = $template.Replace('change-me-to-a-strong-pin-at-least-8-chars', $pin)
  [System.IO.File]::WriteAllText((Join-Path $root '.env'), $template, [System.Text.UTF8Encoding]::new($false))
  Write-Host 'Created private .env with unique secrets. Keep it off public repositories.'
  Write-Host "Your new admin PIN (save it securely): $pin"
} else {
  Write-Host 'Existing .env preserved. Secrets were NOT overwritten.'
}
Write-Host 'Local dependencies ready. Next: configure a persistent HTTPS tunnel and set PUBLIC_BASE_URL in .env.'
Write-Host 'Then run: .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000'
