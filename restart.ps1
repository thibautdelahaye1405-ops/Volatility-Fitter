# restart.ps1 — restart the vol-fitter app (backend on :8000 + frontend on :5173)
#
# Usage:   .\restart.ps1
#          .\restart.ps1 -Live          # backend with Yahoo live provider
#
# Kills whatever is listening on the two dev ports (clears stale uvicorn / Vite
# servers), then relaunches the FastAPI backend and the Vite dev server.

param(
    [switch]$Live  # when set, start the backend against the Yahoo live provider
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
Start-Process -FilePath (Join-Path $repo ".venv\Scripts\python.exe") `
    -ArgumentList "backend\serve.py" -WorkingDirectory $repo

# --- 3. Start the frontend (Vite on :5173) in its own window ---------------
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "npm run dev" `
    -WorkingDirectory (Join-Path $repo "frontend")

Write-Host "Restarted: backend -> http://localhost:8000, frontend -> http://localhost:5173"
