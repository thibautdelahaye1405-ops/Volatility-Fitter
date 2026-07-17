"""Symmetric surface solver: screen -> violation components -> joint GN.

Locks the redesign's contracts:
- a clean ladder is EXACTLY its independent fits (fast path, no joint solve);
- the acute-short-slice phantom does not trigger the solver at all
  (confinement handles it — tests/test_calendar_confinement.py);
- a genuine identified violation is repaired SYMMETRICALLY: both slices give,
  allocation follows the data information, and the far slice ends closer to
  its quotes than under the sequential floor (which pins the near slice);
- repairs are LOCAL: slices outside a violation component are untouched;
- the stacked block-bidiagonal Jacobian matches finite differences.
"""

import numpy as np

from tests import benchmarks as bm
from volfit.calib import ExpiryQuotes, calibrate_surface
from volfit.calib.symmetric import (
    SliceSpec,
    _components,
    build_interface,
    calibrate_surface_symmetric,
    interface_violation,
    stacked_functions,
)
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.quadrature import build_slice

K_GRID = np.linspace(*bm.SVI_FIT_RANGE, 41)
W_NEAR = bm.SVI_RAW.total_variance(K_GRID)


def _spec(t, k, w):
    return SliceSpec(
        t=t, k=np.asarray(k, float), w=np.asarray(w, float),
        fit_kwargs=dict(n_order=6),
    )


def test_components_helper():
    assert _components([False, True, True, False, True]) == [(1, 3), (4, 5)]
    assert _components([True]) == [(0, 1)]
    assert _components([False, False]) == []


def test_clean_ladder_is_exactly_the_independent_fits():
    fit, repair = calibrate_surface_symmetric(
        [
            ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
            ExpiryQuotes(t=1.0, k=K_GRID, w=2.0 * W_NEAR),
        ]
    )
    assert not any(repair.refit)
    assert repair.components == []
    assert all(v <= 5e-5 for v in repair.violations_before)
    assert fit.max_calendar_violation < 1e-6
    assert all(r.max_iv_error < 5e-4 for r in fit.results)


def test_acute_phantom_ladder_does_not_trigger_the_solver():
    """The Note-10 phantom case: far quoted wider and far above the acute near
    slice — the identified screen must stay silent (no joint solve at all)."""
    k_near = np.linspace(-0.06, 0.06, 13)
    k_far = np.linspace(-0.30, 0.30, 25)
    fit, repair = calibrate_surface_symmetric(
        [
            ExpiryQuotes(t=0.02, k=k_near, w=0.0008 + 0.6 * k_near**2),
            ExpiryQuotes(t=0.25, k=k_far, w=0.010 + 0.004 * k_far**2),
        ]
    )
    assert not any(repair.refit)
    far_free = calibrate_slice(k_far, 0.010 + 0.004 * k_far**2, t=0.25)
    assert fit.results[1].max_iv_error < far_free.max_iv_error + 1e-6


def test_stacked_jacobian_matches_finite_differences():
    """The block-bidiagonal analytic Jacobian (data blocks + interface rows,
    active hinges) agrees with central finite differences of the stacked
    residual at the independent-fit point of a genuinely violating pair."""
    near = calibrate_slice(K_GRID, W_NEAR, t=0.5)
    far = calibrate_slice(K_GRID, 0.8 * W_NEAR, t=1.0)
    specs = [_spec(0.5, K_GRID, W_NEAR), _spec(1.0, K_GRID, 0.8 * W_NEAR)]
    # tail_contract=True also covers the seam price rows and the linear
    # wing-slope rows (both active at this violating pair).
    iface = build_interface(specs[0], specs[1], tail_contract=True)
    assert iface is not None and iface.seam_k is not None
    # The hinge must be active at the free fits (far sits below near).
    assert interface_violation(near.slice, far.slice, iface) > 1e-3

    fun, jac, _split = stacked_functions(
        specs,
        [near.params.to_vector(), far.params.to_vector()],
        [iface],
        1.0,
    )
    x0 = np.concatenate([near.params.to_vector(), far.params.to_vector()])
    analytic = jac(x0)
    fd = np.empty_like(analytic)
    for j in range(x0.size):
        h = 1e-6 * max(1.0, abs(x0[j]))
        xp, xm = x0.copy(), x0.copy()
        xp[j] += h
        xm[j] -= h
        fd[:, j] = (fun(xp) - fun(xm)) / (2.0 * h)
    scale = np.abs(fd).max()
    assert scale > 0.0
    assert np.max(np.abs(analytic - fd)) < 1e-4 * scale


