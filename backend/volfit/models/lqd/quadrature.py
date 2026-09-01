"""LQD slice construction: quantile quadrature and call pricing.

Everything works in the logit coordinate z = log(u / (1-u)), where the
endpoint singularities of the log quantile density vanish and

    dQ/dz = e^{g(Lambda(z))}                (eq. q_logit)

with Lambda the logistic function. One quadrature pass per parameter vector
gives the quantile Q(z), the martingale shift mu (eq. mu_norm) and the upper
asset-share integral A(z) (eq. asset_share); every strike is then priced by
monotone interpolation through

    C(k) = A(z_k) - e^k (1 - u_k)           (eq. call_logit)

with analytic tail corrections (eqs. right/left_tail_corr).
Equation references are to Docs/lqd_model_note.tex.

Generalized tails (book ch. 2, Papers/book/chapters/02_lqd): per-side
exponents alpha_-/alpha_+ in [0, 1/2] slow the transport through the
parameter-independent log gauges (eq. xspeed),

    dQ/dz = exp{ g - alpha_- log l_-(z) - alpha_+ log l_+(z) },

interpolating the tails from exponential (alpha = 0, this module's original
model, byte-identical code path) to Gaussian rate (alpha = 1/2). For
alpha > 0 the closed-form tail corrections are replaced by log-domain
quadrature of the power continuation (volfit.models.lqd.tails) behind the
saddle guard x'(Z) <= 1 - eps (eq. operationaltailguard), and the lambda_+
< 1 wall no longer applies (eq. martcondition).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, lru_cache

import numpy as np
from scipy.special import expit

from volfit.core.black import implied_total_variance_otm
from volfit.models.lqd.basis import LQDParams, endpoint_scales, g_eval, legendre_matrix
from volfit.models.lqd.interp import hermite_eval, hermite_invert
from volfit.models.lqd.tails import (
    EPS_TAIL,
    continuation_speed,
    left_tail_put,
    right_tail_call,
    tail_mass_left,
    tail_mass_right,
)

# 4th-order cumulative quadrature on the uniform grid: the compiled
# scipy-replica kernel (volfit.core.cumsimp) — bit-identical to
# scipy.integrate.cumulative_simpson by construction (basic IEEE arithmetic
# only, same operation order; test_batched_kernels locks the equality), with
# scipy itself as the automatic fallback when numba is unavailable.
from volfit.core.cumsimp import cumulative_simpson_uniform as _cumquad


# Default grid: uniform in z, symmetric, odd-sized so z = 0 is a node.
# Z = 40 puts the truncation error far below double-precision vega noise
# for equity-like tail scales (note section 5.2).
Z_MAX = 40.0
N_POINTS = 8001

# Right-tail admissibility buffer: A_R must stay below 1 - EPS_AR.
EPS_AR = 1e-6

# Interior-excursion overflow budget (committee point 5): exp() overflows past
# ~709.78, so a body blow-up hidden by endpoint cancellation (A_R < 1 while
# max g is huge) must be refused as a clean ValueError — which the
# calibrator's penalty branch already catches — never propagated as inf/nan
# prices. Sane fitted slices sit orders of magnitude below this.
EXP_BUDGET = 700.0


# The quadrature grid (z, u = expit(z), u(1-u)) and the Legendre basis
# P_n(1-2u) are *parameter-independent*: they depend only on (z_max, n_points)
# and the model order. A single LQD calibration calls build_slice ~900 times
# (finite-difference Jacobian over 7 params x ~11 iterations), so recomputing
# the 8001-point linspace/expit/Legendre recursion every call is pure waste —
# it was ~40% of build_slice. These small LRU caches make the static arrays
# byte-identical to the recomputed ones while building each slice ~1.7x faster.
# The arrays are returned read-only so an accidental in-place write surfaces as
# an error instead of silently corrupting every future slice that shares them.
@lru_cache(maxsize=8)
def _static_grid(z_max: float, n_points: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cached (z, u, u(1-u)) for the symmetric logit quadrature grid.

    u(1-u) is formed as expit(z) * expit(-z): the naive u * (1 - u) collapses
    to exactly 0 once expit(z) rounds to 1.0 (z > ~36.7, committee point 5),
    silently zeroing the integrand on the outer grid nodes; each factor here
    is evaluated on its own accurate side, so the product stays exact into
    the far wings.
    """
    z = np.linspace(-z_max, z_max, n_points)
    u = expit(z)
    u1mu = u * expit(-z)
    for arr in (z, u, u1mu):
        arr.flags.writeable = False
    return z, u, u1mu


