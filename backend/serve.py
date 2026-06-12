"""Dev server entry point for the volfit API.

Run from the repo root (volfit is pip-installed editable in .venv):
    .venv\\Scripts\\python backend\\serve.py

Provider selection via environment variables:
    VOLFIT_PROVIDER  "synthetic" (default) or "yahoo"
    VOLFIT_TICKERS   comma-separated watchlist for yahoo (default SPY,QQQ,AAPL)

Binds to 127.0.0.1:8000; the Vite frontend (localhost:5173) is CORS-allowed.
"""

import os

import uvicorn

from volfit.api.app import create_app


def build_app():
    """App with the env-selected provider (None keeps the synthetic default)."""
    provider = None
    name = os.environ.get("VOLFIT_PROVIDER", "synthetic").strip().lower()
    if name == "yahoo":
        from volfit.data.yahoo import YahooProvider

        raw = os.environ.get("VOLFIT_TICKERS", "SPY,QQQ,AAPL")
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
        provider = YahooProvider(tickers)
    app = create_app(provider=provider)
    live = app.state.volfit.provider.list_tickers()
    print(f"volfit API: provider={name} tickers={','.join(live)}")
    return app


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8000)
