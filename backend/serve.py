"""Dev server entry point for the volfit API.

Run from the repo root (volfit is pip-installed editable in .venv):
    .venv\\Scripts\\python backend\\serve.py

All four data sources are registered so the in-app Data Source selector can
switch between them at runtime; the *active* one on launch is chosen below.

Environment variables:
    VOLFIT_PROVIDER  Force the active source on launch ("synthetic", "yahoo",
                     "bloomberg", "massive"). Unset (default) = best-reachable
                     auto-pick (bloomberg -> yahoo -> massive -> synthetic).
    VOLFIT_TICKERS   comma-separated watchlist (default SPY,QQQ,AAPL)
    VOLFIT_MASSIVE_KEY  Massive API key; without it Massive shows Red.
    VOLFIT_DB        SQLite path for fit-history persistence (every fit is
                     recorded keyed by snapshot timestamp; GET /history/...).
                     Unset by default: no on-disk side effects unless opted in.

Binds to 127.0.0.1:8000; the Vite frontend (localhost:5173) is CORS-allowed.
"""

import os
import threading
import time

import uvicorn

from volfit.api.app import create_app

#: Preference order for the best-reachable auto-pick (richest feed first).
_AUTO_ORDER = ("bloomberg", "yahoo", "massive", "synthetic")


def _watchlist() -> list[str]:
    """Parse the comma-separated VOLFIT_TICKERS watchlist (default SPY,QQQ,AAPL)."""
    raw = os.environ.get("VOLFIT_TICKERS", "SPY,QQQ,AAPL")
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _build_providers() -> dict:
    """Register every configurable data source over the watchlist.

    All four sources are always registered so the selector lists them with a
    status light each — Bloomberg reports Red without a Terminal, Massive Red
    without VOLFIT_MASSIVE_KEY. Provider construction never touches the network
    (only the status probe and chain fetch do), so registering all four is cheap.
    """
    from datetime import date

    from volfit.data.bloomberg import BloombergProvider
    from volfit.data.massive import MassiveProvider
    from volfit.data.provider import SyntheticProvider
    from volfit.data.yahoo import YahooProvider

    tickers = _watchlist()
    return {
        "yahoo": YahooProvider(tickers),
        "bloomberg": BloombergProvider(tickers),
        "massive": MassiveProvider(
            tickers,
            api_key=os.environ.get("VOLFIT_MASSIVE_KEY", "").strip(),
            ws_url=(os.environ.get("VOLFIT_MASSIVE_WS_URL", "").strip() or None),
            flat_store=_flat_store(),
        ),
        "synthetic": SyntheticProvider(reference_date=date.today(), tickers=tuple(tickers)),
    }


def _flat_store():
    """Build the Massive/Polygon flat-file history store from the environment
    (ROADMAP Tier 2), or None when no S3 credentials are configured.

    Env: ``VOLFIT_FLATFILES_KEY`` / ``VOLFIT_FLATFILES_SECRET`` (the S3 Access Key
    ID + Secret for the flat-file bucket); optional ``VOLFIT_FLATFILES_ENDPOINT`` /
    ``_BUCKET`` / ``_PREFIX`` overrides; ``VOLFIT_FLATFILES_CACHE`` for the local
    Parquet day-cache (defaults under the OS temp dir, persisted across restarts)."""
    import tempfile

    from volfit.data.flatfiles import (
        DEFAULT_BUCKET,
        DEFAULT_ENDPOINT,
        DEFAULT_PREFIX,
        FlatFileStore,
    )

    key = os.environ.get("VOLFIT_FLATFILES_KEY", "").strip()
    secret = os.environ.get("VOLFIT_FLATFILES_SECRET", "").strip()
    if not (key and secret):
        return None
    cache = os.environ.get("VOLFIT_FLATFILES_CACHE", "").strip() or os.path.join(
        tempfile.gettempdir(), "volfit_flatfiles"
    )
    return FlatFileStore(
        access_key=key,
        secret=secret,
        endpoint=os.environ.get("VOLFIT_FLATFILES_ENDPOINT", "").strip() or DEFAULT_ENDPOINT,
        bucket=os.environ.get("VOLFIT_FLATFILES_BUCKET", "").strip() or DEFAULT_BUCKET,
        prefix=os.environ.get("VOLFIT_FLATFILES_PREFIX", "").strip() or DEFAULT_PREFIX,
        cache_dir=cache,
    )


