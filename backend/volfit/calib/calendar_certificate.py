"""Exact full-line calendar certificate for adjacent LQD slices.

Book chapter 2 (Papers/book/chapters/02_lqd, section "A complete calendar
certificate"): with both expiries normalized by their forwards, absence of
calendar arbitrage is call order at every strike, which is EXACTLY ledger
order at every rank (thm. ledgerorder):

    Delta G(z) = G_far(z) - G_near(z) >= 0   for all z in R
                                            (eq. globalledgerconstraint),

and the gap's derivative has one sign per region (eq. calgapderivative):

    (Delta G)'(z) = rho(z) { e^{x_near(z)} - e^{x_far(z)} },

so Delta G can turn only where the two quantile curves cross. Its infimum
over the whole line is therefore attained on a FINITE candidate set — the
interior turning points, the grid nodes, the analytic tail turning points
under the linear quantile continuations — plus the limiting order at
z -> +-inf decided by the endpoint scales (eq. tailscalecalendar), ties
broken by the next asymptotic constant. A nonnegative gap at every candidate
proves the continuum property: a finite certificate, no strike cutoff.

Discrete exactness. The stored curves are cubic Hermite interpolants with
exact nodal derivatives (dA/dz = -e^{Q} u(1-u)), and ``call_price`` prices
from that interpolant — so the object to certify is the interpolated gap
itself. Per segment the gap is a single cubic; its derivative is the
closed-form quadratic that interpolates eq. calgapderivative's right-hand
side at the nodes. The certificate isolates the roots of that quadratic (the
discrete counterpart of the chapter's cubic quantile-crossing problem — one
vectorized root problem per segment) and evaluates the gap there and at
every node: the minimum is EXACT for the priced object, not a sample.
Beyond the grid both slices continue with the exponential tails
``call_price`` uses; the tail gap is a two-exponential expression whose only
possible turning point is the crossing of the linear quantile continuations,
evaluated in closed form.

Phase 0 of Docs/generalized_tails_calendar_roadmap.md: this certificate is
the acceptance/publish authority (api.quality readiness, api.export
blockers); the stride/window sampled diagnostics in volfit.calib.calendar
remain as cheap in-loop screens. The limiting tail order is REPORTED but
does not gate in Phase 0: nothing in today's solver imposes the
eq. tailscalecalendar endpoint-scale monotonicity yet (that is Phase 2's
endpoint-chart rows), and a publish gate a fit cannot yet be asked to
satisfy would block publishes with no repair path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.quadrature import LQDSlice

#: Endpoint-scale tie band for the limiting-order clause. Slope differences
#: inside this band are float noise (the turning point they would imply sits
#: astronomically far outside the grid), so the order is decided by the next
#: asymptotic constant instead — eq. tailscalecalendar's "apart from exact
#: ties, where the next asymptotic constant decides".
SLOPE_TIE = 1e-12

#: Relative tie band for those asymptotic constants: they scale like
#: e^{Q(+-Z) - Z} (~1e-13 for equity tails), so only a RELATIVE comparison is
#: meaningful there.
CONST_RTOL = 1e-9

#: Coefficient degeneracy threshold of the per-segment root problems,
#: relative to the segment's own coefficient scale (a segment whose gap is
#: constant/linear/at machine noise contributes its endpoints only — by
#: eq. calgapderivative the gap cannot turn inside it).
_DEGENERATE = 1e-14


@dataclass(frozen=True)
class LedgerCertificate:
    """Outcome of the exact full-line calendar certificate for one pair.

    ``min_gap`` is the exact minimum of the ledger gap
    Delta G = G_far - G_near over the whole real line (grid + analytic
    tails); >= 0 (up to the caller's tolerance) proves
    eq. globalledgerconstraint for the stored pair. ``z_star``/``k_star``
    locate the minimizing rank coordinate / log-moneyness (at a turning
    point the two quantile curves cross, so the strike there is shared).
    ``tail_order_left/right`` report the limiting order at z -> -/+inf
    (eq. tailscalecalendar; advisory in Phase 0 — see module docstring).
    ``n_turning_points`` counts the interior turning points isolated — the
    discrete quantile-curve crossings of eq. calgapderivative.
    """

    min_gap: float
    z_star: float
    k_star: float
    tail_order_left: bool
    tail_order_right: bool
    n_turning_points: int

    @property
    def tail_order_ok(self) -> bool:
        """Both limiting orders hold — the eq. tailscalecalendar clause."""
        return self.tail_order_left and self.tail_order_right

    def certified(self, tol: float = 0.0) -> bool:
        """Full-line gap nonnegativity to ``tol`` — the Phase-0 publish gate
        (the limiting-order clause rides separately as ``tail_order_ok``)."""
        return self.min_gap >= -tol


def _interior_turning_points(
    gap: np.ndarray, dgap: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interior turning points of the piecewise-cubic Hermite gap.

    On segment i with local t in (0, 1) the gap is
    c0 + c1 t + c2 t^2 + c3 t^3 (values ``gap``, derivatives ``dgap`` at the
    nodes); its derivative 3 c3 t^2 + 2 c2 t + c1 is solved in closed form,
    vectorized over all segments at once. Returns (t, segment index, gap
    value) for every root strictly inside a segment. Degenerate segments
    (constant or linear gap) have no interior turning point and contribute
    their endpoints only, which the nodal candidate set already carries.
    """
    p0, p1 = gap[:-1], gap[1:]
    m0, m1 = dgap[:-1] * h, dgap[1:] * h
    d = p1 - p0
    c0, c1 = p0, m0
    c2 = 3.0 * d - 2.0 * m0 - m1
    c3 = m0 + m1 - 2.0 * d
    a, b, c = 3.0 * c3, 2.0 * c2, c1
    scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), np.abs(c))
    with np.errstate(all="ignore"):
        quad = np.abs(a) > _DEGENERATE * scale
        disc = b * b - 4.0 * a * c
        real = quad & (disc >= 0.0)
        sq = np.sqrt(np.maximum(disc, 0.0))
        # Citardauq pairing: the stable root first, its cofactor second —
        # avoids the classic cancellation when b^2 >> |4ac|.
        qq = -0.5 * (b + np.where(b >= 0.0, sq, -sq))
        r1 = np.where(real, qq / a, np.nan)
        r2 = np.where(real, c / qq, np.nan)  # qq = 0 -> inf/nan, filtered below
        lin = ~quad & (np.abs(b) > _DEGENERATE * scale)
        r3 = np.where(lin, -c / b, np.nan)
    ts, idxs, vals = [], [], []
    for r in (r1, r2, r3):
        keep = np.isfinite(r) & (r > 0.0) & (r < 1.0)
        if keep.any():
            i = np.nonzero(keep)[0]
            t = r[keep]
            ts.append(t)
            idxs.append(i)
            vals.append(((c3[i] * t + c2[i]) * t + c1[i]) * t + c0[i])
    if not ts:
        empty = np.empty(0)
        return empty, np.empty(0, dtype=int), empty
    return np.concatenate(ts), np.concatenate(idxs), np.concatenate(vals)


