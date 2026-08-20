"""V3.1 leg 5: kernel governance — the book's "governed dial" made mechanical.

After a sigmoid fit, hats whose |alpha| sits below the quote-noise resolution
floor (a hat's central vol displacement ≈ alpha / (2 sigma_ref) measured
against the fit's own rms vol error) are pruned and the slice refit ONCE
without them; the returned ``cores`` length is the EFFECTIVE core count (which
the service's ModelInfo "Cores R" row already reports, being len(cores)).
Byte-identical whenever nothing prunes.
"""

from __future__ import annotations

import numpy as np

from tests import benchmarks as bm
from volfit.models.sigmoid import HatCore, MultiCoreSiv, calibrate_sigmoid
from volfit.models.sigmoid.seeding import alpha_resolution_floor


BASE = MultiCoreSiv(
    v0=0.04, s0=-0.004, k0=0.15, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.25,
)
K = np.linspace(-0.35, 0.30, 21)


def test_resolution_floor_is_two_sigma_rms():
    """The floor formula: alpha_min = 2 sigma_ref * rms_vol (doc-comment in
    seeding.alpha_resolution_floor) — an exact fit resolves everything."""
    theta = np.array([0.04, -0.004, 0.15, 0.0, 4.0, 3.0])
    z = K / (0.2 * np.sqrt(0.25))
    from volfit.models.sigmoid.calibrate import _V_FLOOR, _eval_v

    exact_vol = np.sqrt(np.maximum(_eval_v(theta, z, 0), _V_FLOOR))
    assert alpha_resolution_floor(theta, z, exact_vol, 0, 0.2) == 0.0
    off_vol = exact_vol + 0.002  # a uniform 20bp miss
    floor = alpha_resolution_floor(theta, z, off_vol, 0, 0.2)
    assert abs(floor - 2.0 * 0.2 * 0.002) < 1e-12


def test_sub_noise_hats_are_pruned_and_refit():
    """Noisy quotes + a heavy amplitude ridge: the fitted hats shrink below the
    resolution floor and are pruned — the returned slice reports its EFFECTIVE
    core count (0 here), not the requested dial."""
    rng = np.random.default_rng(11)
    noise = rng.normal(0.0, 0.0025, K.size)  # 25bp deterministic quote noise
    w = ((BASE.vol(K) + noise) ** 2) * 0.25
    fit = calibrate_sigmoid(K, w, 0.25, n_cores=2, ridge=10.0)
    assert len(fit.cores) == 0  # both hats were sub-resolution
    # The default ridge resolves its hats on the same data — nothing pruned.
    default = calibrate_sigmoid(K, w, 0.25, n_cores=2)
    assert len(default.cores) == 2


def test_nothing_pruned_is_byte_identical_semantics():
    """Resolvable hats survive untouched: the clean two-core round-trip keeps
    both cores and still recovers the curve (the pre-governance lock — this is
    the 'byte-identical when nothing prunes' contract exercised end to end)."""
    truth = MultiCoreSiv(
        v0=0.04, s0=-0.004, k0=0.02, z0=0.0, kappa_p=2.5, kappa_c=3.0,
        sigma_ref=0.20, t=0.5,
        cores=(HatCore(0.005, -0.7, 0.4, 5.0), HatCore(-0.004, 0.0, 0.5, 4.0)),
    )
    k = np.linspace(-0.5, 0.5, 41)
    fit = calibrate_sigmoid(k, truth.implied_w(k), t=0.5, n_cores=2)
    assert len(fit.cores) == 2
    assert np.max(np.abs(fit.vol(k) - truth.vol(k))) < 10e-4


def test_governance_never_worsens_the_benchmark_fit():
    """On the clean SPX-like benchmark the governed fit is the historical fit
    (no pruning fires), so the cores-buy-precision ordering is intact."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    quote_vol = np.sqrt(w / bm.SVI_T)
    base = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=0)
    cored = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=2)
    assert len(cored.cores) == 2
    assert np.max(np.abs(cored.vol(k) - quote_vol)) < np.max(np.abs(base.vol(k) - quote_vol))
