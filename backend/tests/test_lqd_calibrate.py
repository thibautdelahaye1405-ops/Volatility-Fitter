"""End-to-end calibration: logistic init -> SVI-JW target, per note section 8."""

import numpy as np

from tests import benchmarks as bm
from volfit.models.lqd.basis import endpoint_scales
from volfit.models.lqd.calibrate import calibrate_slice


def test_calibrate_to_svi_benchmark():
    k = np.linspace(*bm.SVI_FIT_RANGE, 66)
    w_quotes = bm.SVI_RAW.total_variance(k)

    result = calibrate_slice(k, w_quotes, t=bm.SVI_T, n_order=6)

    # Fit quality: the note reaches 1.2 vol bp; allow optimizer slack to 5 bp.
    assert result.max_iv_error < 5.0e-4, f"max IV error {result.max_iv_error:.2e}"

    # Structural admissibility and diagnostics.
    a_l, a_r = endpoint_scales(result.params)
    assert 0.0 < a_r < 1.0
    assert 0.0 < a_l
    assert result.slice.martingale_check() == np.float64(1.0) or abs(
        result.slice.martingale_check() - 1.0
    ) < 1e-8

    # Wing scales should land near the note's fitted values (loose bands:
    # wings are weakly identified inside the quoted strike range).
    assert abs(a_l - bm.SVI_LQD_A_LEFT) < 0.08
    assert abs(a_r - bm.SVI_LQD_A_RIGHT) < 0.05


def test_calibration_is_fast_enough():
    """Phase-1 budget: one slice fit should stay well under a second of CPU.

    This is a coarse regression guard, not a benchmark (CI machines vary).
    """
    import time

    k = np.linspace(*bm.SVI_FIT_RANGE, 40)
    w_quotes = bm.SVI_RAW.total_variance(k)
    start = time.perf_counter()
    calibrate_slice(k, w_quotes, t=bm.SVI_T, n_order=6)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"calibration took {elapsed:.1f}s"
