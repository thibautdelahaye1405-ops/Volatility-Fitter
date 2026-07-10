"""Idiosyncratic-move floor for non-observed nodes' credible bands.

Closes the one dishonest cell of the 2026-07-09 benchmark pack
(`backtest/FINDINGS_graph_loo.md`): in the calm regime (low_jul2023) dark
single-name moves are earnings/idiosyncratic, the propagated systematic signal
is negligible, and the posterior band — which derives from the increment prior
plus the (near-infinite-precision) transported baseline — understated the
realized residuals by ~1.9x (zeta std 1.91/1.85). Stress regimes were honest
(spike 1.10/1.02) so a blanket widening would break them.

The fix is a **band floor from the node's own trailing unexplained move**:

    sd_atm'^2 = max(sd_atm^2, IDIO_FLOOR_LAMBDA * sigma_I^2)

where ``sigma_I`` is the shrunk EWMA-RMS of the ticker's past day-over-day ATM
innovations (calibrated - transported prior), pooled across expiries, computed
STRICTLY from days before the solve date. A node's band may not be tighter
than ~sqrt(0.30) ~ 0.55x what the name itself has recently moved beyond its
prior. Key properties (validated offline on all 47,393 stored benchmark rows,
2026-07-10 — the widening is band-only, so stored residuals stay exact):

  * regime-adaptive with NO regime input: in calm tape the band is far below
    the name's realized move (floor binds, low_jul2023 zeta std 1.91->1.02,
    1.85->1.03); in stress the band is already wide (spike 1.10->0.99,
    1.02->0.94; high_oct2022 binds on ~1% of rows, 0.78->0.77);
  * self-gating across asset kinds: index/ETF trailing innovations are small,
    so their (already conservative) bands are essentially untouched — no
    asset taxonomy is needed;
  * mean-invariant by construction: only ``HandleField.sd`` moves, never the
    posterior mean (a dark node's baseline precision enters only its band —
    see ``posterior.py``: the ``1/p0`` term is absent from the mean's
    observed columns);
  * strictly causal and cold-start-silent: no history -> no floor -> the
    legacy field byte-identical.

Production feeds the estimator from innovations recorded whenever a node is
lit and calibrated (``AppState.record_graph_innovations``); a name that goes
dark today is floored from the days it was lit — exactly the product story
("keep dark names marked, with stated uncertainty"). The benchmark harness
(`backtest/graph_loo.py`) accumulates the same quantity across its day pairs.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping

import numpy as np

from volfit.graph.smile_universe import HandleField

#: Floor strength: band VARIANCE floored at this fraction of sigma_I^2.
#: 0.30 chosen on the stored-row sweep (0.25 leaves low at 1.05; 0.50 drags
#: spike to 0.89-0.91) — see the module docstring numbers.
IDIO_FLOOR_LAMBDA = 0.30

#: EWMA half-life (trading days of history) for the trailing RMS. The offline
#: sweep was insensitive across {3, 5, flat}; 5 keeps the estimator responsive
#: without whipsawing on a single print.
IDIO_EWMA_HALFLIFE = 5.0

#: Shrinkage pseudo-count toward the cross-sectional pool (James-Stein-style):
#: a ticker with n own observations gets weight n/(n+K) on its own RMS.
IDIO_SHRINK_K = 4.0

#: Retention horizon for recorded innovations (calendar days of distinct
#: as-of dates kept per ticker).
IDIO_HISTORY_MAX_DAYS = 60


def trailing_idio_sigma(
    own: Iterable[tuple[str, float]],
    pool_mean_sq: float | None = None,
    halflife: float = IDIO_EWMA_HALFLIFE,
    shrink_k: float = IDIO_SHRINK_K,
) -> float | None:
    """Shrunk EWMA-RMS of one ticker's past innovations; None on cold start.

    ``own`` is the ticker's past ``(as_of_iso, innovation)`` records — the
    CALLER enforces causality (only days strictly before the solve date).
    Multiple entries may share a day (one per expiry); recency weights are by
    distinct-day rank so a chain with many expiries is not over-weighted.
    ``pool_mean_sq`` is the cross-sectional mean squared innovation of the
    caller's pool (same-kind in the benchmark, global in production).
    """
    entries = [(a, float(v)) for a, v in own]
    if not entries:
        return None
    days = sorted({a for a, _ in entries})
    rank = {a: i for i, a in enumerate(days)}
    n_days = len(days)
    wsum = vsum = 0.0
    for a, v in entries:
        w = 0.5 ** ((n_days - 1 - rank[a]) / halflife) if halflife > 0 else 1.0
        wsum += w
        vsum += w * v * v
    own_var = vsum / wsum
    if pool_mean_sq is not None and shrink_k > 0:
        n = float(len(entries))
        own_var = (n * own_var + shrink_k * float(pool_mean_sq)) / (n + shrink_k)
    return math.sqrt(own_var)


def apply_idio_floor(
    field: HandleField,
    sigmas: np.ndarray,
    floor_lambda: float = IDIO_FLOOR_LAMBDA,
) -> tuple[HandleField, np.ndarray]:
    """Floor the ATM-band std per node; returns (new field, bound mask).

    ``sigmas`` is (N,) with NaN where no floor applies (observed node or cold
    start). Only ``sd[:, 0]`` can move, and only upward — the posterior means
    and the skew/curvature bands are untouched (skew/curv widening is an open
    follow-up alongside the full handle-covariance work).
    """
    sigmas = np.asarray(sigmas, dtype=float)
    floor_var = floor_lambda * np.square(np.where(np.isnan(sigmas), 0.0, sigmas))
    bound = floor_var > np.square(field.sd[:, 0])
    if not bound.any():
        return field, bound
    sd = field.sd.copy()
    sd[bound, 0] = np.sqrt(floor_var[bound])
    return HandleField(mean=field.mean, sd=sd, posteriors=field.posteriors), bound


class IdioHistory:
    """Bounded per-ticker record of ATM innovations, keyed (ticker, day, node).

    The (day, node) keying makes recording idempotent: re-solving the same
    day overwrites rather than double-counts. ``sigma_map`` pools globally
    across recorded tickers (production has no asset taxonomy; the estimator
    self-gates, see module docstring).
    """

    def __init__(self, data: dict[str, dict[str, dict[str, float]]] | None = None):
        self._data: dict[str, dict[str, dict[str, float]]] = data or {}

    def record(self, ticker: str, day_iso: str, node_key: str, value: float) -> bool:
        """Record one innovation; True when it is new or changed (so callers can
        skip persisting a byte-identical blob on repeated same-day solves)."""
        nodes = self._data.setdefault(ticker, {}).setdefault(day_iso, {})
        value = float(value)
        if nodes.get(node_key) == value:
            return False
        nodes[node_key] = value
        days = self._data[ticker]
        if len(days) > IDIO_HISTORY_MAX_DAYS:  # prune the oldest as-of dates
            for stale in sorted(days)[: len(days) - IDIO_HISTORY_MAX_DAYS]:
                del days[stale]
        return True

    def entries_before(self, ticker: str, day_iso: str) -> list[tuple[str, float]]:
        """The ticker's (day, innovation) records strictly before ``day_iso``."""
        return [
            (d, v)
            for d, nodes in self._data.get(ticker, {}).items()
            if d < day_iso
            for v in nodes.values()
        ]

    def sigma_map(self, before_iso: str) -> dict[str, float]:
        """Per-ticker trailing sigma from records strictly before ``before_iso``."""
        past_sq = [
            v * v
            for days in self._data.values()
            for d, nodes in days.items()
            if d < before_iso
            for v in nodes.values()
        ]
        pool = float(np.mean(past_sq)) if past_sq else None
        out: dict[str, float] = {}
        for ticker in self._data:
            s = trailing_idio_sigma(self.entries_before(ticker, before_iso), pool)
            if s is not None:
                out[ticker] = s
        return out

    def to_blob(self) -> dict:
        return {"tickers": self._data}

    @classmethod
    def from_blob(cls, blob: dict | None) -> "IdioHistory":
        if not blob or not isinstance(blob.get("tickers"), dict):
            return cls()
        try:
            data = {
                str(tk): {
                    str(d): {str(n): float(v) for n, v in nodes.items()}
                    for d, nodes in days.items()
                }
                for tk, days in blob["tickers"].items()
            }
        except (TypeError, ValueError, AttributeError):
            return cls()  # malformed persisted blob -> empty history
        return cls(data)
