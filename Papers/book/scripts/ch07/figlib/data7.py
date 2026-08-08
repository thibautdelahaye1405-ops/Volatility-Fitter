"""Frozen-chain access and carry conventions for the Chapter 7 figures.

Real inputs come from the same single frozen snapshot as every chapter since
Chapter 2 (``data/lqd_paper_snapshot_20260804_0208.json``); node metadata
and the parity-pair construction are reused from the Chapter 3 and Chapter 6
figure libraries (imported directly, exactly as Chapters 5-6 reused their
predecessors).  Chapter 7 additionally reads the raw chain's call AND put
mids per strike, because de-Americanization works quote by quote.

Carry convention for every real-chain tree (appendix 7.A): the level of
the carry comes from the node's resolved forward -- the well-identified
number of Chapter 6 -- while the rate is the stated money-market constant
R_CONV, because the board's own fitted slope is the poorly identified
number (the frozen node's naive slope implies a negative rate).  Given a
forward F, q_d = r - log(F/S)/t.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
for _sib in ("ch03", "ch06"):
    _p = str(_SCRIPTS / _sib / "figlib")
    if _p not in sys.path:
        sys.path.append(_p)  # append: ch07's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)
import data6  # noqa: E402  (Chapter 6's parity pairs and OLS)

SNAPSHOT = data3.SNAPSHOT
RUNNING = data3.SPY_DEC

# The stated money-market rate convention for the snapshot date (per year,
# continuously compounded).  A constant of the construction, stated in
# appendix 7.A -- NOT a fitted number; see the chapter's Section 7.6.
R_CONV = 0.043


def running_node() -> data3.Node:
    return data3.node(*RUNNING)


def carry_yield(F: float, S: float, t: float, r: float = R_CONV) -> float:
    """q_d implied by (F, S, r): F = S exp((r - q_d) t)."""
    return r - np.log(F / S) / t


@lru_cache(maxsize=None)
def chain_mids(ticker: str, expiry: str
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(K, C_mid, P_mid) where BOTH legs quote a live (positive) bid.

    The same both-sides-live rule as Chapter 6's parity pairs, but keeping
    the two mids separately instead of their difference.
    """
    raw = data6._raw()
    tk = next(t for t in raw["tickers"] if t["ticker"] == ticker)
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
    c = np.array([by_strike[k]["C"] for k in strikes])
    p = np.array([by_strike[k]["P"] for k in strikes])
    return strikes, c, p


@lru_cache(maxsize=None)
def otm_population(ticker: str, expiry: str
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(K, mid, is_call): the fitted-side population of one expiry.

    The plain rule stated in appendix 7.A: keep the out-of-the-money side
    of the book (puts below the resolved forward, calls at or above), each
    with a live bid, inside the wing cut |log(K/F)| <= 4 sigma_atm sqrt(t),
    with sigma_atm read from the node's prepared mid quote nearest the
    money.
    """
    node = data3.node(ticker, expiry)
    K, c_mid, p_mid = chain_mids(ticker, expiry)
    is_call = K >= node.forward
    mid = np.where(is_call, c_mid, p_mid)
    sigma_atm = float(node.iv_mid[np.argmin(np.abs(node.k))])
    keep = np.abs(np.log(K / node.forward)) <= 4.0 * sigma_atm * np.sqrt(node.t)
    return K[keep], mid[keep], is_call[keep]


def itm_puts(ticker: str, expiry: str) -> tuple[np.ndarray, np.ndarray]:
    """(K, P_mid) for the in-the-money puts (K above the resolved forward)."""
    node = data3.node(ticker, expiry)
    K, _, p_mid = chain_mids(ticker, expiry)
    keep = K > node.forward
    return K[keep], p_mid[keep]
