"""Bid-ask / haircut band fitting objective (volfit.calib.band).

The band modes replace the |mid - model| data term by a hinge that only
penalizes leaving the quoted band, plus a small mid anchor. Invariants:

1. ``resolve_band`` builds (bid, ask) for bidask and the mid-clamped
   (bid+h, ask-h) for haircut, never crossing mid;
2. with noisy mids that wiggle *inside* a wide band, every model family fits a
   curve that stays inside the band and does not chase the mid noise (so it is
   no rougher than, and usually smoother than, the mid fit);
3. a mid sitting *outside* the band is pulled back to the band edge, not matched.
"""

import numpy as np
import pytest

from volfit.calib.band import (
    DEFAULT_HAIRCUT,
    MID_ANCHOR_WEIGHT,
    band_residuals,
    resolve_band,
)
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi


# ----------------------------------------------------------- resolve_band
def test_resolve_band_modes():
    bid = np.array([0.18, 0.20])
    mid = np.array([0.20, 0.22])
    ask = np.array([0.22, 0.24])

    assert resolve_band(bid, mid, ask, "mid") is None

    raw = resolve_band(bid, mid, ask, "bidask")
    np.testing.assert_allclose(raw.iv_lo, bid)
    np.testing.assert_allclose(raw.iv_hi, ask)

    # haircut 3 vol pts > half-spread (2 vol pts): each side clamps to mid.
    hc = resolve_band(bid, mid, ask, "haircut", haircut=0.03)
    np.testing.assert_allclose(hc.iv_lo, mid)
    np.testing.assert_allclose(hc.iv_hi, mid)

    hc2 = resolve_band(bid, mid, ask, "haircut", haircut=0.005)
    np.testing.assert_allclose(hc2.iv_lo, bid + 0.005)
    np.testing.assert_allclose(hc2.iv_hi, ask - 0.005)
    # Haircut never crosses mid.
    assert np.all(hc2.iv_lo <= mid) and np.all(hc2.iv_hi >= mid)


def test_haircut_default_is_half_vol_point():
    assert DEFAULT_HAIRCUT == 0.005


def test_band_residuals_zero_inside_band():
    """Model inside the band -> only the (small) mid anchor is nonzero."""
    model = np.array([0.20, 0.21])
    lo = np.array([0.18, 0.18])
    hi = np.array([0.22, 0.24])
    mid = np.array([0.20, 0.20])
    res = band_residuals(model, lo, hi, mid, 1.0)
    viol, anchor = res[:2], res[2:]
    np.testing.assert_allclose(viol, 0.0)  # both inside band -> no violation
    np.testing.assert_allclose(anchor, np.sqrt(MID_ANCHOR_WEIGHT) * (model - mid))


# ------------------------------------------------- per-model band behaviour
def _setup(seed: int = 0):
    """A smooth true smile, a wide band, and a noisy mid wiggling inside it."""
    t = 0.3
    k = np.linspace(-0.3, 0.3, 25)
    true_vol = 0.20 - 0.3 * k + 0.5 * k**2
    half = 0.012  # +-1.2 vol-point band
    noise = np.random.default_rng(seed).uniform(-0.009, 0.009, k.size)
    mid = true_vol + noise
    band = resolve_band(true_vol - half, mid, true_vol + half, "bidask")
    return t, k, mid, true_vol - half, true_vol + half, band


def _model_vol(fit, k, t):
    if hasattr(fit, "raw"):  # SVI calibration
        w = fit.raw.total_variance(k)
    elif hasattr(fit, "slice"):  # LQD calibration
        w = fit.slice.implied_w(k)
    else:  # MultiCoreSiv
        w = fit.implied_w(k)
    return np.sqrt(w / t)


_FITTERS = {
    "svi": lambda k, w, t, b: calibrate_svi(k, w, t, band=b),
    "sigmoid": lambda k, w, t, b: calibrate_sigmoid(k, w, t, n_cores=2, band=b),
    "lqd": lambda k, w, t, b: calibrate_slice(k, w, t, band=b),
}


@pytest.mark.parametrize("model", list(_FITTERS))
def test_band_fit_stays_in_band_and_smooths(model):
    t, k, mid, bid, ask, band = _setup()
    fitter = _FITTERS[model]
    w_mid = mid**2 * t

    band_fit = _model_vol(fitter(k, w_mid, t, band), k, t)
    mid_fit = _model_vol(fitter(k, w_mid, t, None), k, t)

    # 1. The band fit sits inside the quoted band at every quoted strike.
    assert np.all(band_fit >= bid - 1e-6)
    assert np.all(band_fit <= ask + 1e-6)
    # 2. It does not chase the mid noise: no rougher than the mid fit.
    rough_band = float(np.sum(np.diff(band_fit, 2) ** 2))
    rough_mid = float(np.sum(np.diff(mid_fit, 2) ** 2))
    assert rough_band <= rough_mid * 1.05


@pytest.mark.parametrize("model", list(_FITTERS))
def test_outside_band_mid_is_pulled_to_edge(model):
    """A single mid spike outside the band is pulled back toward the band, not
    matched (band modes reject the off-band quote)."""
    t = 0.3
    k = np.linspace(-0.25, 0.25, 21)
    true_vol = 0.20 - 0.2 * k + 0.4 * k**2
    half = 0.01
    bid, ask = true_vol - half, true_vol + half
    mid = true_vol.copy()
    j = len(k) // 2
    mid[j] += 0.05  # a 5 vol-pt spike well above the ask
    band = resolve_band(bid, mid, ask, "bidask")
    w_mid = mid**2 * t

    band_fit = _model_vol(_FITTERS[model](k, w_mid, t, band), k, t)
    # The fitted vol at the spike strike is far below the bad mid and near the band.
    assert band_fit[j] < mid[j] - 0.02
    assert band_fit[j] <= ask[j] + 0.005
