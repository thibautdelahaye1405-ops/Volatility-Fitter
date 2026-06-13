"""SSR scenario engine: ATM response and shape preservation per regime."""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.dynamics import Regime, shifted_smile, ssr_of_regime
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice

SPOT_RETURN = -0.03  # a 3% sell-off


@pytest.fixture(scope="module")
def smile():
    slice_ = build_slice(bm.SVI_LQD_PARAMS)
    handles = atm_handles(slice_, bm.SVI_T)
    return slice_, handles


@pytest.mark.parametrize(
    "regime,ssr",
    [
        (Regime.STICKY_MONEYNESS, 0.0),
        (Regime.STICKY_STRIKE, 1.0),
        (Regime.STICKY_LOCAL_VOL, 2.0),
        (1.5, 1.5),  # custom numeric SSR
    ],
)
def test_atm_vol_moves_by_ssr_times_skew(smile, regime, ssr):
    slice_, handles = smile

    def curve(k):
        return slice_.implied_vol(k, bm.SVI_T)

    delta = np.log1p(SPOT_RETURN)
    new_atm = float(shifted_smile(np.array([0.0]), curve, handles.skew, SPOT_RETURN, regime)[0])
    expected = handles.sigma0 + ssr * handles.skew * delta
    # First-order identity; curvature of the smile contributes O(delta^2).
    assert new_atm == pytest.approx(expected, abs=2.0 * abs(handles.curvature) * delta**2)


def test_shape_is_preserved_up_to_level(smile):
    """Exact invariant of the construction: for every regime the shifted
    smile equals the sticky-strike re-indexed curve plus a constant, so
    shifted(k) - sigma_old(k + delta) must be flat in k."""
    slice_, handles = smile

    def curve(k):
        return slice_.implied_vol(k, bm.SVI_T)

    k = np.linspace(-0.2, 0.2, 9)
    delta = np.log1p(SPOT_RETURN)
    for regime in (Regime.STICKY_MONEYNESS, Regime.STICKY_STRIKE, Regime.STICKY_LOCAL_VOL):
        shifted = shifted_smile(k, curve, handles.skew, SPOT_RETURN, regime)
        level = shifted - curve(k + delta)
        np.testing.assert_allclose(level, level[0], atol=1e-12)
        expected_level = (ssr_of_regime(regime) - 1.0) * handles.skew * delta
        assert level[0] == pytest.approx(expected_level, abs=1e-12)


def test_regime_resolution():
    assert ssr_of_regime("sticky_strike") == 1.0
    assert ssr_of_regime(Regime.STICKY_LOCAL_VOL) == 2.0
    assert ssr_of_regime(1.7) == 1.7
    with pytest.raises(ValueError):
        ssr_of_regime("sticky_banana")
