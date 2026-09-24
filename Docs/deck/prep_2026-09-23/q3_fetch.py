"""Q3 (speed): time the raw-data fetches for SPY and pickle the chains.

Run from backend\ :  ..\.venv\Scripts\python <this file>

Times, in this order (serially, one process):
  1. Massive: available_expiries (contract listing) + the live NBBO snapshot for
     a ~10-expiry ladder, then the WHOLE listed chain (every expiry <= 730 d);
  2. Cboe delayed JSON: the whole chain (one CDN file) — the ladder is a subset;
  3. Yahoo (yfinance): the default 8-expiry chain;
  4. Massive as-of history (per-contract NBBO at 2026-09-22 15:45 ET) for the
     same ladder — the ~12 s path of the docs, measured once.
Chains are pickled to q3_chains.pkl for the offline calibration timings.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = r"C:\Users\thiba\vol-fitter\restart.local.ps1"


def load_secrets() -> None:
    text = open(SECRETS, encoding="utf-8").read()
    for name, val in re.findall(r"\$env:([A-Z_]+)\s*=\s*['\"]([^'\"]*)['\"]", text):
        os.environ.setdefault(name, val)


load_secrets()
os.environ["VOLFIT_CALIB_WORKERS"] = "1"

from volfit.data.massive import MassiveProvider  # noqa: E402
from volfit.data.provider import AsOf  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICKER = "SPY"


def et(day: date, hh: int, mm: int) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET).astimezone(UTC).replace(tzinfo=None)


def summarize(chain) -> dict:
    per = {}
    two_sided = 0
    for q in chain.quotes:
        per[q.expiry.isoformat()] = per.get(q.expiry.isoformat(), 0) + 1
        if q.bid is not None and q.ask is not None and q.bid > 0 and q.ask > 0:
            two_sided += 1
    return {"spot": chain.spot, "timestamp": str(chain.timestamp), "quotes": len(chain.quotes),
            "two_sided": two_sided, "expiries": len(per), "per_expiry": per,
            "style": chain.exercise_style, "kind": chain.quote_kind}


def pick_ladder(avail: list[date], today: date) -> list[date]:
    """~10 rungs: the next 3 Fridays (>= 2 days out), then the third Fridays
    (monthlies) out to ~1 year. No 0-2-day dailies (they set the LV lattice step)."""
    fridays = [e for e in avail if e.weekday() == 4 and (e - today).days >= 2]
    weekly = fridays[:3]
    monthly = [e for e in fridays if 15 <= e.day <= 21 and e not in weekly and (e - today).days <= 400]
    ladder = sorted(set(weekly + monthly))[:10]
    return ladder


def main() -> None:
    key = os.environ.get("VOLFIT_MASSIVE_KEY", "")
    assert key, "no VOLFIT_MASSIVE_KEY"
    timings: dict = {}
    chains: dict = {}
    today = date.today()

    prov = MassiveProvider([TICKER], api_key=key, hist_nbbo=True,
                           ws_url=os.environ.get("VOLFIT_MASSIVE_WS_URL") or None)
    t0 = time.perf_counter()
    avail = prov.available_expiries(TICKER)
    timings["massive_available_expiries_s"] = time.perf_counter() - t0
    print(f"Massive lists {len(avail)} expiries in {timings['massive_available_expiries_s']:.2f}s; "
          f"first {[e.isoformat() for e in avail[:6]]}", flush=True)
    ladder = pick_ladder(avail, today)
    print("LADDER", [e.isoformat() for e in ladder], flush=True)

    # 1a. Massive live snapshot, the ladder
    t0 = time.perf_counter()
    live = prov.fetch_chain(TICKER, ladder)
    timings["massive_live_ladder_s"] = time.perf_counter() - t0
    chains["massive_live"] = live
    print("MASSIVE LIVE ladder", f"{timings['massive_live_ladder_s']:.2f}s", summarize(live), flush=True)
    # 1b. Massive live snapshot again (warm HTTP keep-alive)
    t0 = time.perf_counter()
    live2 = prov.fetch_chain(TICKER, ladder)
    timings["massive_live_ladder_2nd_s"] = time.perf_counter() - t0
    print("MASSIVE LIVE ladder (2nd)", f"{timings['massive_live_ladder_2nd_s']:.2f}s", len(live2.quotes), flush=True)
    # 1c. Massive live snapshot, the WHOLE listed chain
    t0 = time.perf_counter()
    try:
        whole = prov.fetch_chain(TICKER, None)
        timings["massive_live_whole_s"] = time.perf_counter() - t0
        s = summarize(whole)
        s.pop("per_expiry")
        print("MASSIVE LIVE whole chain", f"{timings['massive_live_whole_s']:.2f}s", s, flush=True)
        timings["massive_live_whole_quotes"] = len(whole.quotes)
        timings["massive_live_whole_expiries"] = s["expiries"]
    except Exception as exc:  # noqa: BLE001
        timings["massive_live_whole_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print("MASSIVE LIVE whole chain FAILED", timings["massive_live_whole_error"], flush=True)

    # 2. Cboe delayed (one CDN JSON = the whole chain)
    try:
        from volfit.data.cboe import CboeAdapter
        from volfit.data.exchange import ExchangeChainProvider
        cboe = ExchangeChainProvider([TICKER], CboeAdapter())
        t0 = time.perf_counter()
        cb_whole = cboe.fetch_chain(TICKER)
        timings["cboe_whole_s"] = time.perf_counter() - t0
        s = summarize(cb_whole)
        s.pop("per_expiry")
        print("CBOE whole chain", f"{timings['cboe_whole_s']:.2f}s", s, flush=True)
        timings["cboe_whole_quotes"] = len(cb_whole.quotes)
        timings["cboe_whole_expiries"] = s["expiries"]
        t0 = time.perf_counter()
        cb_ladder = cboe.fetch_chain(TICKER, ladder)  # cached raw chain -> the subset
        timings["cboe_ladder_from_cache_s"] = time.perf_counter() - t0
        chains["cboe"] = cb_ladder
        print("CBOE ladder (from the cached raw chain)", f"{timings['cboe_ladder_from_cache_s']:.3f}s",
              summarize(cb_ladder), flush=True)
    except Exception as exc:  # noqa: BLE001
        timings["cboe_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print("CBOE FAILED", timings["cboe_error"], flush=True)

    # 3. Yahoo (yfinance), default 8 expiries
    try:
        from volfit.data.yahoo import YahooProvider
        yh = YahooProvider([TICKER])
        t0 = time.perf_counter()
        y_chain = yh.fetch_chain(TICKER)
        timings["yahoo_default_s"] = time.perf_counter() - t0
        chains["yahoo"] = y_chain
        print("YAHOO default chain", f"{timings['yahoo_default_s']:.2f}s", summarize(y_chain), flush=True)
    except Exception as exc:  # noqa: BLE001
        timings["yahoo_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print("YAHOO FAILED", timings["yahoo_error"], flush=True)

    # 4. Massive as-of history: the ladder at 2026-09-22 15:45 ET (past day -> NBBO history)
    ts = et(date(2026, 9, 22), 15, 45)
    t0 = time.perf_counter()
    try:
        asof = prov.fetch_chain(TICKER, ladder, as_of=AsOf(mode="intraday", ts=ts))
        timings["massive_asof_ladder_s"] = time.perf_counter() - t0
        chains["massive_asof"] = asof
        print("MASSIVE AS-OF ladder", f"{timings['massive_asof_ladder_s']:.2f}s", summarize(asof),
              "gate=", prov.nbbo_history_gate(), flush=True)
    except Exception as exc:  # noqa: BLE001
        timings["massive_asof_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print("MASSIVE AS-OF FAILED", timings["massive_asof_error"], flush=True)

    with open(os.path.join(HERE, "q3_chains.pkl"), "wb") as fh:
        pickle.dump({"ladder": ladder, "chains": chains, "timings": timings, "today": today}, fh)
    with open(os.path.join(HERE, "q3_fetch_timings.json"), "w", encoding="utf-8") as fh:
        json.dump({"ladder": [e.isoformat() for e in ladder], "timings": timings,
                   "summaries": {k: summarize(v) for k, v in chains.items()}}, fh, indent=1, default=str)
    print("DONE", json.dumps(timings, indent=1), flush=True)


if __name__ == "__main__":
    main()
