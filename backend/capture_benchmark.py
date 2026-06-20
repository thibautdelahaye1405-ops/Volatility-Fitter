"""Capture a static Bloomberg option-chain benchmark for the local-vol fit.

Pulls the exact (ticker, expiry) set the user uses to regression-test the
Local-Vol calibration (SPY 5 expiries, NVDA 3) into a self-contained JSON
fixture, so the fit can be reproduced — and diagnosed — OFFLINE, without a
Terminal. Captures the raw NBBO chain (the unit the whole pipeline runs on),
the spot, the exercise style, and the dividend schedule (for the forward /
de-Americanization model).

Run on a machine with the Bloomberg Terminal up (one billable fetch):

    ..\\.venv\\Scripts\\python backend\\capture_benchmark.py

Writes backend/tests/fixtures/lv_benchmark_bloomberg.json.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from volfit.data.bloomberg import BloombergProvider

#: The benchmark universe: the user's SPY + NVDA expiries (3rd-Friday monthlies).
BENCHMARK = {
    "SPY": [date(2026, 7, 17), date(2026, 8, 21), date(2026, 9, 18),
            date(2026, 12, 18), date(2027, 6, 17)],
    "NVDA": [date(2026, 7, 17), date(2026, 9, 18), date(2026, 12, 18)],
}

OUT = Path(__file__).resolve().parent / "tests" / "fixtures" / "lv_benchmark_bloomberg.json"


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


def capture() -> dict:
    payload: dict = {"source": "bloomberg", "captured_utc": None, "tickers": {}}
    for ticker, expiries in BENCHMARK.items():
        provider = BloombergProvider([ticker])
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
    return payload


def main() -> int:
    payload = capture()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    total = sum(len(t["quotes"]) for t in payload["tickers"].values())
    print(f"\nwrote {OUT} ({total} quotes across {len(payload['tickers'])} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
