"""Q2 demo: 0DTE calibration on SPY (2026-09-22) and NVDA (2026-09-18) at four
intraday instants, fetched as-of through Massive's per-contract NBBO history
(the Smile lens's as-of path), calibrated IN-PROCESS on a detached AppState
(the replay pattern of backtest/validate_intraday_clock.py + series_lanes).

Run from backend\ :  ..\.venv\Scripts\python <this file> [--no-fetch]

The provider subclass below fixes ONE thing the app's provider cannot do on a
later day: list contracts AS OF the past day (the app's `_intraday_contracts`
queries `expired=false` without `as_of`, so a same-day expiry that has since
expired never enters the ladder). Nothing else is changed.
Chains are cached as pickles in the scratchpad so the calibration part can be
re-run without refetching.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import re
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = r"C:\Users\thiba\vol-fitter\restart.local.ps1"


def load_secrets() -> None:
    """Export the $env:NAME = '...' assignments of restart.local.ps1 (never printed)."""
    text = open(SECRETS, encoding="utf-8").read()
    for name, val in re.findall(r"\$env:([A-Z_]+)\s*=\s*['\"]([^'\"]*)['\"]", text):
        os.environ.setdefault(name, val)


load_secrets()
os.environ["VOLFIT_CALIB_WORKERS"] = "1"

from volfit.data.massive import MassiveProvider, _iso_date  # noqa: E402
from volfit.data.fieldmap import price_or_none  # noqa: E402
from volfit.data.provider import AsOf  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def et(day: date, hh: int, mm: int) -> datetime:
    """An ET wall instant as UTC-naive (the codebase convention)."""
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET).astimezone(UTC).replace(tzinfo=None)


class AsOfMassive(MassiveProvider):
    """The app's provider + contract discovery AS OF the requested day."""

    asof_day: date | None = None

    def _intraday_contracts(self, ticker, expiries):
        day = self.asof_day
        if day is None:
            return super()._intraday_contracts(ticker, expiries)
        key = (ticker.upper(), frozenset(expiries) if expiries else None, day)
        cached = self._contracts_cache.get(key)
        if cached is not None:
            return cached
        wanted = set(expiries) if expiries else None
        out, seen = [], set()
        for expired in ("true", "false"):
            params = {
                "underlying_ticker": self._underlying(ticker), "as_of": day.isoformat(),
                "expired": expired, "order": "asc", "sort": "expiration_date", "limit": 1000,
                "expiration_date.gte": day.isoformat(),
            }
            if wanted:
                params["expiration_date.lte"] = max(wanted).isoformat()
            for c in self._paginate("/v3/reference/options/contracts", params):
                expiry = _iso_date(c.get("expiration_date"))
                opt = c.get("ticker")
                cp = {"call": "C", "put": "P"}.get(c.get("contract_type"))
                strike = price_or_none(c.get("strike_price"))
                if expiry is None or opt is None or cp is None or strike is None or opt in seen:
                    continue
                if wanted is not None and expiry not in wanted:
                    continue
                seen.add(opt)
                out.append({"ticker": opt, "expiry": expiry, "strike": strike,
                            "call_put": cp, "style": str(c.get("exercise_style", "")).lower()})
        self._contracts_cache[key] = out
        return out


PLAN = {
    "SPY": (date(2026, 9, 22), [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 10, 16)]),
    "NVDA": (date(2026, 9, 18), [date(2026, 9, 18), date(2026, 9, 25), date(2026, 10, 16)]),
}
INSTANTS = [(10, 0), (12, 30), (14, 30), (15, 45)]


def fetch_all() -> dict:
    key = os.environ.get("VOLFIT_MASSIVE_KEY", "")
    assert key, "no VOLFIT_MASSIVE_KEY"
    prov = AsOfMassive(list(PLAN), api_key=key, hist_nbbo=True)
    chains = {}
    for ticker, (day, ladder) in PLAN.items():
        prov.asof_day = day
        for hh, mm in INSTANTS:
            ts = et(day, hh, mm)
            t0 = time.perf_counter()
            chain = prov.fetch_chain(ticker, ladder, as_of=AsOf(mode="intraday", ts=ts))
            wall = time.perf_counter() - t0
            per_exp = {}
            for q in chain.quotes:
                per_exp[q.expiry.isoformat()] = per_exp.get(q.expiry.isoformat(), 0) + 1
            print(f"FETCH {ticker} {day} {hh:02d}:{mm:02d} ET -> ts={chain.timestamp} spot={chain.spot:.2f} "
                  f"quotes={len(chain.quotes)} per-expiry={per_exp} kind={chain.quote_kind} "
                  f"settlement={'yes' if chain.settlement else 'no'} gate={prov.nbbo_history_gate()} "
                  f"wall={wall:.1f}s", flush=True)
            chains[(ticker, ts)] = chain
    with open(os.path.join(HERE, "q2_chains.pkl"), "wb") as fh:
        pickle.dump(chains, fh)
    return chains


