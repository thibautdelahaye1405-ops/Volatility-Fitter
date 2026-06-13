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

Start-Process -FilePath (Join-Path $repo ".venv\Scripts\python.exe") `
    -ArgumentList "backend\serve.py" -WorkingDirectory $repo

# --- 3. Start the frontend (Vite on :5173) in its own window ---------------
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "npm run dev" `
    -WorkingDirectory (Join-Path $repo "frontend")

Write-Host "Restarted: backend -> http://localhost:8000, frontend -> http://localhost:5173"
