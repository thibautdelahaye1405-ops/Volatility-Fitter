"""Idio band floor (volfit.graph.idio) — the calm-regime dark-name band fix.

Contracts locked here (FINDINGS_graph_loo 2026-07-09 follow-up; offline design
validated on the stored benchmark rows 2026-07-10):

  * the floor NEVER moves a posterior mean — it only widens the ATM band std;
  * no history (or ``idioFloor`` off) ⇒ the solved field is byte-identical to
    the legacy solve;
  * the estimator is strictly causal (today's innovations never feed today's
    floor) and cold-start-silent;
  * observed nodes (lit + calibrated + not held out) are never floored;
  * recording is idempotent per (ticker, day, expiry).
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import priors
from volfit.api.graph_extrapolation import solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState
from volfit.graph.idio import (
    IDIO_FLOOR_LAMBDA,
    IdioHistory,
    apply_idio_floor,
    trailing_idio_sigma,
)
from volfit.graph.smile_universe import HandleField

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def primed() -> AppState:
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


# ------------------------------------------------------------------- estimator
def test_trailing_sigma_cold_start_is_none():
    assert trailing_idio_sigma([]) is None


def test_trailing_sigma_single_day_is_rms():
    assert trailing_idio_sigma([("2026-06-01", 0.02)]) == pytest.approx(0.02)


def test_trailing_sigma_shrinks_toward_pool():
    # own value 0 with a nonzero pool: var = (1*0 + K*pool)/(1+K), K=4
    s = trailing_idio_sigma([("2026-06-01", 0.0)], pool_mean_sq=0.0016)
    assert s == pytest.approx(np.sqrt(4 * 0.0016 / 5))


def test_trailing_sigma_recency_weighting():
    entries = [("2026-06-01", 0.10), ("2026-06-02", 0.0)]
    recent = trailing_idio_sigma(entries, halflife=0.5)  # newest day dominates
    flat = trailing_idio_sigma(entries, halflife=0)
    assert recent < flat


# --------------------------------------------------------------------- history
def test_history_causality_and_idempotence():
    h = IdioHistory()
    assert h.record("AAA", "2026-06-10", "2026-07-17", 0.03) is True
    assert h.record("AAA", "2026-06-10", "2026-07-17", 0.03) is False  # unchanged
    assert h.entries_before("AAA", "2026-06-10") == []  # strictly before
    assert h.entries_before("AAA", "2026-06-11") == [("2026-06-10", 0.03)]
    assert h.sigma_map("2026-06-10") == {}
    assert h.sigma_map("2026-06-11")["AAA"] == pytest.approx(0.03)


def test_history_blob_roundtrip_and_malformed():
    h = IdioHistory()
    h.record("AAA", "2026-06-10", "2026-07-17", 0.03)
    again = IdioHistory.from_blob(h.to_blob())
    assert again.sigma_map("2026-06-11") == h.sigma_map("2026-06-11")
    assert IdioHistory.from_blob(None).sigma_map("2099-01-01") == {}
    assert IdioHistory.from_blob({"tickers": {"AAA": "garbage"}}).sigma_map(
        "2099-01-01"
    ) == {}


# ------------------------------------------------------------------ floor unit
def _field(sd0=(0.01, 0.01, 0.01)) -> HandleField:
    mean = np.arange(9, dtype=float).reshape(3, 3)
    sd = np.full((3, 3), 0.02)
    sd[:, 0] = sd0
    return HandleField(mean=mean, sd=sd, posteriors=(None, None, None))


def test_floor_widens_atm_band_only_and_never_the_mean():
    f = _field()
    sigmas = np.array([np.nan, 0.001, 0.5])  # no floor / below band / dominant
    out, bound = apply_idio_floor(f, sigmas)
    assert list(bound) == [False, False, True]
    assert out.mean is f.mean  # the mean array is the SAME object — untouched
    assert out.sd[0, 0] == f.sd[0, 0] and out.sd[1, 0] == f.sd[1, 0]
    assert out.sd[2, 0] == pytest.approx(np.sqrt(IDIO_FLOOR_LAMBDA) * 0.5)
    assert np.array_equal(out.sd[:, 1:], f.sd[:, 1:])  # skew/curv untouched


def test_floor_noop_returns_same_field():
    f = _field()
    out, bound = apply_idio_floor(f, np.array([np.nan, np.nan, np.nan]))
    assert out is f and not bound.any()


# ------------------------------------------------------------------ solve level
def test_solve_without_history_is_byte_identical(primed):
    legacy = solve(primed, GraphExtrapolateRequest(idioFloor=False))
    fresh = solve(primed, GraphExtrapolateRequest())  # empty history -> no floor
    assert legacy is not None and fresh is not None
    assert np.array_equal(legacy.field.mean, fresh.field.mean)
    assert np.array_equal(legacy.field.sd, fresh.field.sd)


def test_solve_floors_dark_band_and_leaves_means_alone(primed):
    tk = primed.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(primed.selected_expiries(tk))]
    primed.set_node_lit(tk, isos[-1], False)  # darken one node of the ticker

    req = GraphExtrapolateRequest()
    base = solve(primed, req, idio_atm_sigma={})
    floored = solve(primed, req, idio_atm_sigma={tk: 1.0})  # dominant sigma
    assert base is not None and floored is not None
    assert np.array_equal(base.field.mean, floored.field.mean)  # mean-invariant

    for i, node in enumerate(floored.universe.nodes):
        was, now = base.field.sd[i, 0], floored.field.sd[i, 0]
        if node.ticker == tk and not node.lit:
            assert now == pytest.approx(np.sqrt(IDIO_FLOOR_LAMBDA) * 1.0)
            assert now > was
            assert floored.base_breakdowns[i].factors["idioSigma"] == 1.0
        elif floored.calibrated[i]:
            assert now == was  # observed nodes are never floored


def test_solve_records_innovations_causally(primed):
    sol = solve(primed, GraphExtrapolateRequest())
    assert sol is not None and any(sol.calibrated)
    # Today's recordings exist but never feed TODAY's floor (strict causality)…
    assert primed.graph_idio_sigma() == {}
    # …and become tomorrow's estimate.
    later = IdioHistory.from_blob(primed._graph_idio.to_blob()).sigma_map("2099-01-01")
    recorded = {n.ticker for i, n in enumerate(sol.universe.nodes) if sol.calibrated[i]}
    assert recorded and recorded <= set(later)
