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
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.special import expit

from volfit.core.black import implied_total_variance
from volfit.models.lqd.basis import LQDParams, endpoint_scales, g_eval, legendre_matrix
from volfit.models.lqd.interp import hermite_eval, hermite_invert

try:  # 4th-order cumulative quadrature (scipy >= 1.12); trapezoid fallback.
    from scipy.integrate import cumulative_simpson as _cumquad
except ImportError:  # pragma: no cover
    from scipy.integrate import cumulative_trapezoid as _ct

    def _cumquad(y: np.ndarray, dx: float, initial: float = 0.0) -> np.ndarray:
        return _ct(y, dx=dx, initial=initial)


# Default grid: uniform in z, symmetric, odd-sized so z = 0 is a node.
# Z = 40 puts the truncation error far below double-precision vega noise
# for equity-like tail scales (note section 5.2).
Z_MAX = 40.0
N_POINTS = 8001

# Right-tail admissibility buffer: A_R must stay below 1 - EPS_AR.
EPS_AR = 1e-6


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
    """Cached (z, u, u(1-u)) for the symmetric logit quadrature grid."""
    z = np.linspace(-z_max, z_max, n_points)
    u = expit(z)
    u1mu = u * (1.0 - u)
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
        u_k = expit(z_k)
        a_k = hermite_eval(z_k, float(self.z[0]), self._step, self.a_z, self.da_dz)
        return a_k - np.exp(k_arr) * (1.0 - u_k)

    def put_price(self, k: np.ndarray | float) -> np.ndarray:
        """Normalized put via parity C - P = 1 - e^k."""
        k_arr = np.asarray(k, dtype=float)
        return self.call_price(k_arr) - (1.0 - np.exp(k_arr))

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Implied total variance w(k) by Black inversion of the call curve."""
        return implied_total_variance(k, self.call_price(k))

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        """Implied Black volatility at expiry ``t``."""
        return np.sqrt(self.implied_w(k) / t)

    # ------------------------------------------------------------ diagnostics
    def density(self) -> tuple[np.ndarray, np.ndarray]:
        """Risk-neutral log-return density f_X on the grid x = Q(z).

        f_X(Q(u)) = 1 / q(u) = u (1-u) e^{-g(u)}; positivity is structural.
        Evaluated in log space so the far tails do not underflow to zero.
        """
        g = g_eval(self.params, self.u)
        # log u = -log(1 + e^{-z}),  log(1-u) = -log(1 + e^{z}).
        log_pdf = -np.logaddexp(0.0, -self.z) - np.logaddexp(0.0, self.z) - g
        return self.q_z, np.exp(log_pdf)

    def martingale_check(self) -> float:
        """Numerical value of E[e^X] (should be 1 after normalization)."""
        mass = np.exp(self.q_z) * self.u * (1.0 - self.u)
        total = float(np.trapezoid(mass, self.z))
        z_end = self.z[-1]
        total += float(np.exp(self.q_z[-1] - z_end)) / (1.0 - self.a_right)
        total += float(np.exp(self.q_z[0] - z_end)) / (1.0 + self.a_left)
        return total

    def var_swap_strike(self) -> float:
        """Var-swap total variance -2 E[X] (log contract replication).

        The integrand Q(z) u(1-u) decays like z e^{-|z|}; truncation beyond
        Z_MAX is negligible at double precision.
        """
        return -2.0 * float(np.trapezoid(self.q_z * self.u * (1.0 - self.u), self.z))


def build_slice(
    params: LQDParams,
    z_max: float = Z_MAX,
    n_points: int = N_POINTS,
) -> LQDSlice:
    """Run the quadrature pipeline of note section 5.2 for one parameter set.

    Raises ValueError when the right integrability condition A_R < 1 fails
    (eq. AR_condition): the forward would be infinite.
    """
    a_left, a_right = endpoint_scales(params)
    if a_right >= 1.0 - EPS_AR:
        raise ValueError(f"A_R = {a_right:.6f} violates the integrability bound A_R < 1")

    # Static grid and Legendre basis are cached on (z_max, n_points[, order]);
    # only the parameter-dependent combination g(u) is formed per call.
    z, u, u1mu = _static_grid(z_max, n_points)
    dz = 2.0 * z_max / (n_points - 1)  # uniform step → Simpson's fast equal path
    g = (1.0 - u) * params.L + u * params.R
    if params.a.size:
        g = g + params.a @ _legendre_grid(z_max, n_points, params.order)[2:]
    dq_dz = np.exp(g)  # dQ/dz, eq. (q_logit)

    # Anchored quantile Qbar(z) = int_0^z e^{g} ds  (eq. qbar); the grid is
    # symmetric so the anchor z = 0 is the center node.
    q_bar = _cumquad(dq_dz, dx=dz, initial=0.0)
    q_bar = q_bar - q_bar[n_points // 2]

    # Martingale normalization mu = -log int e^{Qbar} u(1-u) dz  (eq. mu_norm),
    # with the analytic endpoint corrections (eqs. right/left_tail_corr).
    mass = np.exp(q_bar) * u1mu
    total = float(np.trapezoid(mass, z))
    total += float(np.exp(q_bar[-1] - z_max)) / (1.0 - a_right)
    total += float(np.exp(q_bar[0] - z_max)) / (1.0 + a_left)
    mu = -np.log(total)
    q_z = mu + q_bar

    # Upper asset-share integral A(z) = int_z^inf e^{Q} u(1-u) ds by reverse
    # cumulative quadrature plus the right tail correction.
    mass_n = mass * np.exp(mu)
    rev = _cumquad(mass_n[::-1], dx=dz, initial=0.0)[::-1]
    a_z = rev + float(np.exp(q_z[-1] - z_max)) / (1.0 - a_right)

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
