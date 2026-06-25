"""Offline Local-Vol benchmark harness over the static Bloomberg fixture.

Loads tests/fixtures/lv_benchmark_bloomberg.json (captured by capture_benchmark.py)
and runs the REAL affine local-vol calibration against it through an in-memory
``StaticProvider`` — so the SPY/NVDA fit can be reproduced and diagnosed without a
Terminal, with default hyperparameters (the user's "current default").

Run:

    ..\\.venv\\Scripts\\python backend\\lv_benchmark.py            # default settings
    ..\\.venv\\Scripts\\python backend\\lv_benchmark.py --rate 0.045 --theoretical

Prints per-expiry weighted RMS vol error (bp), the worst-quote error, and the
fit's bound/eval diagnostics. This is the regression benchmark the user asked
for: a fixed quote set with a known good fit quality.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from volfit.api.affine_fit import (
    calibrate_affine_surface,
    last_affine_diagnostics,
    last_affine_expiry_diagnostics,
)
from volfit.api.schemas import ForwardPolicy, MarketSettings
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.schemas_market import DividendSpec
from volfit.api.state import AppState
from volfit.data.provider import OptionChainProvider
from volfit.data.types import ChainSnapshot, OptionQuote

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "lv_benchmark_bloomberg.json"
#: The capture instant; year fractions are measured from this date.
AS_OF = date(2026, 6, 20)


class StaticProvider(OptionChainProvider):
    """Serves the captured chains from memory (no network / Terminal)."""

    def __init__(self, chains: dict[str, ChainSnapshot]) -> None:
        self._chains = chains

    def list_tickers(self) -> list[str]:
        return list(self._chains)

    def available_expiries(self, ticker: str) -> list[date]:
        return self._chains[ticker].expiries()

    def fetch_chain(self, ticker, expiries=None, as_of=None) -> ChainSnapshot:
        ch = self._chains[ticker]
        if expiries:
            want = set(expiries)
            kept = [q for q in ch.quotes if q.expiry in want]
            return ChainSnapshot(ch.ticker, ch.spot, ch.timestamp, kept, ch.exercise_style)
        return ch

    def spot(self, ticker, expiries=None) -> float:
        return self._chains[ticker].spot


def fixture_as_of(data: dict) -> date:
    """The capture date year-fractions measure from: the fixture's ``as_of`` field
    (e.g. the Massive weekly capture) if present, else the legacy ``AS_OF``."""
    raw = data.get("as_of")
    return date.fromisoformat(raw) if raw else AS_OF


def load_benchmark(path: Path = FIXTURE) -> tuple[dict, dict[str, ChainSnapshot]]:
    """Parse the fixture into ``(raw_json, {ticker: ChainSnapshot})``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    chains: dict[str, ChainSnapshot] = {}
    for ticker, t in data["tickers"].items():
        ts = datetime.fromisoformat(t["timestamp"])
        quotes = [
            OptionQuote(
                ticker=ticker, expiry=date.fromisoformat(q["expiry"]), strike=q["strike"],
                call_put=q["cp"], bid=q["bid"], ask=q["ask"], last=q["last"],
                volume=q["volume"], open_interest=q["oi"], timestamp=ts,
            )
            for q in t["quotes"]
        ]
        chains[ticker] = ChainSnapshot(
            ticker=ticker, spot=t["spot"], timestamp=ts,
            quotes=quotes, exercise_style=t["exercise_style"],
        )
    return data, chains


def build_state(
    rate: float = 0.0, theoretical: bool = False, with_dividends: bool = False,
    path: Path = FIXTURE,
) -> AppState:
    """An AppState over the static fixture, with optional market overrides."""
    data, chains = load_benchmark(path)
    state = AppState(fixture_as_of(data), provider=StaticProvider(chains))
    if rate or with_dividends:
        for ticker, t in data["tickers"].items():
            divs = (
                [DividendSpec(exDate=d["ex_date"], amount=d["amount"]) for d in t["dividends"]]
                if with_dividends else []
            )
            mode = "discrete_absolute" if divs else "continuous"
            state.set_market_settings(
                ticker, MarketSettings(rate=rate, dividendMode=mode, dividends=divs)
            )
    if theoretical:
        for ticker in chains:
            for e in chains[ticker].expiries():
                state.set_forward_policy(ticker, e.isoformat(), ForwardPolicy(mode="theoretical"))
    return state


def report(state: AppState, ticker: str) -> None:
    resp = calibrate_affine_surface(state, ticker, AffineFitRequest())
    d = last_affine_diagnostics(state, ticker)
    xdiag = {x.expiry: x for x in (last_affine_expiry_diagnostics(state, ticker) or [])}
    print(
        f"{ticker}: surface RMS = {resp.surfaceRmsError * 1e4:.1f} bp  "
        f"(vtx={d.vertex_count}, bounds={d.active_bound_count}, nfev={d.nfev}/{d.max_nfev})"
    )
    # Phase 0 header: the columns that separate Cause A (vtxInRange) from Cause B
    # (vegaFloored / vega√τ) and Cause C (steps), plus prior leakage (priorRows).
    print(
        "   expiry        rms    maxErr  nQ  | vtxIn/Tot  kRange         "
        "| floored  vegaATM  steps  priorRows"
    )
    for sm in resp.smiles:
        x = xdiag.get(sm.expiry)
        if x is None:
            print(f"   {sm.expiry}  rms={sm.rmsError * 1e4:5.1f} bp")
            continue
        print(
            f"   {sm.expiry} {sm.rmsError * 1e4:5.1f}bp {sm.maxIvErrorBp:6.1f}bp "
            f"{x.n_quotes:3d}  | {x.n_vertices_in_range:3d}/{x.n_vertices_total:<3d}  "
            f"[{x.k_lo:+.3f},{x.k_hi:+.3f}] | "
            f"{x.n_vega_floored:3d} ({x.vega_floor_frac * 100:4.0f}%) "
            f"{x.vega_atm:.4f}  {x.n_time_steps:4d}  {x.n_prior_rows:4d}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline Local-Vol benchmark over the Bloomberg fixture.")
    ap.add_argument("--rate", type=float, default=0.0, help="risk-free rate (default 0)")
    ap.add_argument("--theoretical", action="store_true", help="theoretical (dividend-model) forward")
    ap.add_argument("--dividends", action="store_true", help="load the captured dividend schedule")
    ap.add_argument("--fixture", default=str(FIXTURE), help="fixture JSON (default: Bloomberg benchmark)")
    args = ap.parse_args()
    path = Path(args.fixture)
    data, _ = load_benchmark(path)
    state = build_state(rate=args.rate, theoretical=args.theoretical, with_dividends=args.dividends, path=path)
    src = data.get("source", "?")
    cfg = (
        f"src={src}, as_of={fixture_as_of(data)}, rate={args.rate}, "
        f"forward={'theoretical' if args.theoretical else 'parity'}, dividends={args.dividends}"
    )
    print(f"Local-Vol benchmark ({cfg})\n")
    for ticker in data["tickers"]:
        report(state, ticker)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
