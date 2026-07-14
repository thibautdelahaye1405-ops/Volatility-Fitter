# Stall-supervised runner for the intraday 0DTE capture (USER'S-WINDOW job).
#
# Why a supervisor: the flat-file day scan is ONE multi-hour streamed HTTP GET,
# and a half-dead connection can wedge it FOREVER — observed 2026-07-14: CPU
# frozen for >1 h, zero read ops, socket still ESTABLISHED, DuckDB's
# http_timeout never fired (it does not cover a mid-body stall). No in-process
# fix can abort a thread stuck in a socket read, so the robust cure is
# external: watch the child's CPU clock (a streaming gunzip/reduce burns CPU
# continuously; a flat clock means no bytes are arriving), kill the tree, and
# relaunch. The capture is resumable — finished (ticker, day) fixtures are
# skipped — so restarts only re-pay the day that was in flight.
#
# Usage (any cwd; creds auto-loaded from restart.local.ps1 if not in env):
#   .\backend\backtest\run_capture_intraday.ps1 -Start 2026-07-10 -End 2026-07-10 `
#       -Tickers SPY -DbPath backtest\results\intraday.sqlite
#   (-DbPath, not -Db: PowerShell reserves -Db as the alias of common -Debug)
#
# NB a day whose flat file is genuinely missing ("no usable quotes") makes the
# run look failed, so the supervisor will retry up to -MaxRestarts full scans
# before giving up — keep the date window to days you expect to exist.

param(
    [Parameter(Mandatory = $true)][string]$Start,
    [Parameter(Mandatory = $true)][string]$End,
    [string]$Tickers = 'SPY,QQQ,IWM',
    [string]$DbPath = '',
    [string]$Times = '',
    [int]$StallMinutes = 15,
    [int]$MaxRestarts = 6
)

$ErrorActionPreference = 'Stop'
$backend = Split-Path $PSScriptRoot
$repo = Split-Path $backend
$python = Join-Path $repo '.venv\Scripts\python.exe'
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Force $results | Out-Null

if (-not $env:VOLFIT_FLATFILES_KEY) {
    $localEnv = Join-Path $repo 'restart.local.ps1'
    if (Test-Path $localEnv) { . $localEnv }
}
if (-not $env:VOLFIT_FLATFILES_KEY) {
    throw 'no flat-file credentials (set VOLFIT_FLATFILES_KEY/_SECRET or create restart.local.ps1)'
}

# Stream python's prints into the log as they happen (default block-buffering
# holds everything until exit, which reads as silence for hours).
$env:PYTHONUNBUFFERED = '1'

$argList = @('-m', 'backtest.capture_intraday', '--start', $Start, '--end', $End, '--tickers', $Tickers)
if ($DbPath) { $argList += @('--db', $DbPath) }
if ($Times) { $argList += @('--times', $Times) }

function Get-TreeCpu([int]$RootPid) {
    # CPU seconds of the launched process + its direct children: the venv
    # python.exe is a launcher shim whose real interpreter runs as a child.
    $ids = @($RootPid)
    $ids += @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootPid" |
            ForEach-Object { $_.ProcessId })
    $sum = 0.0
    foreach ($id in $ids) {
        try { $sum += (Get-Process -Id $id -ErrorAction Stop).TotalProcessorTime.TotalSeconds } catch {}
    }
    return $sum
}

function Log([string]$msg) {
    Write-Host ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $msg)
}

for ($run = 1; $run -le $MaxRestarts; $run++) {
    $outLog = Join-Path $results "capture_probe.run$run.out.log"
    $errLog = Join-Path $results "capture_probe.run$run.err.log"
    Log "run $run/${MaxRestarts}: launching capture ($Start -> $End, $Tickers)"
    $p = Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory $backend `
        -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $null = $p.Handle  # cache the handle or $p.ExitCode reads $null later (PS 5.1)

    $killed = $false
    $lastCpu = -1.0
    $lastAdvance = Get-Date
    $ticks = 0
    while (-not $p.HasExited) {
        Start-Sleep -Seconds 60
        if ($p.HasExited) { break }
        $cpu = Get-TreeCpu $p.Id
        if ($cpu -gt $lastCpu + 0.5) { $lastCpu = $cpu; $lastAdvance = Get-Date }
        $quietMin = ((Get-Date) - $lastAdvance).TotalMinutes
        $ticks++
        if ($ticks % 5 -eq 0) {
            Log ('alive: cpu {0:N0}s, last progress {1:N0} min ago' -f $cpu, $quietMin)
        }
        if ($quietMin -ge $StallMinutes) {
            Log "STALLED: no CPU progress for $StallMinutes min (frozen stream) - killing tree, relaunching"
            taskkill /PID $p.Id /T /F | Out-Null
            $killed = $true
            break
        }
    }

    if (-not $killed) {
        $text = ''
        foreach ($f in @($outLog, $errLog)) {
            if (Test-Path $f) { $text += (Get-Content $f -Raw) }
        }
        Log "--- capture output (run $run):"
        if ($text.Trim()) { Write-Host $text.Trim() }
        if ($text -match 'no flat-file credentials') {
            Log 'credentials rejected - aborting (fix env, no point retrying)'
            exit 2
        }
        if (($p.ExitCode -eq 0) -and ($text -notmatch 'failed:|no usable quotes')) {
            Log 'capture completed cleanly.'
            exit 0
        }
        Log 'capture exited with failures - retrying (finished days are skipped on resume)'
        Start-Sleep -Seconds 120  # let a transient network/DNS outage pass
    }
}

Log "gave up after $MaxRestarts runs - see capture_probe.run*.log under backtest\results"
exit 1
