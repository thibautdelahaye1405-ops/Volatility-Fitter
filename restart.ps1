# restart.ps1 — restart the vol-fitter app (backend on :8000 + frontend on :5173)
#
# Usage:   .\restart.ps1
#          .\restart.ps1 -Live                  # backend with Yahoo live provider
#          .\restart.ps1 -Live -Db my.sqlite    # custom persistence file
#          .\restart.ps1 -NoDb                  # disable on-disk persistence
#
# Kills whatever is listening on the two dev ports (clears stale uvicorn / Vite
# servers), then relaunches the FastAPI backend and the Vite dev server.
#
# Persistence: by default VOLFIT_DB points at backend\data\volfit.sqlite, so
# saved/loaded named universes (and the fit-history series) survive restarts.
# Pass -NoDb to run side-effect free, or -Db <path> to use another file.
# (*.sqlite is gitignored, so the DB never lands in version control.)

param(
    [switch]$Live,             # start the backend against the Yahoo live provider
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
if ($Live) {
    $env:VOLFIT_PROVIDER = 'yahoo'
    $env:VOLFIT_TICKERS  = 'SPY,QQQ,AAPL'
    Write-Host "Backend: live Yahoo provider ($env:VOLFIT_TICKERS)"
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
