"""Exact full-line calendar certificate (calib.calendar_certificate).

Phase 0 of the generalized-tails + calendar arc
(Docs/generalized_tails_calendar_roadmap.md; math: book ch. 2, section "A
complete calendar certificate"). Locks the three claims that make the
certificate an acceptance authority rather than one more sampled screen:

1. EXACTNESS — the certificate minimum agrees with a brute-force dense scan
   of the stored Hermite ledger gap on generic pairs (ordered and reversed),
   and is never above it (the scan can only miss depth, never find more).
2. BETWEEN-NODE AUTHORITY — a rigged pair whose only violation lives strictly
   inside one grid segment passes EVERY nodal/stride sampled ledger screen
   and is caught by the certificate.
3. TAIL CLAUSE — the analytic tail turning point beyond the grid is found and
   the limiting order (eq. tailscalecalendar) is decided by the endpoint
   scales, with ties falling back to the asymptotic constants.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from volfit.calib.calendar import (
    CAL_STRIDE,
    calendar_floor,
    calendar_violation,
)
from volfit.calib.calendar_certificate import (
    LedgerCertificate,
    ledger_certificate,
)
from volfit.models.lqd.basis import LQDParams, endpoint_scales
from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.quadrature import build_slice

# A generic asymmetric smile pair: the far slice has uniformly larger tail
# scales, so it dominates the near one (an ordered calendar pair).
NEAR = LQDParams(L=np.log(0.12), R=np.log(0.10), a=np.array([0.020, -0.010]))
FAR = LQDParams(L=np.log(0.20), R=np.log(0.17), a=np.array([0.015, -0.008]))


def _dense_scan_min(near, far, refine: int = 16) -> tuple[float, float]:
    """Brute-force minimum of the stored Hermite ledger gap: evaluate
    A_far - A_near on a grid ``refine`` times finer than the native one."""
    n_fine = (near.z.size - 1) * refine + 1
    z_fine = np.linspace(float(near.z[0]), float(near.z[-1]), n_fine)
    gap = far.asset_share_at(z_fine) - near.asset_share_at(z_fine)
    j = int(np.argmin(gap))
    return float(gap[j]), float(z_fine[j])


@pytest.fixture(scope="module")
def pair():
    return build_slice(NEAR), build_slice(FAR)


def test_certificate_matches_dense_scan_on_ordered_pair(pair):
    near, far = pair
    cert = ledger_certificate(near, far)
    scan_min, _ = _dense_scan_min(near, far)
    # The certificate is exact for the interpolant: never above the scan, and
    # the scan (grid 16x finer) can undershoot it only by curvature ~ (h/16)^2.
    assert cert.min_gap <= scan_min + 1e-12
    assert scan_min - cert.min_gap <= 1e-7
    assert cert.min_gap > -1e-9  # the pair is calendar-ordered
    assert cert.tail_order_left and cert.tail_order_right
    assert np.isfinite(cert.z_star) and np.isfinite(cert.k_star)


def test_certificate_matches_dense_scan_on_reversed_pair(pair):
    near, far = pair
    cert = ledger_certificate(far, near)  # reversed: violation everywhere
    scan_min, z_scan = _dense_scan_min(far, near)
    assert cert.min_gap <= scan_min + 1e-12
    assert scan_min - cert.min_gap <= 1e-7
    assert cert.min_gap < 0.0
    # At least as strict as the full-grid NODAL diagnostic, by construction.
    assert -cert.min_gap >= calendar_violation(far, near) - 1e-15
    assert abs(cert.z_star - z_scan) <= 2.0 * float(near.z[1] - near.z[0])
    # Reversing a pair with strictly larger scales flips both tail orders.
    assert not cert.tail_order_left and not cert.tail_order_right


def test_identical_slices_certify_with_zero_gap(pair):
    near, _ = pair
    cert = ledger_certificate(near, near)
    assert cert.min_gap == 0.0
    assert cert.certified()
    assert cert.tail_order_left and cert.tail_order_right


def test_rigged_between_node_violation_passes_samples_fails_certificate(pair):
    """The acceptance-authority case the roadmap names: nodal ledger values
    IDENTICAL (every stride/nodal sampled screen reads zero violation), but a
    derivative rig dips the Hermite gap below zero strictly inside one
    segment. Only the certificate sees it."""
    near, far = pair
    # far2 = near at every node, with the gap's nodal DERIVATIVES rigged at
    # nodes j and j+1 (both lowered by m). The three touched segments' gap
    # cubics are, in local t with h the step:  m h t^2 (1-t)  (positive lobe),
    # -m h t (2t-1)(t-1)  (dip -m h/(6 sqrt 3) at t ~ 0.211), and
    # -m h t (t-1)^2  (the deepest dip, -4 m h / 27 at t = 1/3) — all vanish
    # at every node, so every nodal/stride ledger screen reads exactly zero.
    j = near.z.size // 2 + 12  # strictly between stride-25 nodes
    assert j % CAL_STRIDE not in (0, CAL_STRIDE - 1)
    m = 0.05
    da = near.da_dz.copy()
    da[j] -= m
    da[j + 1] -= m
    far2 = dataclasses.replace(near, da_dz=da)

    # Every sampled ledger screen passes: nodal values are byte-identical.
    assert calendar_violation(near, far2) <= 0.0
    idx, floor = calendar_floor(near, stride=CAL_STRIDE)
    assert np.all(far2.a_z[idx] >= floor)

    cert = ledger_certificate(near, far2)
    h = float(near.z[1] - near.z[0])
    expected_dip = 4.0 * m * h / 27.0  # the deepest lobe, segment (j+1, j+2)
    assert cert.min_gap < -0.8 * expected_dip
    assert cert.min_gap > -1.2 * expected_dip
    # The minimizer sits inside segment j+1, and its strike is the local one.
    assert near.z[j + 1] < cert.z_star < near.z[j + 2]
    q_local = hermite_eval(cert.z_star, float(near.z[0]), h, near.q_z, near.dq_dz)
    assert abs(cert.k_star - float(q_local)) < 1e-9
    assert not cert.certified(tol=1e-6)
    assert cert.certified(tol=1.0)  # the tolerance knob is honored


def test_tail_turning_point_beyond_grid_is_found(pair):
    """Grid-identical slices whose RIGHT tail scales disagree: the whole grid
    shows zero gap, but the far continuation decays faster, so the gap turns
    negative beyond the boundary. The analytic tail candidate must catch it
    (and the limiting order must flag the lighter far tail)."""
    near, _ = pair
    # Same ledger on the grid; far quantile shifted up at the boundary with a
    # LIGHTER tail slope: crossing at t = eps / (A_Rn - A_Rf) > 0 beyond Z.
    eps = 0.5
    far2 = dataclasses.replace(
        near, q_z=near.q_z + eps, a_right=near.a_right * 0.7
    )
    cert = ledger_certificate(near, far2)
    assert not cert.tail_order_right
    assert cert.z_star > float(near.z[-1])  # the argmin is the tail candidate
    assert cert.min_gap < 0.0
    # Mirrored rig on the LEFT: far correction decays slower (smaller A_L).
    far3 = dataclasses.replace(
        near, q_z=near.q_z - eps, a_left=near.a_left * 0.7
    )
    cert3 = ledger_certificate(near, far3)
    assert not cert3.tail_order_left
    assert cert3.tail_order_right  # right side: constants tie at equal scale


def test_tail_order_tie_falls_back_to_constants(pair):
    """Equal endpoint scales: the order clause is decided by the asymptotic
    constants (eq. tailscalecalendar's tie rule). The right constant is the
    stored boundary ledger value A(Z); the left one is the tail dollar mass
    D = e^{Q(-Z)-Z}/(1+A_L)."""
    near, _ = pair
    # Uniformly LOWER far ledger: right constants order reversed, left tail
    # mass (read from q_z, untouched) still ties equal.
    same = dataclasses.replace(near, a_z=near.a_z - 1e-3)
    cert = ledger_certificate(near, same)
    # Right constants: C_far < C_near at equal decay -> order violated.
    assert not cert.tail_order_right
    # Left: D_far == D_near at equal decay -> the gap vanishes to tolerance,
    # the tie resolves to "ordered".
    assert cert.tail_order_left
    assert cert.min_gap == pytest.approx(-1e-3, rel=1e-9)
    assert isinstance(cert, LedgerCertificate)


def test_grid_mismatch_is_refused(pair):
    near, _ = pair
    small = build_slice(FAR, n_points=4001)
    with pytest.raises(ValueError, match="share the same quadrature grid"):
        ledger_certificate(near, small)


def test_real_fitted_stack_certifies(pair):
    """Two REAL builds with strictly nested scales must certify: the gap is
    positive on the grid interior and the limiting orders hold (both scale
    pairs strictly increase near -> far)."""
    near, far = pair
    a_l_n, a_r_n = endpoint_scales(NEAR)
    a_l_f, a_r_f = endpoint_scales(FAR)
    assert a_l_f > a_l_n and a_r_f > a_r_n  # the fixture's design
    cert = ledger_certificate(near, far)
    assert cert.certified(tol=1e-9)
    assert cert.tail_order_ok
    # Interior gap is genuinely positive (not a boundary artifact): probe ATM.
    mid = near.z.size // 2
    assert float(far.a_z[mid] - near.a_z[mid]) > 1e-4
