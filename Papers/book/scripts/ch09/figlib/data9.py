"""Frozen-snapshot smiles and the chapter's transport rules.

Real inputs come from the same single frozen snapshot as every chapter
since Chapter 2 (``data/lqd_paper_snapshot_20260804_0208.json``), through
Chapter 3's node loader.  Chapter 9 consumes the snapshot's STORED haircut
LQD fits (never refitted): each frozen node yields a smooth smile
sigma(k), its ATM skew s0, and its total variance w(k).  The linear
transport and the frozen-field displacement map live here so every figure
uses one implementation, sign-for-sign.

Chapter conventions carried by every function: the move H is
log(F_new/F_old), positive up; a transported CURVE reads the old curve at
k + H; a fixed-strike QUOTE's label slides to k - H.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
_P = str(_SCRIPTS / "ch03" / "figlib")
if _P not in sys.path:
    sys.path.append(_P)  # append: ch09's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)
from fits import rebuild_stored_lqd  # noqa: E402

SNAPSHOT = data3.SNAPSHOT

# The book's canonical deep-dive node (the running example since Ch. 2).
HERO = data3.SPY_DEC

# The chapter's canonical scenario move and marked put strike.
H_FAN = -0.04     # the fan / dial move (log-forward units)
K_MARK = -0.10    # the marked OTM put strike (today's log-moneyness label)
REGIMES = (0.0, 1.0, 2.0)

_DK = 1e-3        # central-difference step for the ATM skew of a smooth fit


@dataclass(frozen=True)
class Smile:
    """One frozen node's stored fitted smile, ready for transport."""

    ticker: str
    expiry: str
    t: float
    forward: float
    iv: Callable[[np.ndarray], np.ndarray]   # sigma(k) of the stored fit
    w: Callable[[np.ndarray], np.ndarray]    # total variance w(k)
    s0: float                                # ATM skew d sigma/dk at k = 0
    k_lo: float                              # prepared-quote span (fit trust)
    k_hi: float

    @property
    def days(self) -> int:
        return round(self.t * 365.0)

    @property
    def atm_vol(self) -> float:
        return float(self.iv(np.array([0.0]))[0])


@lru_cache(maxsize=None)
def smile(ticker: str, expiry: str) -> Smile:
    """The stored haircut LQD fit of one frozen node, as a Smile."""
    node = data3.node(ticker, expiry)
    slice_ = rebuild_stored_lqd(node)
    t = node.t

    def iv(k, s=slice_, tt=t):
        return np.asarray(s.implied_vol(np.asarray(k, dtype=float), tt))

    def w(k, s=slice_):
        return np.asarray(s.implied_w(np.asarray(k, dtype=float)))

    s0 = float(
        (iv(np.array([_DK]))[0] - iv(np.array([-_DK]))[0]) / (2.0 * _DK)
    )
    return Smile(
        ticker=node.ticker, expiry=node.expiry, t=t, forward=node.forward,
        iv=iv, w=w, s0=s0,
        k_lo=float(node.k.min()), k_hi=float(node.k.max()),
    )


def hero() -> Smile:
    return smile(*HERO)


def gallery(ticker: str = "SPY") -> list[Smile]:
    """All eight frozen nodes of one ticker, sorted by maturity."""
    return [smile(n.ticker, n.expiry) for n in data3.nodes(ticker)]


# ------------------------------------------------------------- transports
def transport_vol(sm: Smile, big_h: float, regime: float):
    """The linear transport: sigma_new(k) = sigma_old(k + H) + (R-1) s0 H."""

    def iv_new(k):
        return sm.iv(np.asarray(k, dtype=float) + big_h) \
            + (regime - 1.0) * sm.s0 * big_h

    return iv_new


def ell(k: np.ndarray, big_h: float) -> np.ndarray:
    """The frozen-field displacement map ell(k, H) = log(e^H (1+e^k) - 1)."""
    arg = np.exp(big_h) * (1.0 + np.exp(np.asarray(k, dtype=float))) - 1.0
    if np.any(arg <= 0.0):
        raise ValueError("ell(k, H): displacement map out of domain")
    return np.log(arg)


def transport_hagan(sm: Smile, big_h: float):
    """The midpoint relabeling: w_new(k) = w_old(ell(k, H)), in vol form."""

    def iv_new(k):
        return np.sqrt(sm.w(ell(k, big_h)) / sm.t)

    return iv_new