@lru_cache(maxsize=8)
def _legendre_grid(z_max: float, n_points: int, n_max: int) -> np.ndarray:
    """Cached Legendre matrix P_0..P_{n_max} evaluated at x = 1 - 2u."""
    _, u, _ = _static_grid(z_max, n_points)
    leg = legendre_matrix(n_max, 1.0 - 2.0 * u)
    leg.flags.writeable = False
    return leg


def _softplus(t: np.ndarray) -> np.ndarray:
    """log(1 + e^t), evaluated per side in its stable regime."""
    return np.maximum(t, 0.0) + np.log1p(np.exp(-np.abs(t)))


@lru_cache(maxsize=8)
def _log_gauges(z_max: float, n_points: int) -> tuple[np.ndarray, np.ndarray]:
    """Cached log tail gauges (log l_-, log l_+) on the static grid.

    l_∓(Lambda(z)) = 1 + softplus(∓z) (eq. ellgauges in the logit
    coordinate). Parameter-independent, so they are cached alongside the
    static grid; the tail exponents simply scale them inside the one exp()
    that builds dQ/dz (eq. xspeed). Read-only like the other cached arrays.
    """
    z, _, _ = _static_grid(z_max, n_points)
    lm = np.log1p(_softplus(-z))
    lp = np.log1p(_softplus(z))
    for arr in (lm, lp):
        arr.flags.writeable = False
    return lm, lp


