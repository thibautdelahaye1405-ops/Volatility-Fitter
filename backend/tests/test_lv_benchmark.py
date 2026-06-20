"""Regression benchmark: the static Bloomberg SPY/NVDA local-vol fit.

Loads the committed fixture (tests/fixtures/lv_benchmark_bloomberg.json, captured
by capture_benchmark.py) and fits the real affine local-vol surface offline. Pins
the fix for the convex-wing × fine-grid regression: at the user's saved settings
(convexWing ON, gridXNodes=20) the low-vol SPY surface read ~26 bp (haircut) /
~13 bp (mid) because the convex constraint fought the dense quoted put wing; with
the constraint confined to the true extrapolation region it fits cleanly.

Opt-in (real chains, ~minute): ``pytest tests/test_lv_benchmark.py -m perf``.
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from volfit.api.affine_fit import calibrate_affine_surface, last_affine_diagnostics
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.state import AppState
from volfit.data.provider import OptionChainProvider
from volfit.data.types import ChainSnapshot, OptionQuote

pytestmark = pytest.mark.perf

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lv_benchmark_bloomberg.json"
AS_OF = date(2026, 6, 20)


class _StaticProvider(OptionChainProvider):
    def __init__(self, chains):
        self._chains = chains

    def list_tickers(self):
        return list(self._chains)

    def available_expiries(self, ticker):
        return self._chains[ticker].expiries()

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        ch = self._chains[ticker]
        if expiries:
            want = set(expiries)
            kept = [q for q in ch.quotes if q.expiry in want]
            return ChainSnapshot(ch.ticker, ch.spot, ch.timestamp, kept, ch.exercise_style)
        return ch

    def spot(self, ticker, expiries=None):
        return self._chains[ticker].spot


def _load():
    import json

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chains = {}
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
    return chains


@pytest.fixture(scope="module")
def state():
    if not FIXTURE.exists():
        pytest.skip("Bloomberg benchmark fixture not captured")
    st = AppState(AS_OF, provider=_StaticProvider(_load()))
    # The settings that triggered the regression: convex wing ON + fine grid.
    st.set_options(st.options().model_copy(update={"convexWing": True, "gridXNodes": 20}))
    return st


def test_spy_lowvol_surface_fits_cleanly(state):
    """SPY (low vol, dense American chain) must fit well even with convexWing ON
    and the fine grid — the regression made this ~13 bp (mid); the fix keeps it low."""
    resp = calibrate_affine_surface(state, "SPY", AffineFitRequest())
    d = last_affine_diagnostics(state, "SPY")
    assert d.vertex_count > 100  # the fine (gridXNodes=20) grid is in force
    assert resp.surfaceRmsError * 1e4 < 8.0
    assert all(sm.rmsError * 1e4 < 12.0 for sm in resp.smiles)


def test_nvda_surface_unaffected(state):
    """NVDA was already fine; the fix must not regress it."""
    resp = calibrate_affine_surface(state, "NVDA", AffineFitRequest())
    assert resp.surfaceRmsError * 1e4 < 16.0
