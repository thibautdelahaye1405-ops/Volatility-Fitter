# record.ps1 — run the Massive TICK RECORDER detached (Docs\massive_streaming.md, "Recorder")
#
# Usage:   .\record.ps1                                  # SPY,NVDA, every listed expiry, frames into backend\data\volfit.sqlite
#          .\record.ps1 -Tickers SPY,QQQ -Expiries monthly
#          .\record.ps1 -Expiries 2026-10-16,2026-11-20   # an explicit ladder
#          .\record.ps1 -NoStore                          # ticks only, no frames
#          .\record.ps1 -Status                           # the recorder's meta (pid, heartbeat, acked, frames)
#          .\record.ps1 -Stop                             # a clean stop (the pid in meta as the fallback)
#
# The recorder (backend\volfit\data\tick_recorder.py) owns the ONE Massive
# websocket the key allows: it records the live book into a daily tick file
# under -Out (ticks_<YYYY-MM-DD>.sqlite) and, every -FrameMinutes, saves each
# ticker's chain into the app's VolStore (-Store) as an as-of frame. Start the
# app with $env:VOLFIT_MASSIVE_BOOK = "recorder:<the -Out directory>" so the
# API reads that book and opens NO socket of its own (restart.ps1 passes the
# env through; put the line in restart.local.ps1 to make it stick).
#
# Logs: backend\data\recorder.out.log / recorder.err.log.

param(
    [string]$Tickers = "SPY,NVDA",
    [string]$Expiries = "all",                  # all | monthly | weekly | csv of ISO dates
    [string]$Store = "backend\data\volfit.sqlite",
    [string]$Out = "backend\data\ticks",
    [int]$FrameMinutes = 1,
    [double]$Interval = 1.0,
    [switch]$NoStore,                           # ticks only, no frames
    [switch]$NoRest,                            # no per-minute REST memory (wings unquoted)
    [switch]$Status,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

# Local secrets / env (gitignored): the Massive key + cluster override.
$localEnv = Join-Path $repo "restart.local.ps1"
if (Test-Path $localEnv) { . $localEnv }

$python = Join-Path $repo ".venv\Scripts\python.exe"
$outDir = if ([System.IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $repo $Out }

if ($Stop) {
    & $python -m volfit.data.tick_recorder stop --out $outDir
    exit $LASTEXITCODE
}
if ($Status) {
    & $python -m volfit.data.tick_recorder status --out $outDir
    exit $LASTEXITCODE
}

$argList = @("-m", "volfit.data.tick_recorder", "record",
    "--tickers", $Tickers, "--expiries", $Expiries, "--out", $outDir,
    "--frame-minutes", $FrameMinutes, "--interval", $Interval)
if (-not $NoStore) {
    $storePath = if ([System.IO.Path]::IsPathRooted($Store)) { $Store } else { Join-Path $repo $Store }
    $argList += @("--store", $storePath)
}
if ($NoRest) { $argList += "--no-rest" }

$logDir = Join-Path $repo "backend\data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "recorder.out.log"
$errLog = Join-Path $logDir "recorder.err.log"
$proc = Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory (Join-Path $repo "backend") `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Write-Host "Recorder started (pid $($proc.Id)): $Tickers / $Expiries -> $outDir" -ForegroundColor Green
Write-Host "  frames -> $(if ($NoStore) { 'none (-NoStore)' } else { $storePath }) every $FrameMinutes min; logs $errLog"
Write-Host "  app side: `$env:VOLFIT_MASSIVE_BOOK = 'recorder:$outDir' then .\restart.ps1 -Massive"
exit 0