@dataclass(frozen=True)
class LQDSlice:
    """A fully built (normalized) LQD slice ready for pricing.

    Attributes hold the shared quadrature grid: quantile ``q_z`` = Q(z),
    asset share ``a_z`` = A(z), and the martingale shift ``mu``.
    """

    params: LQDParams
    z: np.ndarray
    u: np.ndarray
    q_z: np.ndarray
    a_z: np.ndarray
    dq_dz: np.ndarray  # exact nodal dQ/dz = e^{g}
    da_dz: np.ndarray  # exact nodal dA/dz = -e^{Q} u(1-u)
    mu: float
    a_left: float  # endpoint scale A_L
    a_right: float  # endpoint scale A_R

    @property
    def _step(self) -> float:
        return float(self.z[1] - self.z[0])

    def strike_to_z(self, k: np.ndarray | float) -> np.ndarray:
        """Solve Q(z_k) = k by Hermite-Newton inversion (machine precision)."""
        return hermite_invert(
            np.asarray(k, dtype=float), float(self.z[0]), self._step, self.q_z, self.dq_dz
        )

    def asset_share_at(self, z: np.ndarray | float) -> np.ndarray:
        """Upper asset-share integral A(z) at arbitrary z by Hermite interpolation.

        At a grid node A(z) returns the nodal ``a_z`` exactly (Hermite t = 0),
        so calendar constraints expressed in z-values match node-indexed ones
        bit-for-bit at the native grid while remaining valid when the slice is
        built on a coarser optimization grid (see calibrate_slice).
        """
        return hermite_eval(
            np.asarray(z, dtype=float), float(self.z[0]), self._step, self.a_z, self.da_dz
        )

    # ---------------------------------------------------------------- pricing
    def call_price(self, k: np.ndarray | float) -> np.ndarray:
        """Normalized call C(k) via eq. (call_logit).

        Both Q and A are interpolated with cubic Hermite polynomials built on
        their exact nodal derivatives, so priced curves are smooth enough for
        clean finite-difference Greeks.
        """
        k_arr = np.asarray(k, dtype=float)
        z_k = self.strike_to_z(k_arr)
        a_k = hermite_eval(z_k, float(self.z[0]), self._step, self.a_z, self.da_dz)
        # e^k (1 - u_k) in log space: 1 - expit(z) rounds to exactly 0 for
        # z > ~36.7 while e^k is enormous there, which used to step the far
        # right wing up to A(z_k) (committee point 5). log(1 - u) is
        # -softplus(z), so the product is exp(k - logaddexp(0, z)).
        c = a_k - np.exp(k_arr - np.logaddexp(0.0, z_k))
        # Strikes beyond the quantile range of the z grid: strike_to_z clamps
        # there, so price them on the slice's OWN tail continuation (the same
        # form the quadrature's tail corrections use, so the seam at Q(+-Z)
        # is continuous). Exponential subclass (alpha = 0, byte-identical
        # path): with z_r = Z + (k - Q(Z))/A_R,
        #   C(k) = e^{k - z_r} A_R / (1 - A_R),
        # and by the mirrored derivation on the left, with
        # z_l = -Z + (k - Q(-Z))/A_L,
        #   P(k) = e^{k + z_l} A_L / (1 + A_L).
        # For alpha > 0 the root is the power form (eq. rightroot) and the
        # price eq. beyondgrid, both under eq. rightcontinuation (tails.py).
        # Exponents are clipped at 0 only to keep the UNUSED where-branch from
        # overflowing; in the applied region they are always negative. Keeps
        # far-display wings positive, wing-law-consistent and theta-responsive
        # (the functional band's Jacobian must not die at the grid edge).
        if self.a_right > 0.0:
            if self.params.alpha_right == 0.0:
                z_r = self.z[-1] + (k_arr - self.q_z[-1]) / self.a_right
                tail_r = np.exp(np.minimum(k_arr - z_r, 0.0)) * (
                    self.a_right / (1.0 - self.a_right))
            else:
                tail_r = right_tail_call(
                    k_arr, float(self.q_z[-1]), self.a_right,
                    self.params.alpha_right, float(self.z[-1]))
            c = np.where(k_arr > self.q_z[-1], tail_r, c)
        if self.a_left > 0.0:
            if self.params.alpha_left == 0.0:
                z_l = self.z[0] + (k_arr - self.q_z[0]) / self.a_left
                tail_l = (1.0 - np.exp(k_arr)) + np.exp(
                    np.minimum(k_arr + z_l, 0.0)) * (self.a_left / (1.0 + self.a_left))
            else:
                tail_l = (1.0 - np.exp(k_arr)) + left_tail_put(
                    k_arr, float(self.q_z[0]), self.a_left,
                    self.params.alpha_left, float(self.z[-1]))
            c = np.where(k_arr < self.q_z[0], tail_l, c)
        return c

    @cached_property
    def _lower_share(self) -> np.ndarray:
        """Lower asset-share integral Lo(z) — the left mirror of ``a_z``
        (volfit.models.lqd.putside). Lazy: only display / inversion paths
        price puts, so build_slice (the calibration hot path) never pays."""
        from volfit.models.lqd.putside import lower_share
        return lower_share(self)

    def put_price(self, k: np.ndarray | float) -> np.ndarray:
        """Normalized put P(k) = e^k u_k - Lo(z_k), priced on the LEFT side
        (volfit.models.lqd.putside): full relative accuracy into the deep
        lower wing, where the parity route C - (1 - e^k) rounds the time
        value away entirely on short-dated slices."""
        from volfit.models.lqd.putside import put_price
        return put_price(self, np.asarray(k, dtype=float))

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Implied total variance w(k) by tail-accurate Black inversion of
        the OTM instrument — call at k >= 0, put below, each priced on its
        own clean side (core.black.implied_total_variance_otm). Inverting
        calls everywhere floored the left time value at ~1e-16 absolute —
        the short-dated flat-left / ragged-right smile display bug."""
        k_arr = np.asarray(k, dtype=float)
        price = np.asarray(self.call_price(k_arr), dtype=float)
        if np.any(k_arr < 0.0):
            price = np.where(k_arr < 0.0, self.put_price(k_arr), price)
        return implied_total_variance_otm(k_arr, price)

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        """Implied Black volatility at expiry ``t``."""
        return np.sqrt(self.implied_w(k) / t)

    # ------------------------------------------------------------ diagnostics
    def density(self) -> tuple[np.ndarray, np.ndarray]:
        """Risk-neutral log-return density f_X on the grid x = Q(z).

        f_X(Q(u)) = 1 / q(u) = u (1-u) e^{-g(u)}; positivity is structural.
        Evaluated in log space so the far tails do not underflow to zero.
        For alpha > 0, log x' = g - a_- log l_- - a_+ log l_+ (eq. xspeed):
        the gauge terms raise the density where the transport slows.
        """
        g = g_eval(self.params, self.u)
        # log u = -log(1 + e^{-z}),  log(1-u) = -log(1 + e^{z}).
        log_pdf = -np.logaddexp(0.0, -self.z) - np.logaddexp(0.0, self.z) - g
        if self.params.alpha_left != 0.0 or self.params.alpha_right != 0.0:
            lm, lp = _log_gauges(float(self.z[-1]), self.z.size)
            log_pdf = (
                log_pdf
                + self.params.alpha_left * lm
                + self.params.alpha_right * lp
            )
        return self.q_z, np.exp(log_pdf)

    def martingale_check(self) -> float:
        """Numerical value of E[e^X] (should be 1 after normalization)."""
        mass = np.exp(self.q_z) * self.u * expit(-self.z)  # u(1-u), wing-stable
        total = float(np.trapezoid(mass, self.z))
        z_end = self.z[-1]
        if self.params.alpha_right == 0.0:
            total += float(np.exp(self.q_z[-1] - z_end)) / (1.0 - self.a_right)
        else:
            total += float(self.a_z[-1])  # the stored normalized right tail mass
        if self.params.alpha_left == 0.0:
            total += float(np.exp(self.q_z[0] - z_end)) / (1.0 + self.a_left)
        else:
            total += tail_mass_left(
                float(self.q_z[0]), self.a_left, self.params.alpha_left, float(z_end)
            )
        return total

    def var_swap_strike(self) -> float:
        """Var-swap total variance -2 E[X] (log contract replication).

        The integrand Q(z) u(1-u) decays like z e^{-|z|}; truncation beyond
        Z_MAX is negligible at double precision.
        """
        u1mu = self.u * expit(-self.z)  # u(1-u), wing-stable
        return -2.0 * float(np.trapezoid(self.q_z * u1mu, self.z))


def build_slice(
    params: LQDParams,
    z_max: float = Z_MAX,
    n_points: int = N_POINTS,
) -> LQDSlice:
    """Run the quadrature pipeline of note section 5.2 for one parameter set.

    Raises ValueError when the right integrability condition fails: in the
    exponential subclass (alpha_+ = 0) that is A_R < 1 (eq. AR_condition —
    the forward would be infinite); for alpha_+ > 0 the forward is always
    finite (eq. martcondition) and the refusal is instead the numerical
    saddle guard x'(Z) <= 1 - eps (eq. operationaltailguard) — never a
    silent truncation of mass that peaks beyond the grid.
    """
    a_left, a_right = endpoint_scales(params)
    al, ar = params.alpha_left, params.alpha_right
    if ar == 0.0:
        if a_right >= 1.0 - EPS_AR:
            raise ValueError(f"A_R = {a_right:.6f} violates the integrability bound A_R < 1")
    elif continuation_speed(a_right, ar, z_max) > 1.0 - EPS_TAIL:
        raise ValueError(
            "tail saddle guard: continuation speed x'(Z) = "
            f"{continuation_speed(a_right, ar, z_max):.6f} is within "
            f"{EPS_TAIL} of the martingale saddle x' = 1"
        )

    # Static grid and Legendre basis are cached on (z_max, n_points[, order]);
    # only the parameter-dependent combination g(u) is formed per call.
    z, u, u1mu = _static_grid(z_max, n_points)
    dz = 2.0 * z_max / (n_points - 1)  # uniform step → Simpson's fast equal path
    g = (1.0 - u) * params.L + u * params.R
    if params.a.size:
        g = g + params.a @ _legendre_grid(z_max, n_points, params.order)[2:]
    if al != 0.0 or ar != 0.0:
        # Generalized tails: the gauges fold into the ONE exponent that
        # builds the speed (eq. xspeed). alpha = 0 skips this entirely —
        # no pow, no reordered float ops (byte-identity is test-locked).
        lm, lp = _log_gauges(z_max, n_points)
        g = g - al * lm - ar * lp
    g_max = float(np.max(g))
    if not np.isfinite(g_max) or g_max > EXP_BUDGET:
        raise ValueError(f"interior overflow: max g = {g_max:.3g} exceeds the exp budget")
    dq_dz = np.exp(g)  # dQ/dz, eq. (q_logit)

    # Anchored quantile Qbar(z) = int_0^z e^{g} ds  (eq. qbar); the grid is
    # symmetric so the anchor z = 0 is the center node.
    q_bar = _cumquad(dq_dz, dx=dz, initial=0.0)
    q_bar = q_bar - q_bar[n_points // 2]
    q_max = float(np.max(q_bar))
    if not np.isfinite(q_max) or q_max > EXP_BUDGET:
        raise ValueError(f"interior overflow: max Qbar = {q_max:.3g} exceeds the exp budget")

    # Martingale normalization mu = -log int e^{Qbar} u(1-u) dz  (eq. mu_norm)
    # with the tail corrections: closed forms in the exponential subclass
    # (eqs. right/left_tail_corr), log-domain quadrature of the power
    # continuation for alpha > 0 (eq. rightcontinuation and its mirror).
    mass = np.exp(q_bar) * u1mu
    total = float(np.trapezoid(mass, z))
    if ar == 0.0:
        corr_r = float(np.exp(q_bar[-1] - z_max)) / (1.0 - a_right)
    else:
        corr_r = tail_mass_right(float(q_bar[-1]), a_right, ar, z_max)
    if al == 0.0:
        corr_l = float(np.exp(q_bar[0] - z_max)) / (1.0 + a_left)
    else:
        corr_l = tail_mass_left(float(q_bar[0]), a_left, al, z_max)
    total += corr_r
    total += corr_l
    mu = -np.log(total)
    q_z = mu + q_bar

    # Upper asset-share integral A(z) = int_z^inf e^{Q} u(1-u) ds by reverse
    # cumulative quadrature plus the right tail correction.
    mass_n = mass * np.exp(mu)
    rev = _cumquad(mass_n[::-1], dx=dz, initial=0.0)[::-1]
    if ar == 0.0:
        a_z = rev + float(np.exp(q_z[-1] - z_max)) / (1.0 - a_right)
    else:
        a_z = rev + corr_r * float(np.exp(mu))

    return LQDSlice(
        params=params,
        z=z,
        u=u,
        q_z=q_z,
        a_z=a_z,
        dq_dz=dq_dz,
        da_dz=-mass_n,
        mu=float(mu),
        a_left=a_left,
        a_right=a_right,
    )
