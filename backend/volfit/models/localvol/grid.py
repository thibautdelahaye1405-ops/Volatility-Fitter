"""Local-volatility grid: positive node vols on a log-moneyness x maturity lattice.

The model state is sigma_loc sampled on a rectangular grid (t_i, k_j).  Strict
positivity of every node is enforced at construction and *is* the arbitrage
gate: with sigma_loc > 0 the Dupire forward PDE (volfit.models.localvol.pde)
evolves call prices that are butterfly- and calendar-arbitrage-free by
construction, so a valid grid can never encode a bad surface -- only the
numerical scheme can drift, and that drift is measured by the diagnostics in
volfit.models.localvol.model rather than assumed away.

Two interpolants are supported between nodes, with flat extrapolation outside
the grid in both k and t:

- "bilinear"  continuous piecewise-affine in (k, t): affine in k on each cell
              and affine in t between maturity rows (the default);
- "pw_t"      piecewise-constant in t -- sigma(., t) takes the value of the
              interval's LEFT node, row i for t in [t_i, t_{i+1}) -- and
              affine in k.  This matches the market convention of constant
              forward-variance buckets between listed expiries.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_INTERP_MODES = ("bilinear", "pw_t")


@dataclass(frozen=True)
class LocalVolGrid:
    """Strictly positive local vols sigma[i, j] at maturities t[i], strikes k[j]."""

    k: np.ndarray  # log-moneyness nodes, strictly increasing, shape (n_k,)
    t: np.ndarray  # maturity nodes, strictly increasing, t[0] > 0, shape (n_t,)
    sigma: np.ndarray  # local VOLS (not variances), shape (n_t, n_k)
    interp: str = "bilinear"

    def __post_init__(self) -> None:
        k = np.atleast_1d(np.asarray(self.k, dtype=float))
        t = np.atleast_1d(np.asarray(self.t, dtype=float))
        sigma = np.asarray(self.sigma, dtype=float)
        object.__setattr__(self, "k", k)
        object.__setattr__(self, "t", t)
        object.__setattr__(self, "sigma", sigma)

        if self.interp not in _INTERP_MODES:
            raise ValueError(f"interp must be one of {_INTERP_MODES}, got {self.interp!r}")
        if k.ndim != 1 or k.size < 2:
            raise ValueError("k must be a 1-D array with at least 2 nodes")
        if np.any(np.diff(k) <= 0):
            raise ValueError("k nodes must be strictly increasing")
        if t.ndim != 1 or t.size < 1:
            raise ValueError("t must be a 1-D array with at least 1 node")
        if np.any(np.diff(t) <= 0):
            raise ValueError("t nodes must be strictly increasing")
        if t[0] <= 0.0:
            raise ValueError(f"t nodes must be positive, got t[0] = {t[0]}")
        if sigma.shape != (t.size, k.size):
            raise ValueError(f"sigma must have shape {(t.size, k.size)}, got {sigma.shape}")
        if not np.all(np.isfinite(sigma)):
            raise ValueError("sigma must be finite everywhere")
        if np.any(sigma <= 0.0):
            # The no-arbitrage gate: positive local vol => arbitrage-free PDE prices.
            raise ValueError("local vol must be strictly positive at every node")

    # ------------------------------------------------------------ properties
    @property
    def n_k(self) -> int:
        return int(self.k.size)

    @property
    def n_t(self) -> int:
        return int(self.t.size)

    # ----------------------------------------------------------- evaluation
    def _row_at(self, t: float) -> np.ndarray:
        """Local-vol row sigma(., t) on the k nodes for a scalar maturity."""
        tn = self.t
        if self.interp == "pw_t":
            # Right-continuous buckets: row i for t in [t_i, t_{i+1});
            # flat extrapolation clamps to the first / last row.
            i = int(np.searchsorted(tn, t, side="right")) - 1
            return self.sigma[min(max(i, 0), tn.size - 1)]
        # Bilinear: affine in t between rows, flat outside.
        if t <= tn[0]:
            return self.sigma[0]
        if t >= tn[-1]:
            return self.sigma[-1]
        j = int(np.searchsorted(tn, t, side="right"))
        wgt = (t - tn[j - 1]) / (tn[j] - tn[j - 1])
        return (1.0 - wgt) * self.sigma[j - 1] + wgt * self.sigma[j]

    def vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        """Local vol sigma_loc(k, t), vectorized in k for scalar t.

        Affine in k between nodes, flat extrapolation beyond the edge nodes
        (np.interp clamps at the endpoints by default).
        """
        return np.interp(np.asarray(k, dtype=float), self.k, self._row_at(float(t)))
