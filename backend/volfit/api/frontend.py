"""Single-origin static serving for the packaged desktop app.

In development the React app runs under Vite on :5173 and talks cross-origin to
the API on :8000 (CORS — see ``app.py``). For the standalone PyInstaller ``.exe``
there is only ONE process and ONE origin: FastAPI serves both the API (routers
mounted at root) AND the built React bundle (``frontend/dist``).

This module is *additive* — it is never imported by ``create_app`` and so does
not touch the dev/test paths. The desktop entry point (``backend/desktop.py``)
calls :func:`mount_frontend` on the app it builds, after the routers are wired,
so explicit API routes always win and the static mount only catches whatever is
left (``/``, ``/assets/...``, favicon, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def find_frontend_dist() -> Path | None:
    """Locate the built React bundle (the directory containing ``index.html``).

    Resolution order:

    1. **PyInstaller bundle** — when frozen, the spec copies ``frontend/dist``
       into the one-file extraction dir exposed as ``sys._MEIPASS`` under
       ``frontend_dist`` (see ``volfit.spec``).
    2. **Source checkout** — ``<repo>/frontend/dist`` relative to this file
       (``backend/volfit/api/frontend.py`` → three parents up to ``backend``,
       then a sibling ``frontend``). Lets ``python backend/desktop.py`` serve a
       locally-built bundle without freezing.

    Returns ``None`` when no built bundle is found (caller logs a hint to run the
    frontend build first).
    """
    # 1. Frozen PyInstaller one-file bundle.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "frontend_dist"
        if (bundled / "index.html").is_file():
            return bundled

    # 2. Source checkout: backend/volfit/api/frontend.py -> repo root -> frontend/dist
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "frontend" / "dist"
    if (candidate / "index.html").is_file():
        return candidate
    return None


def mount_frontend(app: FastAPI, dist_dir: Path | None = None) -> bool:
    """Mount the built React bundle at ``/`` for single-origin serving.

    Must be called *after* the API routers are included so the explicit API
    routes (``/smiles``, ``/graph``, …) take precedence; the static mount at
    ``/`` only serves paths no router matched. ``html=True`` makes ``/`` resolve
    to ``index.html`` and serves the hashed ``/assets/*`` bundle Vite emits.

    The app is a tab-based SPA with no client-side router, so directory-style
    ``index.html`` resolution is sufficient (no deep-link history fallback
    needed). Returns ``True`` if a bundle was mounted, ``False`` otherwise so the
    caller can warn that only the API is being served.
    """
    dist = dist_dir or find_frontend_dist()
    if dist is None or not (Path(dist) / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    return True
