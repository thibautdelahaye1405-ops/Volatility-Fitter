"""Standalone desktop entry point — the target of the PyInstaller ``.exe``.

Unlike ``serve.py`` (the dev backend, meant to pair with the Vite dev server on
:5173), this runs the WHOLE app as a single single-origin process:

    * builds the API app with every data source registered (reusing
      ``serve.build_app`` — same auto-pick active source, same env config), then
    * mounts the built React bundle at ``/`` (``api.frontend.mount_frontend``) so
      the UI and the API share one origin, then
    * opens the user's default browser at the served page and runs uvicorn.

Run from source against a locally-built bundle:

    npm --prefix frontend run build
    .venv\\Scripts\\python backend\\desktop.py

Or frozen: ``dist\\VolFitter.exe`` (see ``volfit.spec`` / ``build_exe.ps1``).

Environment overrides (all optional — sensible desktop defaults otherwise):
    VOLFIT_DESKTOP_PORT   port to bind (default 8000; falls back to a free port
                          if taken so a stale instance never blocks launch).
    VOLFIT_DESKTOP_NO_BROWSER  set to "1" to skip auto-opening the browser.
    VOLFIT_DB             SQLite persistence path; defaults under LOCALAPPDATA so
                          named universes / fit history survive across launches
                          even when the install dir is read-only.
    (plus all of serve.py's VOLFIT_PROVIDER / VOLFIT_TICKERS / VOLFIT_MASSIVE_KEY …)
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# When frozen by PyInstaller, ``backend/`` is on the bundled module path already.
# When run as a script, sys.path[0] is this file's dir (backend/), so ``serve``
# imports fine. Make the source-checkout case explicit and robust regardless of
# the caller's CWD.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import uvicorn  # noqa: E402

from serve import build_app  # noqa: E402  (backend/serve.py)
from volfit.api.frontend import find_frontend_dist, mount_frontend  # noqa: E402

#: Host is always loopback — this is a local desktop app, never a network server.
HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _default_db_path() -> str:
    """A user-writable SQLite path under the OS app-data dir.

    The install directory of a packaged ``.exe`` may be read-only (Program
    Files), so persistence must live in the user's profile. Honours an existing
    ``VOLFIT_DB``; otherwise ``%LOCALAPPDATA%\\VolFitter\\volfit.sqlite`` (or the
    POSIX ``~/.local/share`` equivalent for source runs on other platforms).
    """
    existing = os.environ.get("VOLFIT_DB", "").strip()
    if existing:
        return existing
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    target = Path(base) / "VolFitter"
    target.mkdir(parents=True, exist_ok=True)
    return str(target / "volfit.sqlite")


def _resolve_port(preferred: int) -> int:
    """Return ``preferred`` if free, else an OS-assigned free port.

    A leftover instance (or the user's own dev server) holding :8000 must not
    brick the launch — bind-test the preferred port and fall back cleanly.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as scratch:
        scratch.bind((HOST, 0))
        return scratch.getsockname()[1]


def _open_browser_when_up(url: str, host: str, port: int) -> None:
    """Open the default browser once the server is accepting connections.

    Polls the socket on a daemon thread (max ~10s) so the page only opens after
    uvicorn has bound — avoids the blank-tab race of opening too early.
    """
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.2)


def main() -> None:
    """Build the single-origin app, open the browser, and serve until closed."""
    os.environ["VOLFIT_DB"] = _default_db_path()

    app = build_app()  # all data sources registered + best-reachable active one
    if mount_frontend(app):
        print(f"Frontend bundle served from {find_frontend_dist()}")
    else:
        print(
            "WARNING: no built frontend bundle found — serving API only. "
            "Run `npm --prefix frontend run build` (or build the .exe via "
            "build_exe.ps1) so the React app is bundled."
        )

    port = _resolve_port(int(os.environ.get("VOLFIT_DESKTOP_PORT", DEFAULT_PORT)))
    url = f"http://{HOST}:{port}/"
    print(f"VolFitter desktop: {url}  (Ctrl+C to quit)")

    if os.environ.get("VOLFIT_DESKTOP_NO_BROWSER", "").strip() != "1":
        threading.Thread(
            target=_open_browser_when_up, args=(url, HOST, port), daemon=True
        ).start()

    uvicorn.run(app, host=HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()
