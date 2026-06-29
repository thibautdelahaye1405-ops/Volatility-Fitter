"""SIV 2-core cap + put-wing no-butterfly regularizer (FINDINGS_calibration_arb R6).

The Multi-Core SIV menu is capped at 2 cores (cores >=3 overfit + manufacture wing
arb), and a soft Durrleman penalty pushes g(k) >= 0 in the UNQUOTED wings. The
penalty is zero on an arb-free slice, so liquid names stay byte-identical; it only
bites where SIV would have produced a butterfly violation.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from tests import benchmarks as bm
from volfit.api.schemas import FitSettings
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv


def _min_g(slice_, k: np.ndarray) -> float:
    g = np.asarray(slice_.gatheral_g(k), dtype=float)
    g = g[np.isfinite(g)]
    return float(g.min()) if g.size else 0.0


# ----------------------------------------------------------------- the 2-core cap
def test_cores_clamped_to_two():
    """nCores > 2 clamps to 2 (so a persisted desk loads); negatives still reject."""
    assert FitSettings(nCores=5).nCores == 2
    assert FitSettings(nCores=3).nCores == 2
    assert FitSettings(nCores=2).nCores == 2
    with pytest.raises(ValidationError):
        FitSettings(nCores=-1)


# ----------------------------------------------------- the put-wing regularizer
#: An arbitraged slice: a strong put hat that breaks convexity (g<0) in the wing.
_ARB = MultiCoreSiv(
    v0=0.04, s0=-0.02, k0=0.5, z0=0.0, kappa_p=8.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.25, cores=(HatCore(alpha=-0.9, c=-1.3, h=0.5, kappa=8.0),),
)
_K = np.linspace(-0.35, 0.30, 21)
_W = _ARB.implied_w(_K)
_GRID = np.linspace(_K.min(), _K.max(), 151)


def test_penalty_removes_wing_arb():
    """Fitting the arbitraged smile: without the penalty SIV-2 reproduces the g<0
    wing; with it, g is pushed back to >= 0."""
    unpenalized = calibrate_sigmoid(_K, _W, 0.25, n_cores=2, wing_penalty=0.0)
    penalized = calibrate_sigmoid(_K, _W, 0.25, n_cores=2, wing_penalty=1e3)
    assert _min_g(unpenalized, _GRID) < -0.5  # the unpenalized fit IS arbitraged
    assert _min_g(penalized, _GRID) >= -0.05  # the penalty repairs it
    assert _min_g(penalized, _GRID) > _min_g(unpenalized, _GRID) + 1.0  # large gain


def test_penalty_byte_identical_on_arb_free_slice():
    """On the clean SVI benchmark (no arb) the penalty is zero, so the fit is
    unchanged whether it is on or off — liquid names are never perturbed."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    off = calibrate_sigmoid(k, w, bm.SVI_T, n_cores=2, wing_penalty=0.0).implied_w(k)
    on = calibrate_sigmoid(k, w, bm.SVI_T, n_cores=2, wing_penalty=1e3).implied_w(k)
    np.testing.assert_allclose(on, off, rtol=1e-9, atol=1e-10)


def test_penalty_off_default():
    """``wing_penalty=0`` (the library default) leaves the calibration unpenalized."""
    a = calibrate_sigmoid(_K, _W, 0.25, n_cores=2).implied_w(_GRID)
    b = calibrate_sigmoid(_K, _W, 0.25, n_cores=2, wing_penalty=0.0).implied_w(_GRID)
    np.testing.assert_array_equal(a, b)
