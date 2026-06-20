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

from volfit.api.affine_fit import calibrate_affine_surface, last_affine_diagnostics
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


def build_state(rate: float = 0.0, theoretical: bool = False, with_dividends: bool = False) -> AppState:
    """An AppState over the static fixture, with optional market overrides."""
    data, chains = load_benchmark()
    state = AppState(AS_OF, provider=StaticProvider(chains))
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
    print(
        f"{ticker}: surface RMS = {resp.surfaceRmsError * 1e4:.1f} bp  "
        f"(vtx={d.vertex_count}, bounds={d.active_bound_count}, nfev={d.nfev}/{d.max_nfev})"
    )
    for sm in resp.smiles:
        print(
            f"   {sm.expiry}  rms={sm.rmsError * 1e4:5.1f} bp   "
            f"maxErr={sm.maxIvErrorBp:6.1f} bp   nQuotes={len(sm.quotes)}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline Local-Vol benchmark over the Bloomberg fixture.")
    ap.add_argument("--rate", type=float, default=0.0, help="risk-free rate (default 0)")
    ap.add_argument("--theoretical", action="store_true", help="theoretical (dividend-model) forward")
    ap.add_argument("--dividends", action="store_true", help="load the captured dividend schedule")
    args = ap.parse_args()
    state = build_state(rate=args.rate, theoretical=args.theoretical, with_dividends=args.dividends)
    cfg = f"rate={args.rate}, forward={'theoretical' if args.theoretical else 'parity'}, dividends={args.dividends}"
    print(f"Local-Vol benchmark ({cfg})\n")
    for ticker in ("SPY", "NVDA"):
        report(state, ticker)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
