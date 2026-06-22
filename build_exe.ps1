# build_exe.ps1 - build the VolFitter standalone desktop .exe.
#
# Pipeline:
#   1. Ensure the freeze-time deps in the .venv (pyinstaller, tbb, pywebview,
#      pythonnet, pillow)
#   2. Regenerate the app icon (assets/volfitter.ico + frontend/public/favicon.ico)
#   3. Build the React bundle  (npm --prefix frontend run build -> frontend/dist)
#   4. Freeze backend/desktop.py into dist/VolFitter.exe via volfit.spec
#
# The result, dist/VolFitter.exe, is a single single-origin process: FastAPI
# serves both the API and the bundled UI, opened in a native pywebview window.
#
# Usage:   .\build_exe.ps1            # full build
#          .\build_exe.ps1 -SkipFrontend   # reuse an existing frontend/dist
#
# Prereqs: Node/npm (for the React build) and the project's .venv (volfit
# editable-installed, numba/scipy/fastapi/uvicorn present - see CLAUDE.md).

param(
    [switch]$SkipFrontend   # reuse an existing frontend/dist (faster re-freeze)
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$py   = Join-Path $repo ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    throw "No .venv python at $py - create the venv first (see CLAUDE.md)."
}

# --- 1. Ensure freeze-time deps --------------------------------------------
# PyInstaller is required; the rest degrade gracefully (the exe falls back to
# the browser without pywebview, to the workqueue layer without tbb, and ships
# no custom icon without pillow), so only PyInstaller is fatal.
Write-Host "Checking PyInstaller ..." -ForegroundColor Cyan
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller into the .venv ..."
    & $py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed (PyPI is flaky here - retry)" }
}

# Intel TBB (numba parallel layer; spec bundles tbb12.dll from <venv>/Library/bin),
# pywebview + pythonnet (native WebView2 window), pillow (icon generation).
Write-Host "Ensuring tbb / pywebview / pythonnet / pillow ..." -ForegroundColor Cyan
& $py -c "import tbb, webview, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $py -m pip install tbb pywebview pythonnet pillow
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  (some optional deps failed to install; exe will use fallbacks)" -ForegroundColor Yellow
    }
}

# --- 2. Regenerate the app icon (before the frontend build, so the favicon
#        lands in dist). Best-effort: skipped if pillow is unavailable. --------
& $py -c "import PIL" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Regenerating app icon ..." -ForegroundColor Cyan
    & $py (Join-Path $repo "assets\make_icon.py")
}

# --- 3. Build the React bundle ---------------------------------------------
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
    throw "frontend/dist/index.html missing - run without -SkipFrontend to build it."
}

# --- 4. Freeze the .exe -----------------------------------------------------
# A still-running VolFitter.exe locks the output file; stop any before freezing.
Get-Process VolFitter -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Freezing dist/VolFitter.exe via volfit.spec ..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean (Join-Path $repo "volfit.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit $LASTEXITCODE)" }

$exe = Join-Path $repo "dist\VolFitter.exe"
if (Test-Path $exe) {
    $size = "{0:N1} MB" -f ((Get-Item $exe).Length / 1MB)
    Write-Host "Built $exe ($size)" -ForegroundColor Green
    Write-Host "Run it directly; it serves the UI + API on one origin in a native window."
} else {
    throw "Build reported success but $exe is missing."
}
