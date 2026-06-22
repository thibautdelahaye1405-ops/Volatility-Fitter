# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the VolFitter standalone desktop app.

Build with the helper script (which builds the React bundle first):

    .\build_exe.ps1

…or directly once `frontend/dist` exists:

    .venv\Scripts\pyinstaller volfit.spec

Produces a one-file `dist/VolFitter.exe` that runs `backend/desktop.py`: a
single single-origin process serving both the API and the bundled React UI,
then opening the browser at it. See `DESKTOP.md`.

Notes / gotchas baked in below:
  * The frozen entry is `backend/desktop.py`; `pathex` puts `backend/` on the
    import path so its `from serve import build_app` resolves.
  * `frontend/dist` is shipped as data under `frontend_dist`; `api.frontend`
    finds it via `sys._MEIPASS` when frozen.
  * uvicorn loads its loop/protocol/lifespan impls by string at runtime, and
    numba/scipy carry native extensions PyInstaller's static analysis misses —
    hence the explicit collection below.
"""

import glob
import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

REPO = os.path.abspath(os.getcwd())
BACKEND = os.path.join(REPO, "backend")
FRONTEND_DIST = os.path.join(REPO, "frontend", "dist")

if not os.path.isfile(os.path.join(FRONTEND_DIST, "index.html")):
    raise SystemExit(
        "frontend/dist/index.html not found — build the React app first "
        "(`npm --prefix frontend run build`) or use build_exe.ps1."
    )

# --- data: the React bundle (-> frontend_dist/) + the app icon ----------------
datas = [(FRONTEND_DIST, "frontend_dist")]
ICON = os.path.join(REPO, "assets", "volfitter.ico")
if os.path.isfile(ICON):
    datas.append((ICON, "."))   # so desktop._find_icon() resolves it at runtime

# --- hidden imports: things loaded by string / native ------------------------
hiddenimports = []
hiddenimports += collect_submodules("volfit")        # all routers/models, dynamically aggregated
hiddenimports += collect_submodules("uvicorn")       # loops/protocols/lifespan picked by name
hiddenimports += [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
]
hiddenimports += collect_submodules("numba")
hiddenimports += collect_submodules("llvmlite")
# pywebview native window: its platform backend + pythonnet (.NET / WebView2 on
# Windows) are resolved dynamically. collect_all is overkill; these cover it.
hiddenimports += collect_submodules("webview")
hiddenimports += ["clr", "clr_loader", "pythonnet", "proxy_tools", "bottle"]

# numba/llvmlite/scipy native libraries.
binaries = []
binaries += collect_dynamic_libs("llvmlite")
binaries += collect_dynamic_libs("numba")

# Intel TBB runtime (numba's TBB threading layer). When `tbb` is pip-installed,
# tbb12.dll lands in <venv>/Library/bin, NOT inside a package dir, so
# collect_dynamic_libs misses it — add it explicitly so the frozen exe gets the
# parallel layer instead of falling back to workqueue (and silences PyInstaller's
# "could not resolve tbb12.dll" warning). Skipped cleanly if tbb isn't installed.
binaries += collect_dynamic_libs("tbb")
for _dll in ("tbb12.dll", "tbbmalloc.dll", "tcm.dll"):
    for _hit in glob.glob(os.path.join(sys.prefix, "Library", "bin", _dll)):
        binaries.append((_hit, "."))

block_cipher = None

a = Analysis(
    [os.path.join(BACKEND, "desktop.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim weight: dev/test-only deps never used at runtime.
        "pytest", "_pytest", "puppeteer", "IPython", "notebook", "matplotlib",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VolFitter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX often trips antivirus + corrupts numba/llvmlite DLLs
    runtime_tmpdir=None,
    console=False,        # windowed app: no console flashes behind the native window
    disable_windowed_traceback=False,
    icon=(ICON if os.path.isfile(ICON) else None),  # exe + window + taskbar icon
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
