# restart.ps1 — restart the vol-fitter app (backend on :8000 + frontend on :5173)
#
# Usage:   .\restart.ps1                        # ALL data sources live; auto-pick active
#          .\restart.ps1 -Live                  # force Yahoo active on launch
#          .\restart.ps1 -Bloomberg             # force Bloomberg active on launch
#          .\restart.ps1 -Massive               # force Massive active on launch
#          .\restart.ps1 -Synthetic             # force the offline synthetic source
#          .\restart.ps1 -Db my.sqlite          # custom persistence file
#          .\restart.ps1 -NoDb                  # disable on-disk persistence
#
# Kills whatever is listening on the two dev ports (clears stale uvicorn / Vite
# servers), then relaunches the FastAPI backend and the Vite dev server.
#
# Data sources: serve.py registers ALL feeds (Yahoo, Bloomberg, Massive when
# $env:VOLFIT_MASSIVE_KEY is set, Synthetic), so the in-app Data Source selector
# can switch between them at runtime with a status light each. The default run
# (no flag) lets the backend auto-pick the best-reachable source as active
# (Bloomberg -> Yahoo -> Massive -> Synthetic); the switches above just FORCE a
# specific one active on launch. Set $env:VOLFIT_MASSIVE_KEY in your shell to
# light up Massive (no key = Massive shows Red, the rest still work).
#
# Persistence: by default VOLFIT_DB points at backend\data\volfit.sqlite, so
# saved/loaded named universes (and the fit-history series) survive restarts.
# Pass -NoDb to run side-effect free, or -Db <path> to use another file.
# (*.sqlite is gitignored, so the DB never lands in version control.)

param(
    [switch]$Live,             # force the Yahoo source active on launch
    [switch]$Bloomberg,        # force the Bloomberg (xbbg) source active on launch
    [switch]$Massive,          # force the Massive source active on launch
    [switch]$Synthetic,        # force the offline synthetic source active on launch
    [string]$Db = "backend\data\volfit.sqlite",  # SQLite persistence file
    [switch]$NoDb              # disable on-disk persistence (overrides -Db)
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

# --- 0. Local secrets / env (gitignored) -----------------------------------
# restart.local.ps1 (NOT committed) sets API keys + flat-file S3 creds so they
# persist across launches without re-exporting them each session. Copy
# restart.local.ps1.example to restart.local.ps1 and fill in your keys. Values
# already set in the shell win (the file's guards skip them).
$localEnv = Join-Path $repo "restart.local.ps1"
if (Test-Path $localEnv) {
    Write-Host "Loading local env from restart.local.ps1"
    . $localEnv
}

# --- 1. Kill anything on the dev ports -------------------------------------
foreach ($port in 8000, 5173) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            Write-Host "Stopping process $_ on port $port"
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}

# --- 2. Start the backend (uvicorn on :8000) -------------------------------
# All sources are registered regardless; these flags only FORCE the active one.
if (-not $env:VOLFIT_TICKERS) { $env:VOLFIT_TICKERS = 'SPY,QQQ,AAPL' }
Remove-Item Env:\VOLFIT_PROVIDER -ErrorAction SilentlyContinue  # default: auto-pick
if ($Bloomberg)     { $env:VOLFIT_PROVIDER = 'bloomberg' }
elseif ($Massive)   { $env:VOLFIT_PROVIDER = 'massive' }
elseif ($Live)      { $env:VOLFIT_PROVIDER = 'yahoo' }
elseif ($Synthetic) { $env:VOLFIT_PROVIDER = 'synthetic' }

$forced = if ($env:VOLFIT_PROVIDER) { $env:VOLFIT_PROVIDER } else { 'auto (best-reachable)' }
Write-Host "Backend: all sources registered; active = $forced ($env:VOLFIT_TICKERS)"
if (-not $env:VOLFIT_MASSIVE_KEY) {
    Write-Host "  (set `$env:VOLFIT_MASSIVE_KEY to light up Massive; it shows Red without one)"
}
if (-not $env:VOLFIT_FLATFILES_KEY) {
    Write-Host "  (set `$env:VOLFIT_FLATFILES_KEY/`$env:VOLFIT_FLATFILES_SECRET +"
    Write-Host "   `$env:VOLFIT_FLATFILES_ENDPOINT='files.massive.com' for Massive past-day"
    Write-Host "   history: official Close + historical intraday via the flat files)"
}

# Persistence: serve.py reads VOLFIT_DB and opens that SQLite file for named
# universes (save/load) and the fit-history series. Resolve to an absolute path
# and ensure its folder exists; Start-Process inherits this process's env.
if ($NoDb) {
    Remove-Item Env:\VOLFIT_DB -ErrorAction SilentlyContinue
    Write-Host "Persistence: OFF (-NoDb)"
} else {
    $dbPath = if ([System.IO.Path]::IsPathRooted($Db)) { $Db } else { Join-Path $repo $Db }
    New-Item -ItemType Directory -Force -Path (Split-Path $dbPath) | Out-Null
    $env:VOLFIT_DB = $dbPath
    Write-Host "Persistence: $dbPath (named universes + fit history persist)"
}

# Capture backend stdout/stderr to log files. Without this the backend runs in a
# window that closes the instant build_app() throws (a provider ctor, a hung
# data-source probe, a bad import) — the error vanishes and "it just won't start".
# With the logs, any startup failure is visible below and in backend\data\.
$logDir = Join-Path $repo "backend\data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "serve.out.log"
$errLog = Join-Path $logDir "serve.err.log"
$backend = Start-Process -FilePath (Join-Path $repo ".venv\Scripts\python.exe") `
    -ArgumentList "backend\serve.py" -WorkingDirectory $repo `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru

# --- 3. Start the frontend (Vite on :5173) in its own window ---------------
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "npm run dev" `
    -WorkingDirectory (Join-Path $repo "frontend")

# --- 4. Wait for the backend to actually bind :8000 ------------------------
# Auto-pick probes every data source before uvicorn binds, so give it a few
# seconds; report the active source on success, or tail the log on failure.
Write-Host "Waiting for backend on :8000 ..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($backend.HasExited) { break }
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 8000)
        $tcp.Close()
        $ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 500
        Write-Host "." -NoNewline
    }
}
Write-Host ""
if ($ready) {
    $active = (Select-String -Path $outLog -Pattern "active=\S+" -ErrorAction SilentlyContinue |
        Select-Object -Last 1).Line
    Write-Host "Backend UP on http://localhost:8000  $active" -ForegroundColor Green
} else {
    Write-Host "Backend FAILED to bind :8000 - last lines of ${errLog}:" -ForegroundColor Red
    Get-Content $errLog -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
}
Write-Host "Restarted: backend -> http://localhost:8000, frontend -> http://localhost:5173"
