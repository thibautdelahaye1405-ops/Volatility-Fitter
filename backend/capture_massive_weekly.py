"""Capture a short-dated SPY chain from Massive (live, delayed tier) for the
Local-Vol SHORT-EXPIRY diagnosis.

The Bloomberg benchmark fixture has no expiry shorter than ~27d, so it cannot
reproduce the reported 1-week LV failure (see the Phase 0 finding). This pulls a
real ladder INCLUDING two true weeklies (the user's 2026-07-01 / 2026-07-06)
plus the longer monthlies that stretch the shared strike axis (the very mechanism
of the short-end strike under-resolution), into the same JSON shape as
lv_benchmark_bloomberg.json — so ``lv_benchmark.py --fixture`` can run the Phase 0
diagnostic on a genuine short-dated surface, offline and reproducibly.

Needs ``VOLFIT_MASSIVE_KEY`` (dot-source restart.local.ps1 first). One live fetch:

    ..\\.venv\\Scripts\\python backend\\capture_massive_weekly.py

Writes backend/tests/fixtures/lv_weekly_massive.json (carries ``as_of`` = the
capture date, so year fractions measure the true DTE).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from volfit.data.massive import MassiveProvider

#: SPY ladder: the two requested weeklies + the longer monthlies (the long end is
#: what widens the shared strike axis — needed to reproduce the under-resolution).
WEEKLY = {
    "SPY": [
        date(2026, 7, 1), date(2026, 7, 6),  # the true weeklies under test
        date(2026, 7, 17), date(2026, 8, 21), date(2026, 9, 18),
        date(2026, 12, 18), date(2027, 6, 17),
    ],
}

OUT = Path(__file__).resolve().parent / "tests" / "fixtures" / "lv_weekly_massive.json"


def _quote_dict(q) -> dict:
    return {
        "expiry": q.expiry.isoformat(),
        "strike": float(q.strike),
        "cp": q.call_put,
        "bid": None if q.bid is None else float(q.bid),
        "ask": None if q.ask is None else float(q.ask),
        "last": None if q.last is None else float(q.last),
        "volume": None if q.volume is None else int(q.volume),
        "oi": None if q.open_interest is None else int(q.open_interest),
    }


def capture(as_of: date) -> dict:
    key = os.environ.get("VOLFIT_MASSIVE_KEY")
    if not key:
        raise SystemExit("set VOLFIT_MASSIVE_KEY (dot-source restart.local.ps1 first)")
    payload: dict = {"source": "massive", "as_of": as_of.isoformat(), "captured_utc": None, "tickers": {}}
    for ticker, expiries in WEEKLY.items():
        provider = MassiveProvider([ticker], api_key=key)
        chain = provider.fetch_chain(ticker, expiries=expiries)
        try:
            divs = provider.dividend_schedule(ticker)
        except Exception:
            divs = ()
        payload["tickers"][ticker] = {
            "spot": float(chain.spot),
            "timestamp": chain.timestamp.isoformat(),
            "exercise_style": chain.exercise_style,
            "expiries": [e.isoformat() for e in expiries],
            "dividends": [
                {"ex_date": d.ex_date.isoformat(), "amount": float(d.amount)} for d in divs
            ],
            "quotes": [_quote_dict(q) for q in chain.quotes],
        }
        payload["captured_utc"] = chain.timestamp.isoformat()
        n2 = sum(1 for q in chain.quotes if q.mid is not None)
        print(
            f"{ticker}: spot {chain.spot:.2f}, {len(chain.quotes)} quotes "
            f"({n2} two-sided), {len(chain.expiries())} expiries, "
            f"{chain.exercise_style}, {len(divs)} dividends"
        )
        provider.close()
    return payload


def main() -> int:
    payload = capture(date.today())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    total = sum(len(t["quotes"]) for t in payload["tickers"].values())
    print(f"\nwrote {OUT} ({total} quotes, as_of {payload['as_of']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