def _bounded(fn, timeout: float, default):
    """Run ``fn`` on a daemon thread, returning its result or ``default`` if it
    raises or exceeds ``timeout`` — so a slow/hanging provider probe can never
    block startup (this all runs BEFORE uvicorn binds)."""
    box = [default]

    def _run() -> None:
        try:
            box[0] = fn()
        except Exception:
            box[0] = default

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout)
    return box[0] if not thread.is_alive() else default


def _probe_level(provider, timeout: float = 4.0) -> str:
    """``feed_status`` level for a provider, bounded against a hanging probe."""
    return _bounded(lambda: provider.feed_status()[0], timeout, "red")


def _can_serve(provider, attempts: int = 3, gap: float = 1.2, timeout: float = 4.0) -> bool:
    """Whether a source can actually RESOLVE a non-empty expiry ladder for its
    first ticker — a startup-only data probe, so a connected-but-capped/gated feed
    (Bloomberg at its daily reference-data limit) is skipped in favour of one that
    truly serves. ``feed_status`` alone can't tell them apart now that it's a
    cheap connectivity check (it must not burn the Bloomberg quota every poll).

    Retries a few times with a short gap so a transient throttle — Yahoo
    rate-limiting a fresh process — does not cause a false skip; a hard refusal
    (a capped/gated feed) fails every attempt and is skipped. The probe shares the
    provider instance the app uses, so a successful chain enumeration warms its
    cache rather than costing an extra request.
    """
    tickers = provider.list_tickers()
    if not tickers:
        return False
    for i in range(attempts):
        if _bounded(lambda: bool(provider.available_expiries(tickers[0])), timeout, False):
            return True
        if i < attempts - 1:
            time.sleep(gap)
    return False


def _pick_active(providers: dict, forced: str) -> str:
    """The active source on launch: the forced one if valid, else the first
    source in preference order that is reachable AND can actually serve data.

    A connected feed that can't resolve a ladder (Bloomberg at its daily cap) is
    skipped, so a restart lands on a source that works (typically Yahoo) instead
    of an empty surface. Synthetic always serves and is the final fallback. Every
    probe is time-bounded so no single source can stall startup.
    """
    if forced and forced in providers:
        return forced
    for sid in _AUTO_ORDER:
        if sid not in providers:
            continue
        if sid == "synthetic":
            return sid  # offline fallback always serves
        if _probe_level(providers[sid]) == "red":
            continue  # unreachable: skip fast (no data probe)
        if _can_serve(providers[sid]):
            return sid
    return "synthetic"


def build_app():
    """App with all data sources registered and a best-reachable active one."""
    providers = _build_providers()
    forced = os.environ.get("VOLFIT_PROVIDER", "").strip().lower()
    active = _pick_active(providers, forced)
    store_path = os.environ.get("VOLFIT_DB") or None  # opt-in fit history
    app = create_app(
        providers=providers, active_source=active, store_path=store_path,
        enable_scheduler=True,  # the live server runs the timed spot/options fetcher
        gated=True,  # trigger-gated: fetch only on the Fetch button, fit only on Calibrate
    )
    if active == "bloomberg":
        _seed_bloomberg_dividends(app.state.volfit, providers["bloomberg"])
    live = app.state.volfit.provider.list_tickers()
    print(
        f"volfit API: active={active} sources={','.join(providers)} "
        f"tickers={','.join(live)} db={store_path}"
    )
    return app


def _seed_bloomberg_dividends(state, provider) -> None:
    """Best-effort: import each watchlist ticker's Bloomberg dividend schedule
    into its market settings, so the discrete-dividend forward/de-Am model is
    populated from real data. Any failure is swallowed (continuous-yield stays).
    """
    from volfit.api.schemas import MarketSettings

    for ticker in provider.list_tickers():
        try:
            schedule = provider.dividend_schedule(ticker, state.reference_date)
        except Exception:
            continue
        if not schedule:
            continue
        try:
            current = state.market_settings(ticker)
            updated = MarketSettings(
                rate=current.rate,
                dividendMode="discrete_absolute",
                dividendYield=current.dividendYield,
                dividends=[
                    {"exDate": d.ex_date.isoformat(), "amount": d.amount}
                    for d in schedule
                ],
                switchYears=current.switchYears,
            )
            state.set_market_settings(ticker, updated)
        except Exception:
            continue


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8000)
