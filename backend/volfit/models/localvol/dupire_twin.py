"""The smooth Dupire twin as a PRICING surface, and the flat control beside it.

``extract_twin`` (dupire_surface) samples the twin on the affine VERTICES —
the object the Compare tab draws beside the fitted sheet. Marching that
coarse sample through the PDE, however, measures the lattice's sampling of a
smooth surface, not the twin: on the synthetic ladder the nodal sheet
repriced its own parametric source to 5 bp at one year where the smooth
surface reads 0.7 (2026-09-08). So the twin's SMILE and scores come from
``DupireTwinSurface`` — the same Gatheral local variance, evaluated where the
march asks (every interior node, every time level), memoized per time level
so the call, put and wing marches of one build share the work. Duck-typed
for ``reprice_affine_dupire``: only ``variance(x, t)`` is needed.

The other finding of that day: the residual is then the OPERATOR's. On a
one-month front marched with nine implicit-Euler steps even a FLAT surface
misprices by 154 bp, and the fit's "converged" refinement (dt/4, dx/2) still
carries 51 bp there; the second-order Rannacher scheme at dt/8, dx/4 reads
2.3 bp for 0.16 s a march. ``FlatSurface`` is that control: repriced on the
same operator, its own error is the floor below which no round trip can be
read — the Compare tab reports it beside the twin's figure.
"""

from __future__ import annotations

import numpy as np

from volfit.models.localvol.dupire import _fill_nearest, dupire_local_variance
from volfit.models.localvol.dupire_surface import (
    DK_DEFAULT,
    T_INTERPS,
    WSurface,
    _default_dt,
    _w_t,
)

#: The twin's DISPLAY operator: the calibration lattice refined by these
#: factors, marched with the second-order Rannacher scheme — chosen where the
#: flat control's front-expiry error fell under ~2.5 bp at ~0.16 s a march
#: (implicit Euler needed dt/64, dx/8 and 2 s for the same).
TWIN_DT_FACTOR = 8
TWIN_DX_FACTOR = 4
TWIN_SCHEME = "rannacher"


class DupireTwinSurface:
    """σ²_loc(x, t) of a total-variance surface, evaluated on demand.

    Same stencil policy as ``extract_twin`` (central FD in k; per-interpolant
    stencil in t), the same display-range guard (vertices outside
    ``[k_lo, k_hi]`` hold flat from the nearest inside one), the same box
    clip; every repair is COUNTED (totals over the build) and the nearest-
    valid fill keeps the march positive. ``t`` below one stencil step reads
    the short-end limit at ``t = dt``.
    """

    def __init__(
        self,
        w_surface: WSurface,
        ts: np.ndarray,
        *,
        t_interp: str = "smooth",
        var_lo: float,
        var_hi: float,
        k_lo: float | None = None,
        k_hi: float | None = None,
        dk: float = DK_DEFAULT,
        dt: float | None = None,
    ) -> None:
        if t_interp not in T_INTERPS:
            raise ValueError(f"t_interp must be one of {T_INTERPS}, got {t_interp!r}")
        if not (0.0 < var_lo < var_hi):
            raise ValueError("need 0 < var_lo < var_hi")
        self.w = w_surface
        self.ts = np.asarray(ts, dtype=float)
        self.edges = np.concatenate([[0.0], self.ts])
        self.t_interp = t_interp
        self.var_lo, self.var_hi = float(var_lo), float(var_hi)
        self.k_lo, self.k_hi = k_lo, k_hi
        self.dk = float(dk)
        self.dt = float(dt) if dt is not None else _default_dt(self.ts)
        self.n_butterfly = self.n_calendar = self.n_floored = self.n_capped = 0
        self._memo: dict[tuple[bytes, float], np.ndarray] = {}

    def variance(self, x: np.ndarray, t: float) -> np.ndarray:
        """Local VARIANCE at strikes ``x`` (K/F) and time ``t`` (the march's clock)."""
        x = np.asarray(x, dtype=float)
        key = (x.tobytes(), float(t))
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        out = self._evaluate(x, float(t))
        self._memo[key] = out
        return out

    def _evaluate(self, x: np.ndarray, t: float) -> np.ndarray:
        t_eval = max(t, self.dt)
        with np.errstate(divide="ignore"):
            k_all = np.where(x > 0.0, np.log(np.where(x > 0.0, x, 1.0)), -np.inf)
        inside = x > 0.0
        if self.k_lo is not None:
            inside &= k_all >= float(self.k_lo)
        if self.k_hi is not None:
            inside &= k_all <= float(self.k_hi)
        if not inside.any():
            raise ValueError("no strike inside the differentiation guard")
        k = k_all[inside]
        w0 = np.asarray(self.w(k, t_eval), dtype=float)
        wp = np.asarray(self.w(k + self.dk, t_eval), dtype=float)
        wm = np.asarray(self.w(k - self.dk, t_eval), dtype=float)
        wk = (wp - wm) / (2.0 * self.dk)
        wkk = (wp - 2.0 * w0 + wm) / (self.dk * self.dk)
        wt = np.asarray(_w_t(self.w, k, t_eval, self.dt, self.t_interp, self.edges), dtype=float)
        var = dupire_local_variance(k, w0, wk, wkk, wt)
        bad = ~np.isfinite(var)
        self.n_butterfly += int(bad.sum())
        if bad.any():
            var = _fill_nearest(var, k)
        self.n_calendar += int(np.sum(var <= 0.0))
        self.n_floored += int(np.sum(var < self.var_lo))
        self.n_capped += int(np.sum(var > self.var_hi))
        row = np.clip(var, self.var_lo, self.var_hi)
        return np.interp(k_all, k, row)  # flat beyond the guard (np.interp clamps)

    @property
    def clean(self) -> bool:
        return (self.n_butterfly + self.n_calendar + self.n_floored + self.n_capped) == 0


class FlatSurface:
    """A constant local variance — the operator's own control (exact reprice
    known: the flat implied vol), so its repricing error IS the operator's."""

    def __init__(self, variance: float) -> None:
        if not variance > 0.0:
            raise ValueError("flat variance must be positive")
        self.var = float(variance)

    def variance(self, x: np.ndarray, t: float) -> np.ndarray:  # noqa: ARG002 - the protocol
        return np.full(np.asarray(x, dtype=float).shape, self.var)
