"""volfit.calib.tails — the tail-matching rows (the Compare view's toggles).

Locks: the rows vanish when the iterate IS the reference; a raw-SVI fit to
quotes with DIFFERENT tails lands on the reference's var-swap / Lee slopes /
quoted-edge value + slope when asked (both charts); the MCS refine does the
same; the resolver clamps Lee targets under the cap, drops Lee on a
generalized-tail reference and parses the wire flags.
"""

import numpy as np
import pytest

from volfit.calib.tails import (
    LEE_CLAMP_MARGIN,
    TAIL_FLAGS,
    TailReference,
    build_tail_match,
    slope_fd,
    tail_match_residuals,
    tail_reference,
)
from volfit.calib.varswap import varswap_total_variance
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi
from volfit.models.svi_jw.svi import RawSVI

T = 0.5
#: The reference (the "LQD" of the test): heavier, more asymmetric wings.
REF = RawSVI(a=0.015, b=0.45, rho=-0.35, m=0.02, sigma=0.18)
#: The quoted smile: same belly region, lighter wings.
QUOTED = RawSVI(a=0.02, b=0.25, rho=0.05, m=0.0, sigma=0.22)
K = np.linspace(-0.35, 0.35, 15)
W = QUOTED.total_variance(K)


def _reference() -> TailReference:
    return tail_reference(REF, float(K.min()), float(K.max()), REF.wing_slopes())


def _lee_of(raw: RawSVI) -> tuple[float, float]:
    return raw.wing_slopes()


def test_rows_vanish_on_the_reference_itself():
    target = build_tail_match(_reference(), TAIL_FLAGS, T, sum_weights=float(K.size), lee_cap=1.95)
    rows = tail_match_residuals(REF.total_variance, lambda: _lee_of(REF), target)
    assert rows.size == 7  # var-swap + 2 Lee + (value, slope) x 2 edges
    assert np.max(np.abs(rows)) < 1e-6
    # The quoted smile has different tails: the same rows are far from zero.
    off = tail_match_residuals(QUOTED.total_variance, lambda: _lee_of(QUOTED), target)
    assert np.max(np.abs(off)) > 1.0


@pytest.mark.parametrize("chart", ["raw", "structural"])
def test_svi_lands_on_the_reference_lee_slopes(chart):
    target = build_tail_match(_reference(), ("lee",), T, float(K.size), lee_cap=1.95)
    plain = calibrate_svi(K, W, T, chart=chart)
    fit = calibrate_svi(K, W, T, chart=chart, tail_match=target)
    b_l, b_r = fit.raw.wing_slopes()
    assert abs(b_l - REF.wing_slopes()[0]) < 2e-3
    assert abs(b_r - REF.wing_slopes()[1]) < 2e-3
    # The unconstrained fit reproduces the QUOTED wings instead (the rows bite).
    assert abs(plain.raw.wing_slopes()[0] - QUOTED.wing_slopes()[0]) < 5e-3
    assert fit.max_iv_error > plain.max_iv_error  # the belly pays for the tails


def test_svi_lands_on_the_reference_var_swap_and_edges():
    ref = _reference()
    vs = calibrate_svi(K, W, T, tail_match=build_tail_match(ref, ("varswap",), T, float(K.size), 1.95))
    vol = lambda w: np.sqrt(w / T)  # noqa: E731
    assert abs(vol(varswap_total_variance(vs.raw.total_variance)) - vol(ref.var_swap_w)) < 2e-4
    edge = calibrate_svi(K, W, T, tail_match=build_tail_match(ref, ("edge",), T, float(K.size), 1.95))
    for e in (ref.edge_left, ref.edge_right):
        w_m = float(edge.raw.total_variance(np.array([e.k]))[0])
        assert abs(vol(w_m) - vol(e.w)) < 2e-4
        assert abs(slope_fd(edge.raw.total_variance, e.k) - e.dw) < 5e-3


