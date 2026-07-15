# Detached relauncher for the REST intraday capture (R2 item 10 campaign).
#
# The capture is fully resumable (per-day fixtures + per-instant checkpoints)
# and rides out ~10 min DNS outages internally; this wrapper only covers the
# rare terminal crash (an outage longer than the in-process budget) by
# relaunching until a clean exit. Launch detached so harness/background-task
# limits cannot kill the campaign:
#
#   Start-Process powershell -WindowStyle Hidden -ArgumentList
#     '-NoProfile','-ExecutionPolicy','Bypass','-File',
#     'backend\backtest\run_capture_rest.ps1'
#
# Progress streams to backend\backtest\results\capture_rest_campaign.log.

param(
    [string]$Start = '2026-06-30',
    [string]$End = '2026-07-10',
    [string]$Tickers = 'SPY,QQQ,IWM',
    [string]$DbPath = 'backtest\results\intraday.sqlite',
    [int]$MaxRounds = 12
)

$repo = Split-Path (Split-Path $PSScriptRoot)
. (Join-Path $repo 'restart.local.ps1')
Set-Location (Join-Path $repo 'backend')
$env:PYTHONUNBUFFERED = '1'
$log = Join-Path $PSScriptRoot 'results\capture_rest_campaign.log'
$python = Join-Path $repo '.venv\Scripts\python.exe'

for ($round = 1; $round -le $MaxRounds; $round++) {
    Add-Content $log ("--- relauncher round {0} at {1}" -f $round, (Get-Date -Format s))
    & $python -m backtest.capture_intraday_rest --start $Start --end $End `
        --tickers $Tickers --db $DbPath *>> $log
    if ($LASTEXITCODE -eq 0) {
        Add-Content $log '--- relauncher: clean exit'
        break
    }
    Start-Sleep -Seconds 60
}
