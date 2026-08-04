"""Multi-start basin audit for the paper's convergence claim (section 9).

Ten randomized starts per node on the two featured liquid strips (SPY
2026-12-18 and NVDA 2027-12-17): the cold start's L and R are perturbed
by up to +-50% relative and the body coefficients seeded with small
random values (fixed RNG seed 20260812 — fully deterministic), then each
start is fitted to convergence with the production objective (mid fit,
production ridge, logistic chart).  Optima are clustered by
max |dtheta| < 1e-4; the paper's sentence holds only if every start of
every node lands in ONE basin.
"""

from __future__ import annotations

import numpy as np

from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import calibrate_slice, logistic_init

import data
from macros import STORE, num, sci

N_STARTS = 10
SEED = 20260812
CLUSTER_TOL = 1e-4


def _perturbed_starts(node: data.Node, rng) -> list[LQDParams]:
    """The cold start plus nine deterministic perturbations of it."""
    w0 = float(np.interp(0.0, node.k, node.iv_mid**2 * node.t))
    base = logistic_init(w0, n_order=node.order)
    n = np.arange(2, node.order + 1)
    starts = [base]
    for _ in range(N_STARTS - 1):
        starts.append(LQDParams(
            base.L * (1.0 + rng.uniform(-0.5, 0.5)),
            base.R * (1.0 + rng.uniform(-0.5, 0.5)),
            rng.normal(0.0, 0.05, n.size) * (2.0 / n),
        ))
    return starts


def _clusters(thetas: list[np.ndarray]) -> list[list[int]]:
    """Greedy clustering by max |dtheta| < CLUSTER_TOL to a representative."""
    groups: list[list[int]] = []
    for i, theta in enumerate(thetas):
        for group in groups:
            if float(np.max(np.abs(theta - thetas[group[0]]))) < CLUSTER_TOL:
                group.append(i)
                break
        else:
            groups.append([i])
    return groups


def multistart() -> str:
    """Fit every start, cluster the optima, emit the audit macros."""
    rng = np.random.default_rng(SEED)
    worst_basins, worst_dtheta, worst_div_bp = 0, 0.0, 0.0
    lines = []
    for key in (data.SPY_DEC, data.NVDA_LONG):
        node = data.node(*key)
        w = node.iv_mid**2 * node.t
        fits = [
            calibrate_slice(node.k, w, node.t, n_order=node.order,
                            reg_lambda=1e-6, reg_power=1.0,
                            coords="logistic", init=start)
            for start in _perturbed_starts(node, rng)
        ]
        thetas = [fit.params.to_vector() for fit in fits]
        groups = _clusters(thetas)
        main = max(groups, key=len)
        spread = max(
            (float(np.max(np.abs(thetas[i] - thetas[j])))
             for i in main for j in main), default=0.0)
        errors_bp = 1e4 * np.array([fit.max_iv_error for fit in fits])
        div_bp = float(errors_bp.max() - errors_bp.min())
        worst_basins = max(worst_basins, len(groups))
        worst_dtheta = max(worst_dtheta, spread)
        worst_div_bp = max(worst_div_bp, div_bp)
        lines.append(f"{node.ticker} {node.expiry}: {len(groups)} basin(s),"
                     f" main spread {spread:.1e}, dIV {div_bp:.2f} bp")

    STORE.add("multistart", "MultiStartCount", str(N_STARTS),
              "randomized starts per node in the basin audit")
    STORE.add("multistart", "MultiStartNodes", "2",
              "nodes audited (SPY Dec and the long NVDA node)")
    STORE.add("multistart", "MultiStartBasins", str(worst_basins),
              "distinct optima found (worst node); 1 = single basin")
    STORE.add("multistart", "MultiStartWorstDTheta", sci(worst_dtheta),
              "worst max |dtheta| within the main cluster")
    STORE.add("multistart", "MultiStartWorstDIvBp", num(worst_div_bp, 2),
              "worst spread of max-IV-error across starts, vol bp")
    return "multistart " + "; ".join(lines)