def _tail_candidates(
    near: LQDSlice, far: LQDSlice
) -> tuple[list[tuple[float, float, float]], bool, bool]:
    """Analytic tail turning points + limiting orders beyond the grid.

    Right of the grid each ledger continues as
    A(z) = A(Z) e^{(A_R - 1)(z - Z)} (the exponential tail ``call_price``
    prices with; the stored boundary node A(Z) = e^{Q(Z)-Z}/(1-A_R) is used
    verbatim so the seam is exact); left of the grid the correction
    1 - A(z) decays as e^{(1 + A_L)(z + Z)}. Each side's two-exponential gap
    can turn only where the linear quantile continuations cross — one
    closed-form candidate per side, kept when it falls beyond the grid.
    The limiting order compares decay rates (endpoint scales), then the
    asymptotic constants on a tie (eq. tailscalecalendar).
    Returns ([(gap, z, k) candidates], order_left, order_right).
    """
    z_max = float(far.z[-1])
    cands: list[tuple[float, float, float]] = []

    # Right tail: gap(Z + t) = C_f e^{(A_Rf - 1) t} - C_n e^{(A_Rn - 1) t}.
    c_n, c_f = float(near.a_z[-1]), float(far.a_z[-1])
    ds = far.a_right - near.a_right
    if abs(ds) > SLOPE_TIE:
        order_right = ds > 0.0  # the farther tail must not decay faster
        t = -(float(far.q_z[-1]) - float(near.q_z[-1])) / ds
        if t > 0.0:
            g = c_f * float(np.exp((far.a_right - 1.0) * t)) - c_n * float(
                np.exp((near.a_right - 1.0) * t)
            )
            k = float(near.q_z[-1]) + near.a_right * t  # quantiles cross here
            cands.append((g, z_max + t, k))
    else:
        order_right = c_f >= c_n * (1.0 - CONST_RTOL)

    # Left tail: gap(-Z + t) = D_n e^{(1 + A_Ln) t} - D_f e^{(1 + A_Lf) t},
    # t <= 0, with D = e^{Q(-Z) - Z}/(1 + A_L) the left tail dollar mass
    # (build_slice's left endpoint correction).
    d_n = float(np.exp(near.q_z[0] - z_max)) / (1.0 + near.a_left)
    d_f = float(np.exp(far.q_z[0] - z_max)) / (1.0 + far.a_left)
    dsl = far.a_left - near.a_left
    if abs(dsl) > SLOPE_TIE:
        order_left = dsl > 0.0  # the farther correction must not decay slower
        t = -(float(far.q_z[0]) - float(near.q_z[0])) / dsl
        if t < 0.0:
            g = d_n * float(np.exp((1.0 + near.a_left) * t)) - d_f * float(
                np.exp((1.0 + far.a_left) * t)
            )
            k = float(near.q_z[0]) + near.a_left * t
            cands.append((g, float(far.z[0]) + t, k))
    else:
        order_left = d_f <= d_n * (1.0 + CONST_RTOL)

    return cands, order_left, order_right


