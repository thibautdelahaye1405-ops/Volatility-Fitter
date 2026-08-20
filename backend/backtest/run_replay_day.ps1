# Full-day 15-minute replay campaign for ONE session (V3.8 item 6):
# capture (basket NVDA/AAPL/MSFT + SPY, --step 15 --ladder term) -> scripted
# leave-out scenarios -> merged JSON/HTML report.
#
# MUST RUN IN THE USER'S OWN WINDOW (the standing constraint: tool-managed
# background jobs get killed on this box). Wall-clock expectation: 15-25 min
# PER TICKER-DAY on the REST source (measured 0DTE-campaign request costs;
# names are far cheaper than ETFs), plus the scenario replay (states rebuilt
# per instant; fits dominate). The capture is fully resumable (per-day
# fixtures + per-instant checkpoints) and the scenario parts are per
# (scenario, day) and skipped when present — rerun this script after any
# interruption and it continues where it stopped. Launch detached so harness
# limits cannot kill it (the run_capture_rest.ps1 pattern):
#
#   Start-Process powershell -WindowStyle Hidden -ArgumentList
#     '-NoProfile','-ExecutionPolicy','Bypass','-File',
#     'backend\backtest\run_replay_day.ps1','-Day','2026-08-19'
#
# Usage (any cwd):
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_replay_day.ps1 -Day 2026-08-19
#   ... -Source flat            # flat-file capture instead of REST (hours/day)
#   ... -Db backtest\results\replay_day.sqlite -Step 15 -Ladder term
#
# Afterwards the artifact lives under backend\backtest\results\scenarios\
# (scenario_report.html / scenario_report.json).

# NB: no [Parameter()]/[CmdletBinding()] attributes here — they would make this
# an advanced script, whose common -Debug parameter carries the alias "db" and
# collides with -Db (the launcher-convention name, cf. run_dynamic_intraday.ps1).
param(
    [string]$Day,
    [string]$Db = 'backtest\results\replay_day.sqlite',
    [string]$Tickers = 'SPY,NVDA,AAPL,MSFT',
    [int]$Step = 15,
    [string]$Ladder = 'term',
    [string]$Source = 'rest'
)

$ErrorActionPreference = 'Stop'
if (-not $Day) { throw 'Missing -Day (session date, e.g. -Day 2026-08-19)' }
if ($Source -notin @('rest', 'flat')) { throw "-Source must be 'rest' or 'flat' (got '$Source')" }
$backend = Split-Path $PSScriptRoot
$repo = Split-Path $backend
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONUNBUFFERED = '1'
# Data credentials (Massive REST key / flat-file S3 creds).
. (Join-Path $repo 'restart.local.ps1')
# `-m backtest.<mod>` resolves the package from the working directory.
Push-Location $backend

try {
    $mod = if ($Source -eq 'rest') { 'backtest.capture_intraday_rest' } else { 'backtest.capture_intraday' }
    Write-Host ('=== capture: {0} {1} step={2}min ladder={3} -> {4}' -f $mod, $Tickers, $Step, $Ladder, $Db)
    & $python -m $mod --start $Day --end $Day --tickers $Tickers `
        --step $Step --ladder $Ladder --db $Db
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host '=== scenarios: run (all five shipped cells)'
    & $python -m backtest.scenarios run --db $Db --days $Day
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'scenarios exited nonzero - rerun this script to resume (finished parts skip)'
        exit $LASTEXITCODE
    }

    Write-Host '=== scenarios: report'
    & $python -m backtest.scenarios report
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host 'Done. Artifact: backend\backtest\results\scenarios\scenario_report.html'
}
finally {
    Pop-Location
}