def test_mcs_lands_on_the_reference_lee_and_var_swap():
    ref = _reference()
    target = build_tail_match(ref, ("varswap", "lee"), T, float(K.size), lee_cap=1.95)
    fit = calibrate_sigmoid(K, W, T, n_cores=1, tail_match=target)
    b_l, b_r = fit.lee_slopes()
    assert abs(b_l - REF.wing_slopes()[0]) < 5e-3
    assert abs(b_r - REF.wing_slopes()[1]) < 5e-3
    vol = lambda w: np.sqrt(w / T)  # noqa: E731
    assert abs(vol(varswap_total_variance(fit.implied_w)) - vol(ref.var_swap_w)) < 5e-4


@pytest.mark.parametrize("chart", ["raw", "structural"])
def test_mcs_analytic_tail_jacobian_matches_finite_differences(chart):
    """sigmoid/tail_rows: the closed-form Jacobian of the tail block (var-swap
    under the integral, Lee partials, edge value + slope) equals the central
    difference of the residual block on a fitted slice, both charts (the
    structural chart chains the base columns in calibrate._fit — locked
    through a constrained refit landing on the targets)."""
    from volfit.models.sigmoid.penalties import fd_rows
    from volfit.models.sigmoid.tail_rows import mcs_tail_jacobian, mcs_tail_rows

    ref = _reference()
    target = build_tail_match(ref, TAIL_FLAGS, T, float(K.size), lee_cap=1.95)
    fit = calibrate_sigmoid(K, W, T, n_cores=2, chart=chart, tail_match=target)
    theta = fit.to_vector()
    n_cores = len(fit.cores)
    rows = lambda th: mcs_tail_rows(th, n_cores, fit.sigma_ref, T, target)  # noqa: E731
    # eps 1e-5: the edge-slope row is itself a central difference in k, so the
    # default 1e-6 step's round-off (~1e-5 relative at a kappa on its bound)
    # would swamp the comparison; at 1e-5 the FD sits 1e-6 from the closed form.
    j_fd = fd_rows(rows, theta, eps=1e-5)
    j_an = mcs_tail_jacobian(theta, n_cores, fit.sigma_ref, T, target)
    assert j_an.shape == j_fd.shape == (7, 6 + 4 * n_cores)
    scale = np.max(np.abs(j_fd), axis=1, keepdims=True) + 1e-9
    assert np.max(np.abs(j_an - j_fd) / scale) < 1e-5
    # And the refit landed near the reference (both charts) — with all SEVEN
    # stiff rows on, the slopes are a least-squares compromise with the edge
    # rows (the module docstring), hence the looser tolerance than the
    # lee + varswap lock above.
    b_l, b_r = fit.lee_slopes()
    assert abs(b_l - REF.wing_slopes()[0]) < 2e-2 and abs(b_r - REF.wing_slopes()[1]) < 2e-2


def test_default_call_is_untouched():
    """tail_match=None is the historical objective: identical solution."""
    a = calibrate_svi(K, W, T)
    b = calibrate_svi(K, W, T, tail_match=None)
    assert a.raw == b.raw


def test_resolver_clamps_under_the_cap_and_drops_lee_on_generalized_tails():
    ref = _reference()
    steep = TailReference(
        var_swap_w=ref.var_swap_w, lee=(2.4, 0.3), edge_left=ref.edge_left, edge_right=ref.edge_right
    )
    t = build_tail_match(steep, ("lee",), T, 10.0, lee_cap=1.95)
    assert t is not None and t.lee_clamped
    assert t.lee == pytest.approx((1.95 - LEE_CLAMP_MARGIN, 0.3))
    assert t.applied == ("lee",)
    generalized = TailReference(
        var_swap_w=ref.var_swap_w, lee=None, edge_left=ref.edge_left, edge_right=ref.edge_right
    )
    assert build_tail_match(generalized, ("lee",), T, 10.0, 1.95) is None
    both = build_tail_match(generalized, ("lee", "edge"), T, 10.0, 1.95)
    assert both is not None and both.applied == ("edge",) and both.lee is None
    assert build_tail_match(ref, (), T, 10.0, 1.95) is None


def test_parse_tail_flags_orders_dedupes_and_rejects_unknown():
    from volfit.api.compare_tails import parse_tail_flags

    assert parse_tail_flags("") == ()
    assert parse_tail_flags("edge, varswap,edge") == ("varswap", "edge")
    assert parse_tail_flags("LEE") == ("lee",)
    with pytest.raises(ValueError, match="unknown"):
        parse_tail_flags("varswap,tails")
