param([Parameter(Mandatory=$true)][ValidateSet('Funnel','Autostart')][string]$Step)
$ErrorActionPreference = 'Stop'
$code = 0
try {
    if ($Step -eq 'Funnel') { & (Join-Path $PSScriptRoot 'enable_tailscale_funnel.ps1') }
    else { & (Join-Path $PSScriptRoot 'register_autostart.ps1') }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $code = 1
}
Read-Host 'Press Enter to close this step' | Out-Null
exit $code
