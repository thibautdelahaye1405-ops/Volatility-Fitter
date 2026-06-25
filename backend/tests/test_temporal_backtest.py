"""Temporal prior-persistence mode scoring (backtest/temporal.py, roadmap Phase 8).

The harness fits day T-1 as the prior, thins day T to its ATM region, refits under
each persistence mode, and scores the RECONSTRUCTED wing vs the true day-T quotes.
These gates lock the pure scoring helpers and one end-to-end self-prior pass on the
synthetic provider (no captured fixtures needed): with the prior == today's own
surface, a persisted prior must reconstruct the held-out wing better than no prior.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api import priors
from volfit.api.state import AppState
from backtest.temporal import (
    NodeScore,
    _atm_mask,
    _flatten,
    _wing_rmse_bp,
    score_node,
    summarize,
)

REF_DATE = date(2026, 6, 10)


class _Slice:
    """A minimal SmileModel stand-in: total variance from a fixed vol on a k-grid."""

    def __init__(self, vol: float, bad_at: float | None = None) -> None:
        self.vol, self.bad_at = vol, bad_at

    def implied_w(self, k):  # noqa: D401 - matches the SmileModel protocol
        k = np.asarray(k, float)
        w = np.full(k.shape, (self.vol**2) * 0.25)
        if self.bad_at is not None:
            w = np.where(np.abs(k - self.bad_at) < 1e-9, np.nan, w)
        return w


def test_atm_mask_widens_with_c():
    """The ATM region is c·σ√τ wide, so a larger c keeps strictly more strikes."""
    k = np.linspace(-0.3, 0.3, 25)
    narrow = _atm_mask(k, atm_vol=0.2, tau=0.25, c_atm=0.5)
    wide = _atm_mask(k, atm_vol=0.2, tau=0.25, c_atm=1.5)
    assert wide.sum() > narrow.sum()
    assert np.all(wide[narrow])  # nested: every narrow-ATM strike is also wide-ATM


def test_wing_rmse_drops_nonfinite_and_guards_thin():
    """Non-finite model vols are dropped; <2 finite survivors ⇒ None (not a NaN)."""
    tau = 0.25
    k = np.array([-0.2, -0.1, 0.1, 0.2])
    w_truth = np.full(4, (0.20**2) * 0.25)  # vol 0.20 everywhere
    # Model at vol 0.22, one strike non-finite: scored on the 3 finite points.
    rmse = _wing_rmse_bp(_Slice(0.22, bad_at=-0.2), k, w_truth, tau)
    assert rmse is not None and abs(rmse - 200.0) < 1.0  # ~2 vol-points = 200 bp
    # Only one finite survivor (the other is non-finite) ⇒ too few to score.
    assert _wing_rmse_bp(_Slice(0.22, bad_at=-0.1), k[:2], w_truth[:2], tau) is None


def test_summarize_ranks_by_median_and_skips_breaks():
    """summarize aggregates per (mode, bw, probe): median RMS / improvement / win-rate,
    ignoring off rows and fit breaks (None scores)."""
    base = dict(asset="X", as_of="2024-08-02", prior_as_of="2024-08-01", expiry="2024-08-16",
                regime="r", t=0.1, atm_vol=0.2, n_full=20, n_atm=8, n_wing=6)
    rows = [
        dict(base, mode="off", bandwidth=None, probe=None, wing_rmse_bp=100.0, improvement_bp=0.0),
        dict(base, mode="hybrid", bandwidth=0.06, probe=1.4, wing_rmse_bp=40.0, improvement_bp=60.0),
        dict(base, mode="hybrid", bandwidth=0.06, probe=1.4, wing_rmse_bp=None, improvement_bp=None),
    ]
    out = summarize(rows)
    assert len(out) == 1
    s = out[0]
    assert s["mode"] == "hybrid" and s["n"] == 1  # the None break was skipped
    assert s["median_wing_rmse_bp"] == 40.0 and s["median_improvement_bp"] == 60.0
    assert s["win_rate"] == 1.0


def test_score_node_self_prior_beats_off():
    """End-to-end on the synthetic provider with the prior == today's own surface:
    a persisted prior (hybrid) must reconstruct the held-out wing at least as well
    as no prior (off), and the off baseline must be a finite number."""
    state = AppState(REF_DATE)
    ticker = state.active_tickers()[0]
    snap = priors.capture_snapshot(state, ticker, "mid", lv=False)
    assert snap is not None
    state.set_active_prior(ticker, snap, "saved")

    # Longest expiry (the densest chain) with lenient bands for the sparse synthetic.
    expiry = sorted(state.forwards(ticker))[-1]
    ns = score_node(
        state, ticker, expiry, prior_as_of=REF_DATE.isoformat(), regime="synthetic",
        modes=("off", "hybrid"), bandwidths=(0.06,), probes=(1.4,),
        c_atm=1.0, c_wing=3.0, min_atm=3, min_wing=2,
    )
    assert isinstance(ns, NodeScore)
    assert np.isfinite(ns.off_rmse_bp)
    hybrid = ns.scores[("hybrid", 0.06, 1.4)]
    assert hybrid is not None
    # Self-prior carries the true wing, so it should not be worse than extrapolation.
    assert hybrid <= ns.off_rmse_bp + 1.0

    rows = _flatten([ns])
    assert any(r["mode"] == "off" for r in rows)
    assert any(r["mode"] == "hybrid" and r["improvement_bp"] is not None for r in rows)
