"""Shared data access and var-swap helpers for the Chapter 5 figures.

Chapter 5 deliberately reuses the earlier chapters' protocols instead of
inventing its own:

  * the RUNNING NODE is the book's canonical SPY December 2026 strip, and the
    three families (LQD / SVI / MCS) are fitted to its mid quotes by Chapter
    3's exact protocol (scripts/ch03/figlib/fits.py, imported directly);
  * the GALLERY (per-node shares, term structure) reads the frozen snapshot's
    stored haircut fits — the published surface — via the same loader as
    Chapters 2-3 (data3.py);
  * the FIELD-side computations reuse Chapter 4's whole-surface local-vol
    protocol (scripts/ch04/figlib/lvfits.py, imported directly).

The sibling figlibs are put on sys.path here (ch05's own figlib stays first,
so ``figstyle``/``macros`` always resolve to Chapter 5's).  All var-swap
evaluations call the reference implementation (volfit.calib.varswap and the
models' own routes); nothing is reimplemented.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
for _sib in ("ch03", "ch04"):
    _p = str(_SCRIPTS / _sib / "figlib")
    if _p not in sys.path:
        sys.path.append(_p)  # append: ch05's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)
import fits  # noqa: E402   (Chapter 3's three-family fitting protocol)
from volfit.calib.varswap import varswap_total_variance  # noqa: E402

# The book's canonical deep-dive node (Chapters 2-4's worked example).
RUNNING = data3.SPY_DEC

# Diagnostics replication grid: same half-width as the reference in-loop grid,
# at the finer diagnostics point count (the "4001-point twin").
HALF_WIDTH = 6.0
POINTS = 4001


@lru_cache(maxsize=1)
def running_node() -> data3.Node:
    return data3.node(*RUNNING)


@lru_cache(maxsize=1)
def family_fits() -> dict[str, fits.FamilyFit]:
    """LQD / SVI / MCS fitted to the running node under the Ch. 3 protocol."""
    return fits.node_fits(*RUNNING)


def w_curve(fit: fits.FamilyFit, t: float):
    """The fit's total-implied-variance curve k -> w(k)."""
    return lambda k: np.asarray(fit.iv(np.asarray(k, dtype=float))) ** 2 * t


def fair_w_replication(implied_w, half: float = HALF_WIDTH,
                       points: int = POINTS) -> float:
    """Strike-side fair strike (total variance) by the reference replication."""
    return varswap_total_variance(implied_w, half_width=half, points=points)


def vs_vol_pct(w_vs: float, t: float) -> float:
    """sigma_vs in percent."""
    return 100.0 * float(np.sqrt(max(w_vs, 0.0) / t))


def strike_integrand(implied_w, half: float = HALF_WIDTH,
                     points: int = POINTS) -> tuple[np.ndarray, np.ndarray]:
    """(k, integrand) of the strike-side integral, same floats as the
    reference replication's integrand (volfit.calib.varswap)."""
    from volfit.core.black import black_call

    k = np.linspace(-half, half, points)
    w = np.maximum(np.asarray(implied_w(k), dtype=float), 1e-12)
    integ = black_call(k, w) * np.exp(-k)
    put = k < 0.0
    integ[put] += 1.0 - np.exp(-k[put])
    return k, 2.0 * integ


def accrual_share(implied_w, half: float = HALF_WIDTH,
                  points: int = POINTS) -> tuple[np.ndarray, np.ndarray]:
    """(k, S(k)): cumulative share of the strike-side integral up to k."""
    k, integ = strike_integrand(implied_w, half, points)
    cum = np.concatenate([[0.0], np.cumsum(
        0.5 * (integ[1:] + integ[:-1]) * np.diff(k))])
    return k, cum / cum[-1]


def span_share(implied_w, k_lo: float, k_hi: float) -> float:
    """Fraction of the strike-side integral accrued inside [k_lo, k_hi]."""
    k, s = accrual_share(implied_w)
    return float(np.interp(k_hi, k, s) - np.interp(k_lo, k, s))


@lru_cache(maxsize=None)
def stored_slice(ticker: str, expiry: str):
    """The snapshot's stored haircut fit for one node (the published surface)."""
    return fits.rebuild_stored_lqd(data3.node(ticker, expiry))


def gallery(ticker: str) -> list[data3.Node]:
    return data3.nodes(ticker)
