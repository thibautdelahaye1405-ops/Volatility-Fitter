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
   frontend, picks a free port (falling back off :8000), opens the browser, and
   runs uvicorn. Persistence defaults to
   `%LOCALAPPDATA%\VolFitter\volfit.sqlite` so named universes / fit history
   survive even when the install dir is read-only.

## Run it from source (no freeze)

```powershell
npm --prefix frontend run build        # produces frontend/dist
.venv\Scripts\python backend\desktop.py
```

Opens your browser at `http://127.0.0.1:8000/` (or a free port). Useful env:
`VOLFIT_DESKTOP_PORT`, `VOLFIT_DESKTOP_NO_BROWSER=1`, plus all of `serve.py`'s
`VOLFIT_PROVIDER` / `VOLFIT_TICKERS` / `VOLFIT_MASSIVE_KEY` …

## Build the `.exe`

```powershell
.\build_exe.ps1            # builds the React bundle, then freezes via volfit.spec
.\build_exe.ps1 -SkipFrontend   # reuse an existing frontend/dist
```

Output: `dist\VolFitter.exe` — a one-file executable. Double-click it; it serves
the UI + API on one origin and opens your browser.

### PyInstaller notes (`volfit.spec`)

- Entry = `backend/desktop.py`; `pathex=[backend]` so `from serve import …`
  resolves. `frontend/dist` ships as data under `frontend_dist`.
- `hiddenimports` collect `volfit`, `uvicorn` (its loop/protocol/lifespan impls
  are loaded by string), `numba`, `llvmlite`; native DLLs for numba/llvmlite are
  pulled via `collect_dynamic_libs`.
- `upx=False` on purpose — UPX trips antivirus and can corrupt the numba/llvmlite
  DLLs. `console=True` so the active data source + URL are visible.

### Build status

The freeze has been run and **succeeds**: `dist\VolFitter.exe` (~135 MB,
one-file) launches, serves the UI + API on one origin (verified `/`,
`/universe`, `/assets/*` all 200 from the frozen bundle's `sys._MEIPASS`
`frontend_dist`), and writes persistence under `%LOCALAPPDATA%\VolFitter`.

Known caveat: PyInstaller warns `tbb12.dll` could not be resolved (numba's TBB
threading layer is not installed in the venv). It is **non-fatal** — numba
imports and falls back to its `workqueue` threading layer, and the LV march has
its own banded fallback besides. To silence it / get TBB parallelism, `pip
install tbb` into the venv before building.

Likely follow-ups: window chrome (pywebview instead of the system browser), an
app icon, and code-signing.
