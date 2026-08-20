"""V3.1 leg 6: the adjudication instrument's calendar columns + gated verdict.

Offline fixture-based smoke: on a two-expiry synthetic node, ``fit_node``
emits, per model row, the per-family calendar certification columns
(cal_kind / cal_gap_min / cal_gap_k / cal_wing_order_ok / cal_certified —
LQD via the exact ledger certificate, SVI and Multi-Core SIV via the
polished-dense certificate with closed-form slope overrides) and the
certificate-gated verdict ``valid`` (butterfly AND calendar certified).
The first expiry (no previous slice) carries None calendar columns and a
butterfly-only verdict. Not a sweep — the benchmark adjudication runs in the
user's window.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from backtest.dispatch import ModelSpec, fit_node
from backtest.replay import StaticProvider
from volfit.api.state import AppState
from volfit.core.black import black_call
from volfit.data.types import ChainSnapshot, OptionQuote

_S = 100.0
_AS_OF = date(2024, 8, 5)
_EXPIRIES = (date(2024, 9, 6), date(2024, 10, 18))
#: A small sweep — one model per family — keeps the smoke fast; the full
#: DEFAULT_SWEEP is the user-window adjudication run's job.
_SPECS = (
    ModelSpec("svi", "SVI-JW"),
    ModelSpec("lqd", "LQD-6", {"n_order": 6}),
    ModelSpec("sigmoid", "SIV-0", {"n_cores": 0}),
)
_CAL_COLS = ("cal_kind", "cal_gap_min", "cal_gap_k", "cal_wing_order_ok", "cal_certified")


def _skew_vol(k: float, t: float) -> float:
    """A GLOBALLY calendar-ordered smile family: hyperbolic total variance
    w(k, t) = a(t) + b(t) sqrt(k² + s²) with a and b both increasing in t, so
    w is increasing in maturity at EVERY k (wings included) and the far wing
    slopes strictly dominate — every family's fitted pair must certify."""
    w = (0.01 + 0.05 * t) + (0.10 + 0.20 * t) * np.sqrt(k * k + 0.04)
    return float(np.sqrt(w / t))


def _state() -> AppState:
    quotes: list[OptionQuote] = []
    ts = datetime(2024, 8, 5, 19, 45)
    for expiry in _EXPIRIES:
        t = (expiry - _AS_OF).days / 365.0
        for strike in range(70, 131, 5):
            k = float(np.log(strike / _S))
            w = _skew_vol(k, t) ** 2 * t
            # European Black prices (zero carry): call at every strike, put by
            # parity — quote prep keeps the OTM leg and needs both legs to
            # resolve the forward.
            call = float(black_call(k, w)) * _S
            put = call - _S + float(strike)
            for is_call, px in ((True, call), (False, put)):
                px = max(px, 0.02)
                quotes.append(OptionQuote(
                    ticker="XYZ", expiry=expiry, strike=float(strike),
                    call_put="C" if is_call else "P",
                    bid=max(px - 0.01, 0.01), ask=px + 0.01,
                    open_interest=None, timestamp=ts,
                ))
    chain = ChainSnapshot(ticker="XYZ", spot=_S, timestamp=ts, quotes=quotes,
                          exercise_style="european")
    state = AppState(_AS_OF, provider=StaticProvider({"XYZ": chain}))
    state.set_expiries("XYZ", list(_EXPIRIES))
    return state


@pytest.fixture(scope="module")
def rows_by_expiry():
    state = _state()
    prev: dict = {}
    out = []
    for expiry in _EXPIRIES:
        slices: dict = {}
        rows = fit_node(
            state, "XYZ", expiry, "smoke", "test", "european",
            specs=_SPECS, prev_slices=prev or None, slices_out=slices,
        )
        out.append(rows)
        prev = slices
    return out


def test_first_expiry_has_null_calendar_and_butterfly_verdict(rows_by_expiry):
    for row in rows_by_expiry[0]:
        assert row["ok"], row.get("error")
        for col in _CAL_COLS:
            assert row[col] is None
        assert row["valid"] == (not row["arb_real"])


def test_second_expiry_emits_per_family_calendar_columns(rows_by_expiry):
    kinds = {}
    for row in rows_by_expiry[1]:
        assert row["ok"], row.get("error")
        assert row["cal_kind"] in ("ledger", "polished")
        assert isinstance(row["cal_gap_min"], float)
        assert isinstance(row["cal_gap_k"], float)
        assert isinstance(row["cal_certified"], bool)
        assert isinstance(row["cal_wing_order_ok"], bool)
        kinds[row["family"]] = row["cal_kind"]
        # The gated verdict: butterfly AND calendar certified.
        assert row["valid"] == (not row["arb_real"] and row["cal_certified"])
    assert kinds["lqd"] == "ledger"  # the exact full-line certificate
    assert kinds["svi"] == "polished" and kinds["sigmoid"] == "polished"


def test_calendar_consistent_surface_certifies(rows_by_expiry):
    """The synthetic surface is calendar-clean by construction: every family's
    pair certifies (the smoke guards against a false-positive instrument)."""
    for row in rows_by_expiry[1]:
        assert row["cal_certified"], (row["model"], row["cal_gap_min"])
        assert row["cal_gap_min"] > -1e-6
