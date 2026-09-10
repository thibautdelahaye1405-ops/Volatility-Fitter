"""Single-origin SYNTHETIC server for the frontend UI smoke (npm run smoke:ui).

Serves the built React bundle (frontend/dist) and the API from one process on
a dedicated port, with the offline SyntheticProvider and a throw-away
VOLFIT_DB (so the named universe / workspace stores are exercised too), so the
headless smoke drives a LIVE shell — fetch, calibrate, File ▸ Save as… /
Open… round trips — without touching the user's :8000 or any market feed.
Deterministic (pinned reference date), no scheduler, never gated.

    python backend/smoke_server.py --port 4188
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import date
from pathlib import Path

import uvicorn

from volfit.api.app import create_app
from volfit.api.frontend import find_frontend_dist, mount_frontend
from volfit.data.provider import SyntheticProvider

REF_DATE = date(2026, 8, 27)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=4188)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=None,
                    help="serve a PREPARED store instead of a throw-away one (a series "
                         "evidence check: the store already holds the series)")
    ap.add_argument("--tickers", default=None,
                    help="comma-separated synthetic universe (default: the provider's own)")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="volfit_smoke_"))
    tickers = tuple(t.strip().upper() for t in args.tickers.split(",")) if args.tickers else None
    provider = (SyntheticProvider(reference_date=REF_DATE, tickers=tickers) if tickers
                else SyntheticProvider(reference_date=REF_DATE))
    app = create_app(
        reference_date=REF_DATE,
        providers={"synthetic": provider},
        active_source="synthetic",
        store_path=args.db or str(tmp / "smoke.sqlite"),
    )
    if not mount_frontend(app):
        raise SystemExit("no frontend/dist bundle — run `npm run build` in frontend/ first")
    print(f"smoke server: frontend={find_frontend_dist()} db={args.db or tmp} port={args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
