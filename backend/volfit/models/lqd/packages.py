"""Trader-package shape controls for the LQD slice (committee revision R5).

The ATM-orthogonal chart's kernel basis V is unique only up to rotation, so
"shape direction 1" can rotate or flip between calibrations — a sound
interface for one-session sculpting, not a persistent trader control.  The
stable vocabulary is the market's own quote packages (risk reversals,
butterflies, var swap), and this module expresses the kernel in it:

For a package vector P(theta) (evaluated by volfit.calib.operators on the
slice's own smile), restrict its Jacobian to ker J_handles and take the
least-norm kernel combination that moves ONE package by one unit while the
ATM handles stay put to first order:

    xi_i  =  argmin |xi|  s.t.  (dP/dtheta V) xi = e_i ,

so ``directions[:, i] = V xi_i`` is "one unit of package i, handles fixed,
minimal shape motion".  The returned cross-talk matrix says how much each
package direction moves the OTHER packages — the honest print of how
independent the controls really are on this slice (they are exactly
independent only to first order and only where the package Jacobian has full
kernel rank; ``rank`` and ``condition`` report when it does not).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.calib.operators import evaluate_operators
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.ortho import ATMCoordinates
from volfit.models.lqd.quadrature import build_slice

#: Default package set: the quote operators a desk actually holds.  ATM is
#: deliberately absent — the level/skew/curvature handles already own it.
DEFAULT_PACKAGES = ("RR25", "BF25", "RR10", "BF10", "VarSwap")


@dataclass(frozen=True)
class PackageControls:
    """Kernel shape controls expressed as market packages.

    ``values`` are the packages at the reference slice; ``directions``
    (d x n_pkg) move one package by one unit (vol units) with handles fixed
    to first order; ``cross_talk`` (n_pkg x n_pkg) is the package response
    to each direction (identity iff the controls are exactly independent);
    ``condition`` is the SVD condition of the kernel-restricted package
    Jacobian and ``rank`` its numerical rank — fewer independent packages
    than requested means the slice cannot move them separately.
    """

    names: tuple[str, ...]
    values: np.ndarray
    directions: np.ndarray
    cross_talk: np.ndarray
    condition: float
    rank: int


def package_vector(params: LQDParams, t: float, names) -> np.ndarray:
    """P(theta): the named packages evaluated on the slice's own smile."""
    slice_ = build_slice(params)
    vals = evaluate_operators(lambda k: slice_.implied_w(k), t, list(names))
    return np.array([vals[n] for n in names], dtype=float)


def package_jacobian(
    params: LQDParams, t: float, names, step: float = 1e-6
) -> np.ndarray:
    """dP/dtheta by central differences (same protocol as atm_jacobian)."""
    theta = params.to_vector()
    jac = np.empty((len(names), theta.size))
    for j in range(theta.size):
        h = step * max(1.0, abs(theta[j]))
        up, dn = theta.copy(), theta.copy()
        up[j] += h
        dn[j] -= h
        jac[:, j] = (
            package_vector(LQDParams.from_vector(up), t, names)
            - package_vector(LQDParams.from_vector(dn), t, names)
        ) / (2.0 * h)
    return jac


def build_package_controls(
    chart: ATMCoordinates, names=DEFAULT_PACKAGES, rank_tol: float = 1e-8
) -> PackageControls:
    """Express the chart's kernel in package coordinates (module docstring)."""
    names = tuple(names)
    params, t = chart.reference, chart.t
    p_jac = package_jacobian(params, t, names)          # (n_pkg, d)
    pv = p_jac @ chart.shape                            # kernel-restricted
    u_svd, s, vt = np.linalg.svd(pv, full_matrices=False)
    rank = int(np.sum(s > rank_tol * s[0])) if s.size and s[0] > 0.0 else 0
    s_inv = np.where(s > rank_tol * (s[0] if s.size else 1.0), 1.0 / s, 0.0)
    xi = vt.T @ (s_inv[:, None] * u_svd.T)              # pinv(pv): (d-3, n_pkg)
    directions = chart.shape @ xi                       # (d, n_pkg)
    return PackageControls(
        names=names,
        values=package_vector(params, t, names),
        directions=directions,
        cross_talk=p_jac @ directions,
        condition=float(s[0] / max(s[-1], 1e-300)) if s.size else float("inf"),
        rank=rank,
    )
