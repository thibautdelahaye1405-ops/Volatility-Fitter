"""Frozen-chain access and synthetic boards for the Chapter 6 figures.

Two kinds of input, per the book's data policy:

* REAL: the raw dollar option chains embedded in the frozen snapshot
  (``data/lqd_paper_snapshot_20260804_0208.json``) -- the same single file
  behind every real-market figure since Chapter 2.  Chapter 6 is the first
  chapter to read the chains at the quote level (call/put mids by strike);
  node metadata (year fraction, resolved forward and discount, spot) and
  the stored LQD fit come through Chapter 3's loader (data3.py / fits.py,
  imported directly, exactly as Chapter 5 did).

* SYNTHETIC: deterministic European boards priced by the Black formula at a
  known forward and discount, used wherever a figure must compare an
  estimator against the truth.  Construction constants are those stated in
  appendix 6.A.  The only randomness anywhere is the seeded generator of
  the identifiability experiment (fig_fwd_ident).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import norm

_SCRIPTS = Path(__file__).resolve().parents[2]
for _sib in ("ch03",):
    _p = str(_SCRIPTS / _sib / "figlib")
    if _p not in sys.path:
        sys.path.append(_p)  # append: ch06's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)

SNAPSHOT = data3.SNAPSHOT

# The book's canonical deep-dive node (Chapters 2-5's worked example).
RUNNING = data3.SPY_DEC


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def running_node() -> data3.Node:
    return data3.node(*RUNNING)


@lru_cache(maxsize=None)
def chain_pairs(ticker: str, expiry: str) -> tuple[np.ndarray, np.ndarray]:
    """(K, Pi): paired strikes and call-minus-put mid differences, one expiry.

    Mids are (bid+ask)/2 from the embedded raw chain; a strike enters only if
    both legs quote a positive bid (the same both-sides-live rule the
    reference implementation applies before its parity fit).
    """
    tk = next(t for t in _raw()["tickers"] if t["ticker"] == ticker)
    ch = tk["chain"]
    idx = {c: j for j, c in enumerate(ch["quoteColumns"])}
    by_strike: dict[float, dict[str, float]] = {}
    for q in ch["quotes"]:
        if q[idx["expiry"]] != expiry:
            continue
        bid, ask = q[idx["bid"]], q[idx["ask"]]
        if bid is None or ask is None or bid <= 0.0:
            continue
        by_strike.setdefault(q[idx["strike"]], {})[q[idx["callPut"]]] = (
            0.5 * (bid + ask)
        )
    strikes = np.array(
        sorted(k for k, v in by_strike.items() if "C" in v and "P" in v)
    )
    pi = np.array([by_strike[k]["C"] - by_strike[k]["P"] for k in strikes])
    return strikes, pi


# --------------------------------------------------------------- Black board

def _d12(F: float, K: np.ndarray, w: float) -> tuple[np.ndarray, np.ndarray]:
    sw = np.sqrt(w)
    d1 = np.log(F / K) / sw + 0.5 * sw
    return d1, d1 - sw


def black_call(F: float, K: np.ndarray, w: float, D: float) -> np.ndarray:
    """Dollar Black call: D [F Phi(d+) - K Phi(d-)] at total variance w."""
    d1, d2 = _d12(F, K, w)
    return D * (F * norm.cdf(d1) - K * norm.cdf(d2))


@dataclass(frozen=True)
class Board:
    """One synthetic European board with known truth."""

    S: float
    F: float
    D: float
    t: float
    r: float
    qd: float
    sigma: float
    K: np.ndarray
    C: np.ndarray        # cent-rounded call mids
    P: np.ndarray        # cent-rounded put mids
    C_exact: np.ndarray  # unrounded model prices
    P_exact: np.ndarray

    @property
    def Pi(self) -> np.ndarray:
        return self.C - self.P

    @property
    def Pi_exact(self) -> np.ndarray:
        return self.C_exact - self.P_exact


def board(t: float = 0.5, r: float = 0.04, qd: float = 0.01,
          sigma: float = 0.22, S: float = 100.0,
          k_lo: float = 70.0, k_hi: float = 130.0, step: float = 2.5,
          tick: float = 0.01) -> Board:
    """The running synthetic board (appendix 6.A constants by default)."""
    K = np.arange(k_lo, k_hi + 0.5 * step, step)
    F = S * np.exp((r - qd) * t)
    D = np.exp(-r * t)
    w = sigma * sigma * t
    C = black_call(F, K, w, D)
    P = C - D * (F - K)  # parity: exact European puts
    round_ = (lambda x: np.round(x / tick) * tick) if tick else (lambda x: x)
    return Board(S, F, D, t, r, qd, sigma, K, round_(C), round_(P), C, P)


# ---------------------------------------------------------------- estimators

def ols(K: np.ndarray, Pi: np.ndarray) -> tuple[float, float, float, float]:
    """Least squares of Pi on K: returns (F_hat, D_hat, a_hat, b_hat)."""
    b, a = np.polyfit(K, Pi, 1)
    D = -b
    return a / D, D, a, b


def trim_fit(K: np.ndarray, Pi: np.ndarray, nsigma: float = 4.0,
             max_rounds: int = 3, floor: float = 0.01, min_keep: int = 3
             ) -> tuple[float, float, np.ndarray]:
    """The iterated residual trim: fit, robust scale, drop, refit.

    floor is the robust-scale floor in dollars (one basis point of a
    100-dollar spot by default).  Returns (F_hat, D_hat, keep_mask).
    """
    keep = np.ones(K.size, dtype=bool)
    for _ in range(max_rounds):
        F, D, a, b = ols(K[keep], Pi[keep])
        resid = Pi - (a + b * K)
        scale = max(1.4826 * np.median(np.abs(resid[keep])), floor)
        bad = keep & (np.abs(resid) > nsigma * scale)
        if not bad.any() or keep.sum() - bad.sum() < min_keep:
            break
        keep &= ~bad
    F, D, _, _ = ols(K[keep], Pi[keep])
    return F, D, keep
