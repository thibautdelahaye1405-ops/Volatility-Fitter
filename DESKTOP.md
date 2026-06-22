# VolFitter — Standalone Desktop `.exe`

This branch (`feature/desktop-exe`) packages VolFitter as a **single-origin
desktop app**: one process, one port, both the API and the React UI. It is the
prerequisite for the PyInstaller `.exe` — a browser app can only be bundled into
one executable if the same server serves the page *and* answers its API calls.

The dev workflow on `main` is unchanged: `restart.ps1` still runs Vite on
:5173 cross-origin to the backend on :8000 with CORS. Single-origin only kicks
in for production / packaged runs.

## How single-origin works

| Layer | Dev (`main`, `restart.ps1`) | Packaged (`desktop.py` / `.exe`) |
| --- | --- | --- |
| UI host | Vite dev server, :5173 | FastAPI static mount, same port as API |
| API host | uvicorn, :8000 | uvicorn, same port |
| Cross-origin | yes (CORS allow-list) | no — one origin |
| Frontend API base | `http://localhost:8000` | `window.location.origin` (relative) |

Three small, additive pieces make it work:

1. **`frontend/src/state/api.ts`** — `API_BASE_URL` is now
   `import.meta.env.DEV ? "http://localhost:8000" : window.location.origin`.
   Production builds therefore call the same host:port that served the page, so
   the bundle is port-agnostic (the launcher may bind off :8000 if it's taken).

2. **`backend/volfit/api/frontend.py`** — `mount_frontend(app)` mounts the built
   `frontend/dist` at `/` *after* the routers, so the API routes (all at root:
   `/smiles`, `/graph`, …) still win and the static mount only serves the SPA
   shell + hashed `/assets/*`. `find_frontend_dist()` locates the bundle in a
   source checkout *or* inside a frozen PyInstaller bundle (`sys._MEIPASS`).
   `create_app` is **untouched**, so dev and the test suite are unaffected.

3. **`backend/desktop.py`** — the packaged entry point. Reuses
   `serve.build_app()` (same data-source registration / auto-pick), mounts the
   frontend, picks a free port (falling back off :8000), serves uvicorn on a
   **background thread**, and opens the UI in a **native pywebview window**
   (system WebView2 on Windows) — falling back to the system browser if the
   window backend is unavailable. Persistence defaults to
   `%LOCALAPPDATA%\VolFitter\volfit.sqlite` so named universes / fit history
   survive even when the install dir is read-only.

## Native window, icon & logs

- **Window** — pywebview owns the main thread (a Windows requirement), so
  uvicorn runs on a daemon thread; closing the window stops the server
  (`server.should_exit`). Title "VolFitter", 1480×920, dark-navy background so
  there's no white flash before the React app paints.
- **Icon** — `assets/make_icon.py` draws a volatility-smile tile
  (`assets/volfitter.ico` for the exe/window/taskbar; `frontend/public/favicon.ico`
  for the browser tab / WebView2 favicon). `build_exe.ps1` regenerates both
  before the frontend build; `volfit.spec` sets the exe `icon=`.
- **Logs** — the exe is windowed (`console=False`), so `desktop.py` redirects
  `stdout`/`stderr` to `%LOCALAPPDATA%\VolFitter\desktop.log` (uvicorn logging
  would otherwise crash writing to a null stream). A failed launch leaves a
  trace there.

### Launch modes (`VOLFIT_DESKTOP_MODE`)

| value | behaviour |
| --- | --- |
| `window` *(default)* | native pywebview window (browser fallback if unavailable) |
| `browser` | serve + open the system browser |
| `server` | serve only, launch no UI (smoke tests / headless) |

(`VOLFIT_DESKTOP_NO_BROWSER=1` is a deprecated alias for `server`.)

## Run it from source (no freeze)

```powershell
npm --prefix frontend run build        # produces frontend/dist
.venv\Scripts\python backend\desktop.py   # opens a native window
```

Useful env: `VOLFIT_DESKTOP_MODE`, `VOLFIT_DESKTOP_PORT`, plus all of
`serve.py`'s `VOLFIT_PROVIDER` / `VOLFIT_TICKERS` / `VOLFIT_MASSIVE_KEY` …

## Build the `.exe`

```powershell
.\build_exe.ps1            # builds the React bundle, then freezes via volfit.spec
.\build_exe.ps1 -SkipFrontend   # reuse an existing frontend/dist
```

Output: `dist\VolFitter.exe` — a one-file executable. Double-click it; it serves
the UI + API on one origin and opens a native window.

### PyInstaller notes (`volfit.spec`)

- Entry = `backend/desktop.py`; `pathex=[backend]` so `from serve import …`
  resolves. `frontend/dist` ships as data under `frontend_dist`; the icon ships
  at the bundle root.
- `hiddenimports` collect `volfit`, `uvicorn` (its loop/protocol/lifespan impls
  are loaded by string), `numba`, `llvmlite`, and `webview` + `pythonnet`/`clr`
  (the WebView2 backend); native DLLs for numba/llvmlite/tbb are pulled via
  `collect_dynamic_libs` + an explicit `tbb12.dll` add.
- `upx=False` on purpose — UPX trips antivirus and can corrupt the numba/llvmlite
  DLLs. `console=False` (windowed); logs go to `%LOCALAPPDATA%\VolFitter\desktop.log`.

### Build status

The freeze has been run and **succeeds**: `dist\VolFitter.exe` (~135 MB,
one-file) launches a native window, serves the UI + API on one origin (verified
the WebView2 window renders the app and drives live API calls — `/`, `/favicon.ico`,
`/priors`, `/spot`, `/smiles/*` all 200 from the frozen `sys._MEIPASS` bundle),
and writes persistence + logs under `%LOCALAPPDATA%\VolFitter`. The bundle
contains `tbb12.dll`, `volfitter.ico`, and `frontend_dist/favicon.ico`.

numba's TBB threading layer: `build_exe.ps1` installs `tbb` into the venv and
`volfit.spec` bundles `tbb12.dll` (from `<venv>/Library/bin`) into the exe, so
numba gets its parallel layer when frozen — no `tbb12.dll` warning. If `tbb` is
ever missing, the build still succeeds and numba falls back to the `workqueue`
layer (and the LV march has its own banded fallback besides).

Likely follow-ups: code-signing (avoids the SmartScreen prompt on first run) and
an installer (e.g. Inno Setup) for Start-menu/desktop shortcuts.
