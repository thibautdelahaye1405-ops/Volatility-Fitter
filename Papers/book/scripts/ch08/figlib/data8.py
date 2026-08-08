"""Frozen-snapshot ATM ladders for the Chapter 8 figures.

Real inputs come from the same single frozen snapshot as every chapter
since Chapter 2 (``data/lqd_paper_snapshot_20260804_0208.json``), through
Chapter 3's node loader.  Chapter 8 needs one number per (ticker, expiry)
node: the at-the-money total implied variance, read from the prepared mid
quotes by linear interpolation of w in log-moneyness at k = 0 (the plain
rule stated in appendix 8.A).  Nothing is refetched and no smile is
refitted -- the clock story runs entirely on the ATM ladder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
_P = str(_SCRIPTS / "ch03" / "figlib")
if _P not in sys.path:
    sys.path.append(_P)  # append: ch08's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)

SNAPSHOT = data3.SNAPSHOT

# The Chapter 8 hero horizon: candidates through the December 2026 expiry.
HORIZON_EXPIRY = "2026-12-18"


def atm_w(node) -> float:
    """ATM total variance: linear interpolation of w_mid in k at k = 0."""
    order = np.argsort(node.k)
    return float(np.interp(0.0, node.k[order], node.w_mid[order]))


def ladder(ticker: str):
    """(t, w, expiries) -- the ticker's quoted ATM ladder, sorted by t."""
    ns = data3.nodes(ticker)
    t = np.array([n.t for n in ns])
    w = np.array([atm_w(n) for n in ns])
    return t, w, [n.expiry for n in ns]


def atm_vol(ticker: str):
    """(days, sigma_cal) -- calendar ATM vol readings for the ladder."""
    t, w, _ = ladder(ticker)
    return t * 365.0, np.sqrt(w / t)
