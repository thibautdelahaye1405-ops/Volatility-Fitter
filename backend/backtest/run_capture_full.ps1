# 25-asset capture, all 3 regimes (the graph cross-asset experiment) — resumable.
#
# REST quotes source (~5 min/trading day for the 17 non-pilot names; pilot
# fixtures are skipped automatically). ~15 h total; relaunch to resume.
# Run from YOUR OWN PowerShell window (session-managed background jobs get
# killed on this box):
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_capture_full.ps1
param(
    [string]$Regimes = "spike_aug2024,high_oct2022,low_jul2023"
)
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"

# Force-set the Massive key from the secrets file (a stale env var can shadow
# the guarded assignment in restart.local.ps1 — the documented gotcha).
$m = Select-String -Path (Join-Path $root "restart.local.ps1") `
    -Pattern '\$env:VOLFIT_MASSIVE_KEY\s*=\s*"([^"]+)"'
if ($m) { $env:VOLFIT_MASSIVE_KEY = $m.Matches[0].Groups[1].Value }
if (-not $env:VOLFIT_MASSIVE_KEY -or $env:VOLFIT_MASSIVE_KEY.Length -lt 16) {
    Write-Host "!!! VOLFIT_MASSIVE_KEY missing/short - check restart.local.ps1"
    exit 1
}

Push-Location (Join-Path $root "backend")
try {
    & $py -m backtest.capture --universe full --regimes $Regimes --source rest
}
finally {
    Pop-Location
}
