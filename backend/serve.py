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
        "massive": MassiveProvider(tickers, api_key=os.environ.get("VOLFIT_MASSIVE_KEY", "").strip()),
        "synthetic": SyntheticProvider(reference_date=date.today(), tickers=tuple(tickers)),
    }


def _pick_active(providers: dict, forced: str) -> str:
    """The active source on launch: the forced one if valid, else the first
    reachable source in preference order (its feed_status isn't Red)."""
    if forced and forced in providers:
        return forced
    for sid in _AUTO_ORDER:
        if sid not in providers:
            continue
        try:
            level, _ = providers[sid].feed_status()
        except Exception:
            level = "red"
        if level != "red":
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
