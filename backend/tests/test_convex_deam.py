"""Wing-only convex de-Am repair (volfit/calib/convex_deam.py, FINDINGS R3).

De-Am can leave the American call wings non-convex (butterfly-arbitrageable). The
repair convexifies ONLY the wings and leaves the ATM core byte-identical — the
guard against the reverted global projection that moved the ATM (the SPY/NVDA gap).
"""

from __future__ import annotations

import numpy as np

from volfit.calib.convex_deam import convex_wing_repair, min_norm_butterfly

F = 100.0
W_ATM = 0.04  # vol 0.20, t=1 -> sqrt(w_atm)=0.20, so |z|<=1 <=> |k|<=0.20


def _convex_call_curve(k: np.ndarray) -> np.ndarray:
    """A strictly convex, decreasing normalized call curve in strike."""
    strikes = F * np.exp(k)
    return np.exp(-3.0 * (strikes - strikes[0]) / (strikes[-1] - strikes[0]))


def _band(c: np.ndarray, half: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """A symmetric bid/ask band around a mid call curve (wide unless told otherwise)."""
    return c - half, c + half


def test_convex_curve_returns_none():
    """An already-convex curve is the no-op (byte-identical) path."""
    k = np.linspace(-0.30, 0.30, 25)
    c = _convex_call_curve(k)
    lo, hi = _band(c)
    assert min_norm_butterfly(F * np.exp(k), c) >= 0.0
    assert convex_wing_repair(k, c, lo, hi, W_ATM, F) is None


def test_short_chain_returns_none():
    k = np.linspace(-0.1, 0.1, 4)  # n < 5
    c = _convex_call_curve(k)
    lo, hi = _band(c)
    assert convex_wing_repair(k, c, lo, hi, W_ATM, F) is None


def test_wing_nonconvexity_repaired_with_atm_byte_identical():
    """A wing dip is convexified; the ATM core (|z|<=1) is EXACTLY preserved."""
    k = np.linspace(-0.30, 0.30, 25)
    strikes = F * np.exp(k)
    c = _convex_call_curve(k)
    wing = int(np.argmax(k > 0.25))  # a right-wing strike, |z| > 1
    c[wing] -= 0.01  # dip -> local non-convexity (negative butterfly)
    lo, hi = _band(c)  # wide band -> convexity drives the repair
    assert min_norm_butterfly(strikes, c) < 0.0

    rep = convex_wing_repair(k, c, lo, hi, W_ATM, F)
    assert rep is not None
    core = np.abs(k / np.sqrt(W_ATM)) <= 1.0
    assert np.array_equal(rep[core], c[core])  # ATM byte-identical (the guard)
    assert not np.array_equal(rep[~core], c[~core])  # the wing actually moved
    assert min_norm_butterfly(strikes, rep) >= -1e-6  # now (near-)convex


def test_left_wing_repaired():
    """The put (left) wing is handled too (the reflected-distance path)."""
    k = np.linspace(-0.30, 0.30, 25)
    strikes = F * np.exp(k)
    c = _convex_call_curve(k)
    wing = int(np.argmax(k > -0.28))  # a deep left-wing strike
    c[wing] -= 0.01
    lo, hi = _band(c)
    assert min_norm_butterfly(strikes, c) < 0.0
    rep = convex_wing_repair(k, c, lo, hi, W_ATM, F)
    assert rep is not None
    core = np.abs(k / np.sqrt(W_ATM)) <= 1.0
    assert np.array_equal(rep[core], c[core])
    assert min_norm_butterfly(strikes, rep) >= -1e-6


def test_duplicate_strike_at_core_boundary_does_not_crash():
    """Captured chains can carry DUPLICATE strikes (multiple listings at one strike).
    A duplicate straddling a core boundary made the anchor slope divide by zero and
    fed ``lsq_linear`` an infinite lower bound — the spike_aug2024 XOM 2024-12-20
    ValueError that killed whole backtest day-pairs. The anchor slope must be taken
    to the nearest DISTINCT strike instead."""
    for boundary in (-1.0, 1.0):  # duplicate at the left / right core edge (z = ±1)
        k = np.linspace(-0.30, 0.30, 25)
        edge = int(np.argmin(np.abs(k / np.sqrt(W_ATM) - boundary)))
        inward = 1 if boundary < 0 else -1
        k[edge + inward] = k[edge]  # coincident strike pair straddling the boundary
        strikes = F * np.exp(k)
        c = _convex_call_curve(k)
        wing = 1 if boundary < 0 else -2  # a deep same-side wing strike
        c[wing] -= 0.01  # non-convexity so the repair actually runs
        lo, hi = _band(c)
        assert min_norm_butterfly(strikes, c) < 0.0
        rep = convex_wing_repair(k, c, lo, hi, W_ATM, F)  # must not raise
        assert rep is not None and np.all(np.isfinite(rep))
        core = np.abs(k / np.sqrt(W_ATM)) <= 1.0
        assert np.array_equal(rep[core], c[core])  # ATM core still byte-identical


def test_fully_coincident_core_skips_wing():
    """When EVERY core strike coincides (no measurable anchor slope at all), the
    wing repair is skipped — original prices kept, no raise. The >=3 coincident
    strikes also exercise the zero-span guard in ``min_norm_butterfly``."""
    k = np.concatenate([np.zeros(6), np.linspace(0.22, 0.30, 6)])  # flat core + wing
    c = _convex_call_curve(k)
    c[-2] -= 0.01  # wing dip so the repair path actually runs
    lo, hi = _band(c)
    assert min_norm_butterfly(F * np.exp(k), c) < 0.0  # finite despite zero spans
    rep = convex_wing_repair(k, c, lo, hi, W_ATM, F)  # must not raise
    assert rep is not None
    assert np.array_equal(rep, c)  # unmeasurable slope -> wing left untouched


def test_repair_stays_within_band():
    """The repaired mid never leaves the bid/ask band — the fix for unphysical
    extreme-IV wings (a tight band clips the convex projection)."""
    k = np.linspace(-0.30, 0.30, 25)
    c = _convex_call_curve(k)
    wing = int(np.argmax(k > 0.22))
    c[wing] -= 0.02  # a big dip
    half = 0.003  # a TIGHT band: the convex repair must be clipped into it
    lo, hi = _band(c, half)
    rep = convex_wing_repair(k, c, lo, hi, W_ATM, F)
    assert rep is not None
    assert np.all(rep >= lo - 1e-9) and np.all(rep <= hi + 1e-9)  # inside the band
