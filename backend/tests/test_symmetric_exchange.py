"""In-solver active-set exchange for hard LQD calendar constraints.

Tails+calendar arc Phase 4 / forward roadmap V3.0
(calib.symmetric_exchange). The book's exchange loop
(ch. 2, B_implementation "Exchange algorithm for global calendar order")
enforces the FULL-LINE ledger order G_far(z) >= G_near(z)
(eq. globalledgerconstraint) as hard per-rank rows in the joint stacked
solve, certified each round by the EXACT Phase 0 certificate at the
acceptance grid. Locks:

1. The per-rank ledger rows' analytic Jacobian (asset_share_rows: +dA_near /
   -dA_far block writes) matches finite differences with a nonempty active
   set — the stacked-Jacobian lock extended to the exchange rows.
2. A rigged adjacent pair whose only violation lives beyond the sampled
   screens' support (the theta-realizable analogue of the certificate's
   between-node dip rig: invisible to every stride/window screen, so the
   penalty+escalation repair never fires) is left FAILING the certificate by
   repair_surface and is certified by exchange_refit.
3. A clean ladder never enters the exchange: round 0, thetas byte-identical
   to the joint-free independent fits (the fast-path identity, mirroring the
   clean-ladder lock of the symmetric solver).
4. Convergence postcondition: converged=True implies every adjacent pair's
   FRESH full-grid certificate passes at the acceptance tolerance.
5. Idempotence: exchanging an already-certified stack is a no-op.
6. Common-alpha power tails (the arc's ratified policy) go through the same
   loop: the rank rows' Jacobian and the certificate's power-continuation
   candidates are alpha-correct.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.calib.calendar_certificate import ledger_certificate
from volfit.calib.symmetric import (
    SliceSpec,
    _spec_params,
    build_interface,
    repair_surface,
)
from volfit.calib.symmetric_exchange import (
    _CAL_TOL,
    EXCHANGE_W,
    IFACE_BASE_WEIGHT,
    exchange_ladder,
    exchange_refit,
)
from volfit.calib.symmetric_stack import stacked_functions
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.quadrature import build_slice

K_GRID = np.linspace(*bm.SVI_FIT_RANGE, 41)
W_NEAR = bm.SVI_RAW.total_variance(K_GRID)

# The rigged wing pair: the near expiry is quoted WIDE with steep wings, the
# far expiry NARROW and flat, sitting just above the near curve on the common
# support. Every sampled screen — the 33-node tapered interface grid, the
# stride/window diagnostics — is confined to (a margin around) that support
# and reads clean, but the near slice's steep extrapolated wing overtakes the
# far ledger out at z* ~ 7 (eq. calgapderivative's crossing beyond the quoted
# span): only the full-line certificate sees it, and only the exchange's
# per-rank ledger rows (+ the eq. tailscalecalendar slope rows) can repair it.
K_WIDE = np.linspace(-0.40, 0.40, 33)
W_WIDE = 0.020 + 0.50 * K_WIDE**2
T_NEAR = 0.5
K_NARROW = np.linspace(-0.15, 0.15, 13)
W_NARROW = 0.0245 + 0.55 * K_NARROW**2
T_FAR = 0.75


def _spec(t, k, w, **kw):
    return SliceSpec(
        t=t, k=np.asarray(k, float), w=np.asarray(w, float),
        fit_kwargs=dict(n_order=6, **kw),
    )


def _fd_jacobian(fun, x0):
    fd = None
    for j in range(x0.size):
        h = 1e-6 * max(1.0, abs(x0[j]))
        xp, xm = x0.copy(), x0.copy()
        xp[j] += h
        xm[j] -= h
        col = (fun(xp) - fun(xm)) / (2.0 * h)
        if fd is None:
            fd = np.empty((col.size, x0.size))
        fd[:, j] = col
    return fd


@pytest.fixture(scope="module")
def rigged():
    """Independent fits + screen-blind repair + exchange of the wing pair."""
    near = calibrate_slice(K_WIDE, W_WIDE, t=T_NEAR, n_order=6)
    far = calibrate_slice(K_NARROW, W_NARROW, t=T_FAR, n_order=6)
    specs = [_spec(T_NEAR, K_WIDE, W_WIDE), _spec(T_FAR, K_NARROW, W_NARROW)]
    repair = repair_surface(specs, [near.params.to_vector(), far.params.to_vector()])
    iface = build_interface(specs[0], specs[1], tail_contract=True)
    result = exchange_refit(specs, repair.thetas, [iface], IFACE_BASE_WEIGHT)
    return specs, repair, iface, result


# ------------------------------------------------------- 1. Jacobian lock
def test_rank_rows_jacobian_matches_finite_differences():
    """The stacked FD lock extended to the exchange's per-rank ledger rows
    (eq. globalledgerconstraint): active hinge rows write +dA_near into the
    near block and -dA_far into the far block via asset_share_rows."""
    near = calibrate_slice(K_GRID, W_NEAR, t=0.5)
    far = calibrate_slice(K_GRID, 0.8 * W_NEAR, t=1.0)
    specs = [_spec(0.5, K_GRID, W_NEAR), _spec(1.0, K_GRID, 0.8 * W_NEAR)]
    iface = build_interface(specs[0], specs[1])
    ranks = [np.array([-2.0, -0.5, 0.4, 1.5])]

    fun, jac, _split = stacked_functions(
        specs,
        [near.params.to_vector(), far.params.to_vector()],
        [iface],
        1.0,
        active_ranks=ranks,
        rank_weight=EXCHANGE_W,
    )
    x0 = np.concatenate([near.params.to_vector(), far.params.to_vector()])
    res = fun(x0)
    # The rank rows are the trailing block and must be genuinely ACTIVE here
    # (far quoted below near => G_near > G_far in the belly), so the FD probe
    # crosses no hinge kink.
    assert np.all(res[-4:] > 0.0)

    analytic = jac(x0)
    fd = _fd_jacobian(fun, x0)
    assert analytic.shape == fd.shape
    scale = np.abs(fd).max()
    assert scale > 0.0
    assert np.max(np.abs(analytic - fd)) < 1e-4 * scale
    # And the rank rows specifically (not just the dominant data rows).
    rows = slice(res.size - 4, res.size)
    rscale = np.abs(fd[rows]).max()
    assert rscale > 0.0
    assert np.max(np.abs(analytic[rows] - fd[rows])) < 1e-4 * rscale


def test_empty_active_set_leaves_stack_byte_identical():
    """active_ranks=None / empty arrays add no rows and change no values —
    the pre-exchange stacked problem is untouched (byte-identity)."""
    near = calibrate_slice(K_GRID, W_NEAR, t=0.5)
    far = calibrate_slice(K_GRID, 0.8 * W_NEAR, t=1.0)
    specs = [_spec(0.5, K_GRID, W_NEAR), _spec(1.0, K_GRID, 0.8 * W_NEAR)]
    iface = build_interface(specs[0], specs[1])
    thetas0 = [near.params.to_vector(), far.params.to_vector()]
    x0 = np.concatenate(thetas0)
    fun0, jac0, _ = stacked_functions(specs, thetas0, [iface], 1.0)
    fun1, jac1, _ = stacked_functions(
        specs, thetas0, [iface], 1.0,
        active_ranks=[np.empty(0)], rank_weight=EXCHANGE_W,
    )
    assert fun0(x0).tobytes() == fun1(x0).tobytes()
    assert jac0(x0).tobytes() == jac1(x0).tobytes()


# ------------------------------------- 2. rigged pair: screens blind, exchange fixes
def test_rigged_wing_pair_screen_blind_repair_leaves_certificate_failing(rigged):
    """The sampled screen reads clean (no component, no refit — the
    penalty+escalation loop never even fires), yet the full-line certificate
    fails on the repaired ladder: the violation lives beyond the sampled
    support, exactly the class Phase 0 made visible."""
    specs, repair, _iface, _result = rigged
    assert repair.refit == [False, False]  # the screen is blind to the wing
    assert repair.components == []
    assert all(v == 0.0 for v in repair.violations_before)
    slices = [
        build_slice(_spec_params(t, s.fit_kwargs))
        for t, s in zip(repair.thetas, specs)
    ]
    cert = ledger_certificate(slices[0], slices[1])
    assert not cert.certified(_CAL_TOL)
    assert cert.min_gap < -1e-3  # a genuine dip, far beyond tolerance
    assert cert.k_star > float(np.max(K_WIDE))  # strictly beyond every quote


def test_rigged_wing_pair_exchange_certifies(rigged):
    """exchange_refit clears the pair the penalty pass left: the failing
    certificate's minimizer becomes a hard ledger row and the joint solve
    reorders the wing ('the active ranks are few' — one round here)."""
    specs, _repair, _iface, result = rigged
    assert result.converged
    assert 1 <= result.rounds <= 3
    assert result.irreducible == ()
    assert result.active_ranks[0].size >= 1
    assert all(c.certified(_CAL_TOL) for c in result.certificates)
    # The repair is a wing repair: both slices still price their own quotes
    # to a desk-reasonable error (no bulldozed belly).
    for theta, s in zip(result.thetas, specs):
        slc = build_slice(_spec_params(theta, s.fit_kwargs))
        iv_err = np.max(np.abs(np.sqrt(slc.implied_w(s.k) / s.t) - np.sqrt(s.w / s.t)))
        assert iv_err < 0.02  # < 200 vol bp on the quotes


# ------------------------------------------------- 3. clean ladder fast path
def test_clean_ladder_exchange_never_enters_and_is_byte_identical():
    """A certified ladder returns round 0 with the INPUT thetas untouched —
    the exchange analogue of the clean-ladder lock (fast path identity)."""
    near = calibrate_slice(K_GRID, W_NEAR, t=0.5)
    far = calibrate_slice(K_GRID, 2.0 * W_NEAR, t=1.0, init=near.params)
    specs = [_spec(0.5, K_GRID, W_NEAR), _spec(1.0, K_GRID, 2.0 * W_NEAR)]
    thetas0 = [near.params.to_vector(), far.params.to_vector()]

    iface = build_interface(specs[0], specs[1], tail_contract=True)
    result = exchange_refit(specs, thetas0, [iface], IFACE_BASE_WEIGHT)
    assert result.converged and result.rounds == 0
    assert result.irreducible == ()
    assert all(r.size == 0 for r in result.active_ranks)
    for out, orig in zip(result.thetas, thetas0):
        assert out.tobytes() == orig.tobytes()

    # The ladder-level wrapper (the phase-B entry) is equally untouched.
    thetas, touched, certs = exchange_ladder(specs, thetas0)
    assert touched == [False, False]
    assert all(c.certified(_CAL_TOL) for c in certs)
    for out, orig in zip(thetas, thetas0):
        assert out.tobytes() == orig.tobytes()


# ------------------------------------------- 4. convergence postcondition
def test_converged_exchange_passes_fresh_certificates(rigged):
    """converged=True is a THEOREM about the returned thetas, not a flag:
    rebuilding every slice at the acceptance grid and re-running the
    certificate per adjacent pair passes at the acceptance tolerance."""
    specs, _repair, _iface, result = rigged
    assert result.converged
    slices = [
        build_slice(_spec_params(t, s.fit_kwargs))
        for t, s in zip(result.thetas, specs)
    ]
    for j in range(len(slices) - 1):
        fresh = ledger_certificate(slices[j], slices[j + 1])
        assert fresh.certified(_CAL_TOL)


# ----------------------------------------------------------- 5. idempotence
def test_exchange_is_idempotent_on_certified_stack(rigged):
    """Re-running the exchange on its own converged output is a no-op:
    round 0, thetas byte-identical, no new active ranks."""
    specs, _repair, iface, result = rigged
    again = exchange_refit(specs, result.thetas, [iface], IFACE_BASE_WEIGHT)
    assert again.converged and again.rounds == 0
    assert all(r.size == 0 for r in again.active_ranks)
    for out, orig in zip(again.thetas, result.thetas):
        assert out.tobytes() == orig.tobytes()


# ------------------------------------------------- 6. common-alpha power tails
def test_common_alpha_pair_goes_through_exchange():
    """The same rigged wing pair under the ratified common-alpha policy
    (alpha = 0.25 both sides): the rank rows' Jacobian rides the alpha-aware
    sensitivity pass and the certificate's POWER-continuation tail
    candidates (eq. rightcontinuation) drive the exchange to a certified
    stack whose params carry the exponents."""
    a = dict(alpha_left=0.25, alpha_right=0.25)
    near = calibrate_slice(K_WIDE, W_WIDE, t=T_NEAR, n_order=6, **a)
    far = calibrate_slice(K_NARROW, W_NARROW, t=T_FAR, n_order=6, **a)
    specs = [
        _spec(T_NEAR, K_WIDE, W_WIDE, **a),
        _spec(T_FAR, K_NARROW, W_NARROW, **a),
    ]
    thetas0 = [near.params.to_vector(), far.params.to_vector()]
    cert0 = ledger_certificate(near.slice, far.slice)
    assert not cert0.certified(_CAL_TOL)  # the alpha rig still violates

    iface = build_interface(specs[0], specs[1], tail_contract=True)
    result = exchange_refit(specs, thetas0, [iface], IFACE_BASE_WEIGHT)
    assert result.converged
    assert result.rounds >= 1
    slices = [
        build_slice(_spec_params(t, s.fit_kwargs))
        for t, s in zip(result.thetas, specs)
    ]
    assert slices[0].params.alpha_left == 0.25
    assert slices[1].params.alpha_right == 0.25
    assert ledger_certificate(slices[0], slices[1]).certified(_CAL_TOL)

    # FD lock of the rank rows at alpha > 0 (the branched d_az pass).
    ranks = [np.array([result.active_ranks[0][0], 0.5])]
    fun, jac, _split = stacked_functions(
        specs, thetas0, [iface], 1.0,
        active_ranks=ranks, rank_weight=EXCHANGE_W,
    )
    x0 = np.concatenate(thetas0)
    analytic = jac(x0)
    fd = _fd_jacobian(fun, x0)
    scale = np.abs(fd).max()
    assert scale > 0.0
    assert np.max(np.abs(analytic - fd)) < 1e-4 * scale
