"""Stage 4 — the compiled de-Am kernel matches the NumPy fallback exactly.

`core.american.deamericanize_batch` runs the Numba kernel (`core.american_numba`)
when available and the lockstep NumPy batch otherwise. The contract: the two
paths agree to tree rounding on every quote (price/IV), including the discrete
cash-dividend escrow, and the NumPy fallback works with Numba forced off. The
kernel's bracketing mirrors the fallback's `<=`/`>=`/`<` comparisons, so the two
also agree on which quotes invert (NaN alignment).
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.core import american_numba
from volfit.core.american import binomial_price_batch, deamericanize_batch


@pytest.fixture
def force_numpy(monkeypatch):
    """Run deamericanize_batch on the NumPy fallback (Numba dispatch disabled)."""
    monkeypatch.setattr(american_numba, "NUMBA_AVAILABLE", False)


def _chain(spot, t, r, q, lo_m=0.55, hi_m=1.75, n=60):
    """Calls and puts across a wide moneyness ladder at a known smile."""
    fwd = spot * float(np.exp((r - q) * t))
    strikes = np.concatenate([np.linspace(lo_m, hi_m, n) * fwd] * 2)
    is_call = np.concatenate([np.ones(n, bool), np.zeros(n, bool)])
    sigma = 0.2 + 0.05 * np.log(strikes / fwd) ** 2
    prices = binomial_price_batch(is_call, spot, strikes, t, sigma, r, q, american=True)
    return is_call, strikes, sigma, prices


def _both_paths(monkeypatch, fn):
    """Return (numba_result, numpy_result) for the same de-Am call."""
    numba = fn()
    monkeypatch.setattr(american_numba, "NUMBA_AVAILABLE", False)
    numpy = fn()
    return numba, numpy


def test_numba_matches_numpy_continuous_yield(monkeypatch):
    spot, t, r, q = 100.0, 0.5, 0.05, 0.02
    is_call, strikes, _, prices = _chain(spot, t, r, q)
    nb, npy = _both_paths(
        monkeypatch, lambda: deamericanize_batch(is_call, prices, spot, strikes, t, r, q)
    )

    assert np.array_equal(np.isfinite(nb), np.isfinite(npy))  # same quotes invert
    ok = np.isfinite(nb)
    assert ok.sum() >= 80  # the wide ladder mostly inverts
    assert np.max(np.abs(nb[ok] - npy[ok])) < 1e-6  # agree to tree rounding


def test_numba_matches_numpy_discrete_cash_dividends(monkeypatch):
    """The escrowed discrete-cash schedule (the key American feature) must match
    across both paths — this is where a naive continuous-yield proxy would not."""
    spot, t, r = 100.0, 0.7, 0.04
    div_t = np.array([0.2, 0.5])
    div_a = np.array([1.5, 1.5])
    fwd = spot * float(np.exp(r * t))  # cash divs handled via escrow, q = 0
    strikes = np.concatenate([np.linspace(0.6, 1.6, 30) * fwd] * 2)
    is_call = np.concatenate([np.ones(30, bool), np.zeros(30, bool)])
    sigma = np.full(strikes.size, 0.25)
    prices = binomial_price_batch(
        is_call, spot, strikes, t, sigma, r, 0.0, american=True,
        div_times=div_t, div_amounts=div_a,
    )

    nb, npy = _both_paths(
        monkeypatch,
        lambda: deamericanize_batch(
            is_call, prices, spot, strikes, t, r, 0.0, div_times=div_t, div_amounts=div_a
        ),
    )
    assert np.array_equal(np.isfinite(nb), np.isfinite(npy))
    ok = np.isfinite(nb)
    assert ok.all()  # the in-bounds cash-div chain inverts everywhere
    assert np.max(np.abs(nb[ok] - npy[ok])) < 1e-6
    assert np.max(np.abs(nb[ok] - 0.25)) < 5e-4  # recovers the flat input smile


def test_numba_recovers_known_smile(monkeypatch):
    """Both paths recover the generating smile to tree tolerance (not just each
    other) — guards against a shared but wrong implementation."""
    spot, t, r, q = 100.0, 0.5, 0.05, 0.02
    is_call, strikes, sigma, prices = _chain(spot, t, r, q)
    nb = deamericanize_batch(is_call, prices, spot, strikes, t, r, q)
    ok = np.isfinite(nb)
    assert np.max(np.abs(nb[ok] - sigma[ok])) < 5e-4


def test_numpy_fallback_runs_without_numba(force_numpy):
    """With Numba forced off the chain still de-Americanizes correctly."""
    assert not american_numba.NUMBA_AVAILABLE
    spot, t, r, q = 100.0, 0.5, 0.05, 0.02
    is_call, strikes, sigma, prices = _chain(spot, t, r, q)
    npy = deamericanize_batch(is_call, prices, spot, strikes, t, r, q)
    ok = np.isfinite(npy)
    assert ok.sum() >= 80
    assert np.max(np.abs(npy[ok] - sigma[ok])) < 5e-4


def test_empty_and_expired_return_all_nan():
    """Degenerate inputs are handled before dispatch (no kernel call needed)."""
    out = deamericanize_batch(
        np.array([True]), np.array([5.0]), 100.0, np.array([100.0]), 0.0, 0.05, 0.0
    )
    assert out.shape == (1,) and np.isnan(out).all()  # expired
    # A price below intrinsic is screened out (NaN) on both paths.
    below = deamericanize_batch(
        np.array([True]), np.array([0.0]), 100.0, np.array([50.0]), 0.5, 0.05, 0.0
    )
    assert np.isnan(below).all()
