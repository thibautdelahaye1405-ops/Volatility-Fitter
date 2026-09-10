"""Compute phase — replay frozen fixtures offline through the production engine.

Loads the immutable JSON fixtures written by ``capture.py`` and serves them to an
``AppState`` via an in-memory ``StaticProvider`` (the same seam ``lv_benchmark.py``
uses), so every model x hyperparameter fit runs with no network and is fully
deterministic. Forwards/de-Americanization are recomputed by the engine exactly as
in production (the captured parity forwards are kept only for diagnostics).
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime

from backtest.fixture_hygiene import dedupe_quotes
from volfit.api.state import AppState
from volfit.data.provider import OptionChainProvider
from volfit.data.types import ChainSnapshot, OptionQuote

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

#: ``VOLFIT_FIXTURE_DEDUPE=0`` replays the raw chain (byte-identity checks);
#: the default runs fixture_hygiene.dedupe_quotes on every load.
DEDUPE_ENV = "VOLFIT_FIXTURE_DEDUPE"


@dataclass(frozen=True)
class Fixture:
    """A loaded fixture: metadata + the NBBO chain (one series per contract —
    ``hygiene`` reports what fixture_hygiene dropped, per expiry; empty when
    nothing was duplicated or the dedupe is switched off)."""

    asset: str
    as_of: date
    regime: str
    exercise_style: str
    sector: str
    expiries: list[date]
    forwards: dict  # iso expiry -> {forward, discount, residual_rms, ...}
    chain: ChainSnapshot
    hygiene: dict = field(default_factory=dict)


class StaticProvider(OptionChainProvider):
    """Serves captured chains from memory (no network / Terminal)."""

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


def load_fixture(path: str) -> Fixture:
    """Parse one fixture JSON into a ``Fixture`` (metadata + ChainSnapshot)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    ts = datetime.fromisoformat(d["snapshot_ts_utc"])
    quotes = [
        OptionQuote(
            ticker=d["asset"], expiry=date.fromisoformat(q["expiry"]), strike=q["strike"],
            call_put=q["cp"], bid=q["bid"], ask=q["ask"],
            open_interest=q.get("ask_size"), timestamp=ts,
        )
        for q in d["quotes"]
    ]
    # One series per (expiry, strike, side): the daily capture could write two
    # roots into one slice (an adjusted series, SPX + SPXW) — see
    # fixture_hygiene. Off by VOLFIT_FIXTURE_DEDUPE=0.
    hygiene: dict = {}
    if os.environ.get(DEDUPE_ENV, "1") != "0":
        quotes, hygiene = dedupe_quotes(quotes, d.get("forwards") or {}, d["spot"])
    chain = ChainSnapshot(
        ticker=d["asset"], spot=d["spot"], timestamp=ts,
        quotes=quotes, exercise_style=d["exercise_style"],
    )
    return Fixture(
        asset=d["asset"], as_of=date.fromisoformat(d["as_of"]), regime=d.get("regime", ""),
        exercise_style=d["exercise_style"], sector=d.get("sector", ""),
        expiries=[date.fromisoformat(e) for e in d["expiries"]],
        forwards=d["forwards"], chain=chain, hygiene=hygiene,
    )


def list_fixtures(regime: str | None = None, asset: str | None = None) -> list[str]:
    """All fixture paths, optionally filtered by regime / asset."""
    pattern = os.path.join(FIXTURE_DIR, regime or "*", "*", f"{asset or '*'}.json")
    return sorted(glob.glob(pattern))


def state_for_day(fixtures: list[Fixture]) -> AppState:
    """An ungated AppState over one as-of day's fixtures (all share reference_date).

    The state's per-ticker expiry selection is pinned to each fixture's captured
    expiries — otherwise ``AppState`` applies its default auto-selection (a subset),
    and ``snapshot`` would silently drop the captured expiries the default rule
    didn't pick, leaving those nodes with no quotes (and no parity forward)."""
    as_of = {f.as_of for f in fixtures}
    if len(as_of) != 1:
        raise ValueError(f"fixtures span multiple as-of dates: {sorted(as_of)}")
    chains = {f.asset: f.chain for f in fixtures}
    state = AppState((as_of.pop()), provider=StaticProvider(chains))
    for f in fixtures:
        state.set_expiries(f.asset, list(f.expiries))
    return state
