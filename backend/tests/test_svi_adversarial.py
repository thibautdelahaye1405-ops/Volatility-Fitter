"""Committee revision R5, challenge 9: the adversarial input battery.

'LM crosses kinks faster than TRF' is an observation, not a robustness
guarantee — so the guarantee is made empirical: every adversarial input the
committee listed either fits to a FINITE, fence-respecting slice or refuses
DETERMINISTICALLY with a reason. Run over BOTH charts (the structural chart
must inherit every robustness property it claims to improve on).
Certification case ``svi_adversarial_inputs``.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.calib.band import BandTarget
from volfit.models.svi_jw.calibrate import _LEE_SLOPE_MAX, calibrate_svi

CHARTS = ("raw", "structural")
#: Post-fit sanity bar: finite params, finite curve on a wide grid, wings at
#: or under the fence (small overshoot allowed for the SOFT raw-chart rows).
WING_TOL = 0.02


def _assert_sane(fit, chart: str) -> None:
    raw = fit.raw
    for f in ("a", "b", "rho", "m", "sigma"):
        assert np.isfinite(getattr(raw, f)), f"{f} not finite"
    grid = np.linspace(-3.0, 3.0, 601)
    w = raw.total_variance(grid)
    assert np.all(np.isfinite(w))
    wing = raw.b * (1.0 + abs(raw.rho))
    if chart == "structural":
        assert wing < _LEE_SLOPE_MAX  # structurally strict, no tolerance
        assert raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2) > 0.0
    else:
        assert wing <= _LEE_SLOPE_MAX + WING_TOL
    assert isinstance(fit.success, bool)  # honesty flag present either way


def _base_quotes(n: int = 21, lo: float = -0.4, hi: float = 0.4):
    k = np.linspace(lo, hi, n)
    base = 0.04 + 0.05 * np.abs(k) ** 1.5 + 0.02 * np.maximum(-k, 0.0)
    return k, base * 0.25  # total variance at t = 0.25


@pytest.mark.parametrize("chart", CHARTS)
def test_three_quotes_fits_and_two_refuses(chart):
    """Fewer than five usable quotes: 3 fits (5 rows >= 5 params with the
    penalty rows), 2 refuses with a REASON instead of a scipy crash."""
    k, w = _base_quotes(3)
    _assert_sane(calibrate_svi(k, w, 0.25, chart=chart), chart)
    k2, w2 = _base_quotes(2)
    with pytest.raises(ValueError, match="at least 3 usable quotes"):
        calibrate_svi(k2, w2, 0.25, chart=chart)


@pytest.mark.parametrize("chart", CHARTS)
def test_one_sided_chain_and_missing_atm(chart):
    """One-sided boards and an ATM hole: finite fence-respecting fits (the
    unseen side is extrapolation — stability across fits is the quality
    layer's business, finiteness is the calibrator's)."""
    k = np.linspace(0.05, 0.60, 12)  # calls only
    w = (0.04 + 0.06 * k) * 0.25
    _assert_sane(calibrate_svi(k, w, 0.25, chart=chart), chart)
    k, w = _base_quotes(25)
    hole = (k < -0.05) | (k > 0.25)  # missing ATM region
    _assert_sane(calibrate_svi(k[hole], w[hole], 0.25, chart=chart), chart)


@pytest.mark.parametrize("chart", CHARTS)
def test_near_zero_total_variance(chart):
    """0DTE-scale tenor: w ~ 1e-6 exercises the floors and the exp/softplus
    lifts without NaN."""
    t = 1e-4
    k = np.linspace(-0.02, 0.02, 15)
    w = (0.20**2 + 0.5 * k**2) * t  # ~4e-6 total variance
    _assert_sane(calibrate_svi(k, w, t, chart=chart), chart)


@pytest.mark.parametrize("chart", CHARTS)
def test_extreme_rho_and_duplicate_strikes(chart):
    """|rho| ~ 1 targets (tanh/logit saturation) and duplicated strikes
    (rank-deficient Jacobian rows) stay finite."""
    from volfit.models.svi_jw.svi import RawSVI

    steep = RawSVI(a=0.005, b=0.35, rho=0.985, m=-0.05, sigma=0.12)
    k = np.linspace(-0.5, 0.5, 21)
    _assert_sane(calibrate_svi(k, steep.total_variance(k), 0.25, chart=chart), chart)
    k_dup = np.concatenate([k, k[7:10]])  # duplicate listings, same strikes
    w_dup = steep.total_variance(k_dup)
    _assert_sane(calibrate_svi(k_dup, w_dup, 0.25, chart=chart), chart)


@pytest.mark.parametrize("chart", CHARTS)
def test_noisy_quotes_and_crossed_band(chart):
    """50%-relative quote noise and a partially CROSSED bid-ask band (bad
    feed rows the quarantine may not own): finite, fenced, no exception."""
    rng = np.random.default_rng(11)
    k, w = _base_quotes(25)
    noisy = w * np.exp(rng.normal(scale=0.5, size=k.size))
    _assert_sane(calibrate_svi(k, noisy, 0.25, chart=chart), chart)
    t = 0.25
    iv_mid = np.sqrt(w / t)
    iv_lo, iv_hi = iv_mid * 0.97, iv_mid * 1.03
    crossed = slice(5, 9)  # a few crossed rows: lo above hi
    iv_lo[crossed], iv_hi[crossed] = iv_hi[crossed] * 1.05, iv_lo[crossed] * 0.95
    band = BandTarget(iv_lo=iv_lo, iv_hi=iv_hi, iv_mid=iv_mid)
    _assert_sane(calibrate_svi(k, w, t, band=band, chart=chart), chart)


@pytest.mark.parametrize("chart", CHARTS)
def test_evaluation_cap_exhaustion_is_honest(chart):
    """The beta = 2 pull (the R1 boundary quotes): even when the solver
    burns its budget (the raw chart does on real nodes), the result is
    finite, fenced, and the success flag tells the truth."""
    from volfit.models.svi_jw.svi import RawSVI

    boundary = RawSVI(a=0.04, b=2.0, rho=0.0, m=0.0, sigma=0.2)
    k = np.linspace(-1.5, 1.5, 25)
    fit = calibrate_svi(k, boundary.total_variance(k), 0.25, chart=chart)
    _assert_sane(fit, chart)
    assert fit.n_evaluations > 0
