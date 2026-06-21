# build_exe.ps1 — build the VolFitter standalone desktop .exe.
#
# Pipeline:
#   1. Build the React bundle  (npm --prefix frontend run build -> frontend/dist)
#   2. Ensure PyInstaller is installed in the .venv
#   3. Freeze backend/desktop.py into dist/VolFitter.exe via volfit.spec
#
# The result, dist/VolFitter.exe, is a single single-origin process: FastAPI
# serves both the API and the bundled UI, then opens the browser at it.
#
# Usage:   .\build_exe.ps1            # full build
#          .\build_exe.ps1 -SkipFrontend   # reuse an existing frontend/dist
#
# Prereqs: Node/npm (for the React build) and the project's .venv (volfit
# editable-installed, numba/scipy/fastapi/uvicorn present — see CLAUDE.md).

param(
    [switch]$SkipFrontend   # reuse an existing frontend/dist (faster re-freeze)
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$py   = Join-Path $repo ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    throw "No .venv python at $py — create the venv first (see CLAUDE.md)."
}

# --- 1. Build the React bundle ---------------------------------------------
if ($SkipFrontend) {
    Write-Host "Skipping frontend build (-SkipFrontend); reusing frontend/dist"
} else {
    Write-Host "Building React bundle (npm run build) ..." -ForegroundColor Cyan
    Push-Location (Join-Path $repo "frontend")
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

$indexHtml = Join-Path $repo "frontend\dist\index.html"
if (-not (Test-Path $indexHtml)) {
    throw "frontend/dist/index.html missing — run without -SkipFrontend to build it."
}

# --- 2. Ensure PyInstaller is available ------------------------------------
Write-Host "Checking PyInstaller ..." -ForegroundColor Cyan
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller into the .venv ..."
    & $py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed (PyPI is flaky here — retry)" }
}

# --- 3. Freeze the .exe -----------------------------------------------------
Write-Host "Freezing dist/VolFitter.exe via volfit.spec ..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean (Join-Path $repo "volfit.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit $LASTEXITCODE)" }

$exe = Join-Path $repo "dist\VolFitter.exe"
if (Test-Path $exe) {
    $size = "{0:N1} MB" -f ((Get-Item $exe).Length / 1MB)
    Write-Host "Built $exe ($size)" -ForegroundColor Green
    Write-Host "Run it directly; it serves the UI + API on one origin and opens your browser."
} else {
    throw "Build reported success but $exe is missing."
}
