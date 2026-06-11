"""Local-volatility model: cached Dupire-PDE pricing, slices, diagnostics.

``LocalVolModel`` owns a strictly positive LocalVolGrid and prices by solving
the Dupire forward PDE once per requested expiry set (cached on the expiry
tuple; mesh parameters are fixed per instance).  ``LocalVolSlice`` adapts a
single expiry row to the SmileModel protocol via linear price interpolation
in k plus Black inversion.

The diagnostics are the roadmap's gate (risk #4): the model is built from
positive local vol, so the continuum prices are arbitrage-free by
construction -- any butterfly (negative density) or calendar (convex-order)
violation in the discrete solution is *numerics*, and we surface it rather
than hide it.  Tolerances DENSITY_TOL / CALENDAR_TOL bound acceptable scheme
noise; anything beyond means the mesh or time step needs attention.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import implied_total_variance
from volfit.models.localvol.grid import LocalVolGrid
from volfit.models.localvol.pde import (
    DEFAULT_DT_MAX,
    DEFAULT_N_K,
    PDESolution,
    solve_dupire,
)

DENSITY_TOL = 1e-8  # butterfly: min density may dip this far below zero
CALENDAR_TOL = 1e-8  # calendar: C_i - C_{i+1} may exceed zero by this much


@dataclass(frozen=True)
class LocalVolSlice:
    """One expiry of the PDE solution, exposed through the SmileModel protocol.

    Prices are interpolated linearly in k between mesh nodes (piecewise-linear
    interpolation of convex nodal values stays convex, so no butterfly is
    introduced).  Each implied_w call runs one Brent inversion per strike
    (volfit.core.black.implied_total_variance), so the cost is per call --
    batch strikes into arrays rather than looping.
    """

    t: float
    k_mesh: np.ndarray
    prices: np.ndarray

    def call_price(self, k: np.ndarray | float) -> np.ndarray:
        """Normalized call price by linear interpolation of the PDE row."""
        return np.interp(np.asarray(k, dtype=float), self.k_mesh, self.prices)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Total implied variance w(k) by Black inversion of the call curve."""
        return implied_total_variance(k, self.call_price(k))

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        """Implied Black volatility at expiry ``t`` (the slice's own maturity)."""
        return np.sqrt(self.implied_w(k) / t)


@dataclass(frozen=True)
class LocalVolDiagnostics:
    """Numerical no-arbitrage residuals of the discrete PDE solution."""

    expiries: np.ndarray  # sorted unique, shape (n_exp,)
    min_density: np.ndarray  # per expiry, min over the mesh (butterfly)
    calendar_violation: np.ndarray  # per pair i: max over mesh of C_i - C_{i+1}
    sigma_min: float  # grid node extremes, for context
    sigma_max: float
    arbitrage_free: bool  # residuals within DENSITY_TOL / CALENDAR_TOL


class LocalVolModel:
    """Dupire-PDE pricing wrapper around a LocalVolGrid, with solution cache."""

    def __init__(
        self,
        grid: LocalVolGrid,
        *,
        k_lo: float | None = None,  # None: adaptive span (pde.SPAN_SD sd)
        k_hi: float | None = None,
        n_k: int = DEFAULT_N_K,
        dt_max: float = DEFAULT_DT_MAX,
    ) -> None:
        self.grid = grid
        self.k_lo = k_lo
        self.k_hi = k_hi
        self.n_k = n_k
        self.dt_max = dt_max
        self._cache: dict[tuple[float, ...], PDESolution] = {}

    def solve(self, expiries) -> PDESolution:
        """PDE solution for an expiry set; cached on the sorted unique tuple."""
        key = tuple(sorted({float(t) for t in expiries}))
        sol = self._cache.get(key)
        if sol is None:
            sol = solve_dupire(
                self.grid,
                key,
                k_lo=self.k_lo,
                k_hi=self.k_hi,
                n_k=self.n_k,
                dt_max=self.dt_max,
            )
            self._cache[key] = sol
        return sol

    def slice_at(self, t: float) -> LocalVolSlice:
        """SmileModel-compatible slice at expiry t (reuses any cached solve)."""
        t = float(t)
        for sol in self._cache.values():
            (idx,) = np.nonzero(sol.expiries == t)
            if idx.size:
                return LocalVolSlice(t=t, k_mesh=sol.k_mesh, prices=sol.prices[idx[0]])
        sol = self.solve((t,))
        return LocalVolSlice(t=t, k_mesh=sol.k_mesh, prices=sol.prices[0])

    def diagnostics(self, expiries) -> LocalVolDiagnostics:
        """Butterfly / calendar residuals of the discrete solution.

        Calendar: normalized undiscounted calls are increasing in maturity
        (convex order), so max(C_i - C_{i+1}) over the mesh should be <= 0 up
        to scheme noise.  Butterfly: density(i) should be >= 0 everywhere.
        """
        sol = self.solve(expiries)
        n_exp = sol.expiries.size
        min_density = np.array([float(sol.density(i).min()) for i in range(n_exp)])
        if n_exp > 1:
            calendar = np.max(sol.prices[:-1] - sol.prices[1:], axis=1)
        else:
            calendar = np.empty(0)
        ok = bool(
            min_density.min() >= -DENSITY_TOL
            and (calendar.size == 0 or calendar.max() <= CALENDAR_TOL)
        )
        return LocalVolDiagnostics(
            expiries=sol.expiries,
            min_density=min_density,
            calendar_violation=calendar,
            sigma_min=float(self.grid.sigma.min()),
            sigma_max=float(self.grid.sigma.max()),
            arbitrage_free=ok,
        )