def ledger_certificate(near: LQDSlice, far: LQDSlice) -> LedgerCertificate:
    """Certify calendar order of one adjacent pair on the whole real line.

    Both slices must share the quadrature grid (the production default —
    ``build_slice`` rebuilds every accepted fit on it), so the ledger gap is
    a nodal difference with exact nodal derivatives. The candidate set —
    every node, every interior turning point, the analytic tail turning
    points — yields the EXACT minimum of the stored gap; the limiting orders
    complete the continuum statement (see module docstring).
    """
    if (
        near.z.shape != far.z.shape
        or near.z[0] != far.z[0]
        or near.z[-1] != far.z[-1]
    ):
        raise ValueError("slices must share the same quadrature grid")
    z = near.z
    z0 = float(z[0])
    h = float(z[1] - z[0])
    gap = far.a_z - near.a_z
    dgap = far.da_dz - near.da_dz

    t_int, seg, v_int = _interior_turning_points(gap, dgap, h)
    cand_v = np.concatenate([gap, v_int])
    cand_z = np.concatenate([z, z0 + (seg + t_int) * h])
    j = int(np.argmin(cand_v))
    min_gap, z_star = float(cand_v[j]), float(cand_z[j])
    # Log-moneyness at the minimizer: at a turning point the two quantile
    # curves cross (eq. calgapderivative), so the mean is exact there; at a
    # nodal minimizer it is the natural midpoint strike of the pair.
    q_n = hermite_eval(z_star, z0, h, near.q_z, near.dq_dz)
    q_f = hermite_eval(z_star, z0, h, far.q_z, far.dq_dz)
    k_star = 0.5 * float(q_n + q_f)

    tail, order_left, order_right = _tail_candidates(near, far)
    for g, z_t, k_t in tail:
        if g < min_gap:
            min_gap, z_star, k_star = g, z_t, k_t

    return LedgerCertificate(
        min_gap=min_gap,
        z_star=z_star,
        k_star=k_star,
        tail_order_left=bool(order_left),
        tail_order_right=bool(order_right),
        n_turning_points=int(t_int.size),
    )
