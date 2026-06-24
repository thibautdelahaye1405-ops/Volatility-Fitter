"""Capture phase — freeze immutable NBBO chain fixtures from the quotes flat files.

For each (asset, trading-day) it reconstructs the 15:45-ET NBBO chain via
``QuotesFlatFileStore``, selects a standard expiry ladder, computes the
parity-implied forwards (de-biased for American exercise), and writes one JSON
fixture per (asset, date). The compute phase then replays these offline through a
``StaticProvider`` — so the slow, quota-bound S3 scan happens exactly once.

The daily S3 scan is shared across the whole watchlist (one ``COPY`` per day,
cached as a tiny Parquet), and the per-(asset, date) fixture is skipped if it
already exists, so the job is fully resumable.

Run (flat-file creds in env — dot-source restart.local.ps1):

    python -m backtest.capture --universe pilot --regimes spike_aug2024
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, time as time_of_day

from volfit.data.forwards import implied_forwards
from volfit.data.types import ChainSnapshot, OptionQuote

from backtest.quotes_store import QuotesFlatFileStore
from backtest.rest_quotes import RestQuotesClient
from backtest.universe import (
    FULL,
    PILOT,
    REGIME_WINDOWS,
    AssetSpec,
    all_option_roots,
    snapshot_utc,
    trading_days,
)

ROOT = os.path.dirname(__file__)
FIXTURE_DIR = os.path.join(ROOT, "fixtures")
CACHE_DIR = os.path.join(ROOT, "_cache")

# --- expiry-ladder selection -------------------------------------------------
MIN_DTE, MAX_DTE = 7, 400
MAX_EXPIRIES = 10
FRONT_WEEKLIES = 3


def _is_monthly(e: date) -> bool:
    """3rd-Friday monthly expiry (the standard listed cycle)."""
    return e.weekday() == 4 and 15 <= e.day <= 21


def select_expiries(available: list[date], as_of: date) -> list[date]:
    """A compact ladder: all in-range monthlies + the nearest few weeklies."""
    cand = sorted(e for e in available if MIN_DTE <= (e - as_of).days <= MAX_DTE)
    monthlies = [e for e in cand if _is_monthly(e)]
    chosen = set(monthlies)
    for e in (e for e in cand if not _is_monthly(e)):
        if len(chosen) >= len(monthlies) + FRONT_WEEKLIES:
            break
        chosen.add(e)
    return sorted(chosen)[:MAX_EXPIRIES]


# --- fixture (de)serialization ----------------------------------------------
def _quote_dict(q: OptionQuote) -> dict:
    return {
        "expiry": q.expiry.isoformat(),
        "strike": float(q.strike),
        "cp": q.call_put,
        "bid": None if q.bid is None else float(q.bid),
        "ask": None if q.ask is None else float(q.ask),
        "ask_size": None if q.open_interest is None else int(q.open_interest),
    }


def _build_fixture(asset: AssetSpec, as_of: date, chain: ChainSnapshot) -> dict | None:
    """Select expiries, resolve forwards, assemble the fixture payload (or None)."""
    expiries = select_expiries(chain.expiries(), as_of)
    if not expiries:
        return None
    want = set(expiries)
    kept = [q for q in chain.quotes if q.expiry in want]
    sub = ChainSnapshot(chain.ticker, chain.spot, chain.timestamp, kept, chain.exercise_style)
    fwds = implied_forwards(sub, reference_date=as_of)  # de-biased if American
    usable = [e for e in expiries if e in fwds]
    if not usable:
        return None
    return {
        "asset": asset.ticker,
        "as_of": as_of.isoformat(),
        "snapshot_ts_utc": chain.timestamp.isoformat(),
        "exercise_style": chain.exercise_style,
        "sector": asset.sector,
        "spot": float(chain.spot),
        "option_roots": list(asset.option_roots),
        "expiries": [e.isoformat() for e in usable],
        "forwards": {
            e.isoformat(): {
                "forward": float(fwds[e].forward),
                "discount": float(fwds[e].discount),
                "n_strikes": int(fwds[e].n_strikes),
                "residual_rms": float(fwds[e].residual_rms),
                "n_outliers": int(fwds[e].n_outliers),
            }
            for e in usable
        },
        "quotes": [_quote_dict(q) for q in kept if q.expiry in set(usable)],
    }


# --- nightly window ----------------------------------------------------------
def _parse_window(spec: str) -> tuple[time_of_day, time_of_day]:
    """Parse 'HH:MM-HH:MM' into (start, end) local times (may wrap midnight)."""
    a, b = spec.split("-")
    sh, sm = (int(x) for x in a.split(":"))
    eh, em = (int(x) for x in b.split(":"))
    return time_of_day(sh, sm), time_of_day(eh, em)


def _in_window(now: time_of_day, start: time_of_day, end: time_of_day) -> bool:
    """Is ``now`` inside [start, end]? Handles a window that wraps midnight."""
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end  # e.g. 23:30 .. 06:30


def _wait_for_window(start: time_of_day, end: time_of_day) -> None:
    """Block until the local clock is inside the window (checked each minute).

    Called only BETWEEN days, so a day already in progress always runs to
    completion (the scan can exceed the window — never killed mid-scan, which
    would waste the partial download since the cache writes only on COPY)."""
    announced = False
    while not _in_window(datetime.now().time(), start, end):
        if not announced:
            print(f"  [window] outside {start:%H:%M}-{end:%H:%M}; "
                  f"sleeping until the window opens (now {datetime.now():%H:%M})",
                  flush=True)
            announced = True
        time.sleep(60)


# --- driver ------------------------------------------------------------------
def _fixture_path(regime: str, as_of: date, ticker: str) -> str:
    return os.path.join(FIXTURE_DIR, regime, as_of.isoformat(), f"{ticker}.json")


def capture_day(fetch, assets: tuple[AssetSpec, ...], regime: str, as_of: date) -> dict:
    """Capture every asset for one trading day via ``fetch(asset, as_of) ->
    ChainSnapshot | None`` (rest or flat-file source); returns a cost record."""
    t0 = time.perf_counter()
    n_written = n_skipped = n_empty = 0
    for asset in assets:
        path = _fixture_path(regime, as_of, asset.ticker)
        if os.path.exists(path):
            n_skipped += 1
            continue
        chain = fetch(asset, as_of)
        fixture = _build_fixture(asset, as_of, chain) if chain is not None else None
        if fixture is None:
            n_empty += 1
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(fixture, fh)
        n_written += 1
    return {
        "regime": regime, "date": as_of.isoformat(),
        "scan_seconds": round(time.perf_counter() - t0, 1),
        "written": n_written, "skipped": n_skipped, "empty": n_empty,
    }


def _flatfile_fetch(assets: tuple[AssetSpec, ...]):
    """A fetch closure backed by the quotes_v1 flat files (the firehose)."""
    scan_roots = all_option_roots(assets)
    store = QuotesFlatFileStore(
        access_key=os.environ.get("VOLFIT_FLATFILES_KEY", ""),
        secret=os.environ.get("VOLFIT_FLATFILES_SECRET", ""),
        endpoint=os.environ.get("VOLFIT_FLATFILES_ENDPOINT", "files.massive.com"),
        cache_dir=CACHE_DIR,
    )
    if not store.available():
        raise SystemExit("flat-file creds missing — dot-source restart.local.ps1 first.")

    def fetch(asset: AssetSpec, as_of: date):
        return store.chain_at(
            asset.ticker, None, snapshot_utc(as_of),
            option_roots=list(asset.option_roots), cache_roots=scan_roots,
            exercise_style=asset.exercise_style,
        )

    return fetch


def _rest_fetch():
    """A fetch closure backed by the per-contract REST quotes API (fast path)."""
    client = RestQuotesClient(os.environ.get("VOLFIT_MASSIVE_KEY", ""))  # raises on a stub key

    def fetch(asset: AssetSpec, as_of: date):
        by_expiry = client.enumerate_contracts(list(asset.option_roots), as_of)
        selected = select_expiries(sorted(by_expiry), as_of)
        sub = {e: by_expiry[e] for e in selected if e in by_expiry}
        if not sub:
            return None
        return client.fetch_nbbo(asset.ticker, sub, snapshot_utc(as_of), asset.exercise_style)

    return fetch


def main() -> int:
    ap = argparse.ArgumentParser(description="Freeze NBBO chain fixtures for the backtest.")
    ap.add_argument("--universe", choices=["pilot", "full"], default="pilot")
    ap.add_argument("--regimes", default="spike_aug2024",
                    help="comma-separated regime names (default the spike window)")
    ap.add_argument("--limit-days", type=int, default=0, help="cap trading days (0 = all)")
    ap.add_argument("--dates", default=None,
                    help="comma-separated ISO dates overriding the regime window "
                         "(captured under the first --regimes name)")
    ap.add_argument("--window", default=None,
                    help="restrict scanning to a nightly local-time window, "
                         "e.g. '23:30-06:30'; a day in progress finishes, but no "
                         "new day starts outside it")
    ap.add_argument("--source", choices=["rest", "flatfile"], default="rest",
                    help="rest = per-contract REST quotes (fast, ~min/day); "
                         "flatfile = the quotes_v1 firehose (~hours/day)")
    args = ap.parse_args()
    window = _parse_window(args.window) if args.window else None

    assets = PILOT if args.universe == "pilot" else FULL
    fetch = _rest_fetch() if args.source == "rest" else _flatfile_fetch(assets)

    explicit = (
        [date.fromisoformat(d.strip()) for d in args.dates.split(",")]
        if args.dates else None
    )
    for regime in args.regimes.split(","):
        regime = regime.strip()
        if explicit is not None:
            days = explicit
        else:
            start, end = REGIME_WINDOWS[regime]
            days = trading_days(start, end)
        if args.limit_days:
            days = days[: args.limit_days]
        print(f"== {regime}: {len(days)} trading days, {len(assets)} assets "
              f"(source={args.source}) ==", flush=True)
        for d in days:
            # Skip the window wait when this day is already fully captured (cheap
            # resume) — only gate genuine scans.
            done = all(os.path.exists(_fixture_path(regime, d, a.ticker)) for a in assets)
            if window is not None and not done:
                _wait_for_window(*window)
            try:
                rec = capture_day(fetch, assets, regime, d)
                print(
                    f"  {rec['date']}  scan={rec['scan_seconds']:6.1f}s  "
                    f"written={rec['written']} skipped={rec['skipped']} empty={rec['empty']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - one bad day must not kill a multi-day job
                print(f"  {d}  FAILED: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