def calibrate_all(chains: dict) -> list[dict]:
    from volfit.api import service
    from volfit.api.quality import build_quality_report
    from volfit.api.state import AppState
    from volfit.calib.intraday_time import intraday_variance_days
    from volfit.data.expiry_time import default_settlement
    from volfit.models.lqd.atm import atm_handles
    from volfit.replay_report import _StoredChains
    import numpy as np

    rows = []
    for (ticker, ts), chain in sorted(chains.items()):
        state = AppState(ts.date(), provider=_StoredChains({ticker: chain}))
        ladder = sorted(chain.expiries())
        state.set_expiries(ticker, ladder)
        opts = state.options()  # the app's defaults
        # --- the app's DEFAULT options (intradayClock OFF) on the same-day rung
        same_day = ts.date()
        default_note = ""
        if same_day in ladder:
            try:
                p = service.prepared_quotes(state, ticker, same_day)
                rec = service.calibrate_node(state, ticker, same_day.isoformat(), opts.fitMode)
                default_note = (f"OFF-clock fit: t={p.t*365:.4f}d nQ={p.k.size} "
                                f"maxErr={rec.result.max_iv_error*1e4:.0f}bp success={rec.result.success}")
            except Exception as exc:  # noqa: BLE001
                default_note = f"OFF-clock: {type(exc).__name__}: {str(exc)[:90]}"
        # --- the intraday clock ON (the 0DTE research clock), everything else default
        state.set_options(opts.model_copy(update={"intradayClock": True}))
        parity = state.forwards(ticker)
        for expiry in ladder:
            iso = expiry.isoformat()
            settle = (chain.settlement or {}).get(expiry)
            settle_ts = settle.settle if settle is not None else default_settlement(expiry, ticker).settle
            hours_to_settle = (settle_ts - ts).total_seconds() / 3600.0
            legacy_days = state.year_fraction(expiry) * 365.0
            row = {"ticker": ticker, "ts_utc": ts.isoformat(), "et": ts.replace(tzinfo=UTC).astimezone(ET).strftime("%H:%M"),
                   "expiry": iso, "settle_utc": settle_ts.isoformat(), "hours_to_settle": round(hours_to_settle, 3),
                   "legacy_days": legacy_days, "spot": chain.spot, "raw_quotes": sum(q.expiry == expiry for q in chain.quotes)}
            if expiry not in parity:
                row["status"] = "SKIPPED no parity forward"
                rows.append(row); print(row, flush=True); continue
            prepared, reason = service.prepare_slice_or_reason(state, ticker, iso)
            if prepared is None:
                row["status"] = f"DEGRADED {reason}"
                rows.append(row); print(row, flush=True); continue
            t0 = time.perf_counter()
            try:
                rec = service.calibrate_node(state, ticker, iso, opts.fitMode)
            except Exception as exc:  # noqa: BLE001
                row["status"] = f"FAILED {type(exc).__name__}: {str(exc)[:120]}"
                rows.append(row); print(row, flush=True); continue
            wall = time.perf_counter() - t0
            res = rec.result
            tau = float(prepared.tau)
            k = np.asarray(prepared.k, float)
            model = np.array([float(res.slice.implied_vol(float(x), tau)) for x in k])
            resid = model - np.asarray(prepared.iv_mid, float)
            below = np.asarray(prepared.iv_bid) - model
            above = model - np.asarray(prepared.iv_ask)
            band_exc = float(max(0.0, np.max(np.maximum(below, above)))) * 1e4
            h = atm_handles(res.slice, tau)
            vec = np.asarray(res.params.to_vector(), float)
            # the research clock reading, for the narrative only (no fit)
            research = intraday_variance_days(ts, settle_ts, 0.60, 0.0)
            row.update({
                "status": "OK" if res.success else "OK(no-converge-flag)",
                "t_exact_days": float(prepared.t) * 365.0, "tau_days": tau * 365.0,
                "tau_research_days_share0.6_w0": research,
                "nQ": int(k.size), "screened": len(prepared.screened), "vega_floored": int(prepared.vega_floored),
                "k_min": float(k.min()), "k_max": float(k.max()),
                "rms_bp": float(np.sqrt(np.mean(resid**2))) * 1e4,
                "max_err_bp": float(res.max_iv_error) * 1e4, "band_excess_bp": band_exc,
                "atm_vol": float(h.sigma0), "skew": float(h.skew),
                "atm_total_var": float(h.sigma0) ** 2 * tau,
                "finite": bool(np.all(np.isfinite(vec)) and math.isfinite(h.sigma0)),
                "n_params": int(vec.size), "n_eval": int(res.n_evaluations),
                "forward": float(prepared.forward), "discount": float(prepared.discount),
                "wall_ms": wall * 1e3,
            })
            if expiry == same_day:
                row["default_options_note"] = default_note
            rows.append(row)
            print({k_: (round(v, 4) if isinstance(v, float) else v) for k_, v in row.items()}, flush=True)
        # the desk's Quality report on this state (calendar / wings / readiness)
        try:
            rep = build_quality_report(state, opts.fitMode)
            for node in rep.nodes:
                d = node.model_dump()
                keep = {k_: d[k_] for k_ in ("expiry", "ready", "calendarOk", "wingsClean", "issues", "degraded",
                                             "rmsBp", "maxIvErrBp", "nQuotes") if k_ in d}
                print("QUALITY", ticker, ts, keep, flush=True)
                for r in rows:
                    if r["ticker"] == ticker and r["ts_utc"] == ts.isoformat() and r["expiry"] == d.get("expiry"):
                        r["quality"] = keep
        except Exception as exc:  # noqa: BLE001
            print("QUALITY failed", ticker, ts, type(exc).__name__, str(exc)[:200], flush=True)
    with open(os.path.join(HERE, "q2_results.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, default=str)
    return rows


if __name__ == "__main__":
    if "--no-fetch" in sys.argv:
        with open(os.path.join(HERE, "q2_chains.pkl"), "rb") as fh:
            chains = pickle.load(fh)
    else:
        chains = fetch_all()
    calibrate_all(chains)