def test_real_violation_is_shared_symmetrically():
    """Far quoted BELOW near in total variance on the same strikes: a hard
    identified violation. The sequential floor pins the near slice and pushes
    the WHOLE correction into the far fit; the symmetric solve must split it —
    and still end (essentially) calendar-clean."""
    quotes = [
        ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
        ExpiryQuotes(t=1.0, k=K_GRID, w=0.8 * W_NEAR),
    ]
    seq = calibrate_surface(quotes, enforce_calendar=True)
    sym, repair = calibrate_surface_symmetric(quotes)

    assert repair.refit == [True, True]
    assert repair.violations_before[0] > 1e-3
    assert repair.max_slack < 1e-4  # constraint feasible: crushed, not slack

    near_err, far_err = (r.max_iv_error for r in sym.results)
    # Both slices absorb part of the inconsistency...
    assert near_err > 1e-3 and far_err > 1e-3
    # ...and the far slice ends CLOSER to its quotes than sequential left it,
    # while the near slice (pinned at ~0 error by sequential) gives some.
    assert far_err < seq.results[1].max_iv_error
    assert near_err > seq.results[0].max_iv_error
    assert sym.max_calendar_violation < 1e-3


def test_tail_contract_orders_the_extrapolated_wings():
    """extrapolation-guard ON: the acute near slice's steep extrapolated wing
    (in-support clean, so untouched by default) now triggers the low-dim tail
    contract — after repair the wings are ordered at the seam and in slope,
    while the far slice stays on its quotes (a nudge, not the old full-grid
    bulldozer)."""
    from volfit.calib.symmetric import calibrate_surface_symmetric as fit_sym
    from volfit.calib.symmetric import tail_violation

    k_near = np.linspace(-0.06, 0.06, 13)
    k_far = np.linspace(-0.30, 0.30, 25)
    w_near = 0.0008 + 0.6 * k_near**2
    w_far = 0.010 + 0.004 * k_far**2
    quotes = [
        ExpiryQuotes(t=0.02, k=k_near, w=w_near),
        ExpiryQuotes(t=0.25, k=k_far, w=w_far),
    ]
    far_free = calibrate_slice(k_far, w_far, t=0.25)

    fit, repair = fit_sym(quotes, tail_contract=True)
    assert repair.refit == [True, True]  # the wing crossing triggers the solve
    # The contract is (essentially) met after repair...
    pair = build_interface(
        _spec(0.02, k_near, w_near), _spec(0.25, k_far, w_far), tail_contract=True
    )
    assert (
        tail_violation(fit.results[0].slice, fit.results[1].slice, pair) < 5e-4
    )
    # ...the far fit stays on its quotes, and the identified region is clean.
    assert fit.results[1].max_iv_error < far_free.max_iv_error + 2e-4
    assert fit.max_calendar_violation < 1e-6


def test_repair_is_local_to_the_violation_component():
    """Slice 3 sits far above the violating (1, 2) pair: it must come out of
    the symmetric pipeline byte-identical to its independent fit."""
    quotes = [
        ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
        ExpiryQuotes(t=1.0, k=K_GRID, w=0.8 * W_NEAR),
        ExpiryQuotes(t=2.0, k=K_GRID, w=4.0 * W_NEAR),
    ]
    sym, repair = calibrate_surface_symmetric(quotes)
    assert repair.refit == [True, True, False]
    assert repair.components == [(0, 1)]

    # Reproduce the independent fit of slice 3 (same warm-start chain).
    r0 = calibrate_slice(K_GRID, W_NEAR, t=0.5)
    r1 = calibrate_slice(K_GRID, 0.8 * W_NEAR, t=1.0, init=r0.params)
    r2 = calibrate_slice(K_GRID, 4.0 * W_NEAR, t=2.0, init=r1.params)
    assert np.array_equal(repair.thetas[2], r2.params.to_vector())
    # And the untouched slice still clears the repaired pair (no new violation).
    pair = build_interface(_spec(1.0, K_GRID, 0.8 * W_NEAR), _spec(2.0, K_GRID, 4.0 * W_NEAR))
    lifted = build_slice(sym.results[1].params)
    assert interface_violation(lifted, sym.results[2].slice, pair) <= 5e-5
