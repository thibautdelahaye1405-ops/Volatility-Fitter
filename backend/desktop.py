"""Standalone desktop entry point — the target of the PyInstaller ``.exe``.

Unlike ``serve.py`` (the dev backend, meant to pair with the Vite dev server on
:5173), this runs the WHOLE app as a single single-origin process:

    * builds the API app with every data source registered (reusing
      ``serve.build_app`` — same auto-pick active source, same env config), then
    * mounts the built React bundle at ``/`` (``api.frontend.mount_frontend``) so
      the UI and the API share one origin, then
    * serves uvicorn on a background thread and opens the UI in a **native
      pywebview window** (system WebView2 on Windows) — so it feels like a real
      desktop app, not a browser tab. Falls back to the default browser if
      pywebview is unavailable.

Run from source against a locally-built bundle:

    npm --prefix frontend run build
    .venv\\Scripts\\python backend\\desktop.py

Or frozen: ``dist\\VolFitter.exe`` (see ``volfit.spec`` / ``build_exe.ps1``).

Environment overrides (all optional — sensible desktop defaults otherwise):
    VOLFIT_DESKTOP_MODE   "window" (default — native pywebview window), "browser"
                          (serve + open the system browser), or "server" (serve
                          only, launch no UI — for smoke tests / headless).
    VOLFIT_DESKTOP_PORT   port to bind (default 8000; falls back to a free port
                          if taken so a stale instance never blocks launch).
    VOLFIT_DESKTOP_NO_BROWSER  deprecated alias for VOLFIT_DESKTOP_MODE=server.
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


def _app_data_dir() -> Path:
    """The user-writable VolFitter app-data dir (created on demand)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    target = Path(base) / "VolFitter"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _ensure_log_streams() -> None:
    """Redirect stdout/stderr to a log file when they are missing.

    A windowed PyInstaller build (``console=False``) can leave
    ``sys.stdout``/``sys.stderr`` as ``None``; uvicorn's logging then crashes on
    its first write. Point them at ``%LOCALAPPDATA%\\VolFitter\\desktop.log`` so
    logging works and a failed launch leaves a recoverable trace.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = open(_app_data_dir() / "desktop.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = log
    sys.stderr = log


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
    return str(_app_data_dir() / "volfit.sqlite")


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


def _launch_mode() -> str:
    """Resolve how to surface the UI: ``window`` | ``browser`` | ``server``.

    ``VOLFIT_DESKTOP_MODE`` wins; the legacy ``VOLFIT_DESKTOP_NO_BROWSER=1`` maps
    to ``server`` (serve only, no UI). Default is the native pywebview window.
    """
    mode = os.environ.get("VOLFIT_DESKTOP_MODE", "").strip().lower()
    if mode in ("window", "browser", "server"):
        return mode
    if os.environ.get("VOLFIT_DESKTOP_NO_BROWSER", "").strip() == "1":
        return "server"
    return "window"


def _wait_until_up(host: str, port: int, timeout: float = 20.0) -> bool:
    """Block until the server accepts a connection (or ``timeout`` elapses)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _serve_in_thread(app, host: str, port: int):
    """Start uvicorn on a daemon thread, returning the ``Server`` + thread.

    A background server lets the pywebview GUI loop own the main thread (a hard
    requirement on Windows). ``server.should_exit = True`` stops it cleanly when
    the window closes; the daemon thread is reaped on process exit regardless.
    """
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    thread.start()
    return server, thread


def _find_icon() -> str | None:
    """Locate the app icon — bundled (``sys._MEIPASS``) or in the source tree."""
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "volfitter.ico")
    candidates.append(Path(__file__).resolve().parents[1] / "assets" / "volfitter.ico")
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _open_window(url: str) -> None:
    """Open the UI in a native pywebview window (blocks until it is closed).

    Raises if pywebview / its platform backend is unavailable, so the caller can
    fall back to the system browser.
    """
    import webview  # imported lazily so 'browser'/'server' modes need no GUI deps

    webview.create_window(
        "VolFitter",
        url,
        width=1480,
        height=920,
        min_size=(1100, 720),
        background_color="#0b1220",  # app dark ground — no white flash on load
    )
    icon = _find_icon()
    # `icon` is honoured on GTK/Qt; on the Windows EdgeChromium backend the
    # window/taskbar icon comes from the host exe (set in volfit.spec). Passing
    # it is harmless either way; guard for older signatures.
    try:
        webview.start(icon=icon) if icon else webview.start()
    except TypeError:
        webview.start()


def main() -> None:
    """Build the single-origin app and surface it per the launch mode."""
    _ensure_log_streams()
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
    mode = _launch_mode()
    print(f"VolFitter desktop [{mode}]: {url}")

    # 'server' mode: foreground uvicorn, no UI launch (smoke tests / headless).
    if mode == "server":
        uvicorn.run(app, host=HOST, port=port, log_level="info")
        return

    server, thread = _serve_in_thread(app, HOST, port)
    if not _wait_until_up(HOST, port):
        print("ERROR: server failed to bind — aborting UI launch.")
        server.should_exit = True
        return

    if mode == "window":
        try:
            _open_window(url)  # blocks until the window closes
            server.should_exit = True
            return
        except Exception as exc:  # pragma: no cover - GUI backend missing
            print(f"pywebview unavailable ({exc}); falling back to the browser.")

    # 'browser' mode (or window fallback): open the default browser, serve on.
    webbrowser.open(url)
    print("(Ctrl+C to quit)")
    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
