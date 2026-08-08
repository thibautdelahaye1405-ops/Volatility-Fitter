"""Frozen-snapshot access + the thinned-morning ensemble for Chapter 10.

The chapter's real-data exhibit is the book's canonical SPY December 2026
node, THINNED to its at-the-money band (|k| <= 0.10) to stage a sparse
morning.  The ensemble refits that band with the reference implementation
under several deliberately different rules -- Chapter 3's exact protocol
(scripts/ch03/figlib/fits.py) for the three families, plus LQD at varied
resolution and ridge strength -- and the spread of the ensemble in the
unquoted wing is the chapter's measurement of the likelihood's flat
directions.  The frozen snapshot is read via Chapter 3's loader; nothing is
refetched.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
_P3 = str(_SCRIPTS / "ch03" / "figlib")
if _P3 not in sys.path:
    sys.path.append(_P3)  # append: ch10's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)
import fits  # noqa: E402   (Chapter 3's three-family fitting protocol)
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402

RUNNING = data3.SPY_DEC
BAND = 0.10  # the staged morning: quotes kept iff |k| <= BAND


@lru_cache(maxsize=1)
def running_node() -> data3.Node:
    return data3.node(*RUNNING)


@lru_cache(maxsize=1)
def thinned() -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """(k, iv_mid, w_mid, t) of the band-thinned running node."""
    n = running_node()
    keep = np.abs(n.k) <= BAND
    return n.k[keep], n.iv_mid[keep], n.w_mid[keep], n.t


@dataclass(frozen=True)
class EnsembleFit:
    """One member of the thinned-band ensemble."""

    label: str
    iv: Callable[[np.ndarray], np.ndarray]


def _lqd_member(k, w_mid, t, order: int, ridge: float) -> EnsembleFit:
    n_eff = fits.lqd_effective_order(k.size, order)
    res = calibrate_slice(
        np.asarray(k, float), np.asarray(w_mid, float), t, n_order=n_eff,
        reg_lambda=ridge, reg_power=fits.LQD_RIDGE_POWER, coords="logistic",
    )
    slice_ = res.slice

    def iv_fn(kk, s=slice_, tt=t):
        return np.asarray(s.implied_vol(np.asarray(kk, float), tt))

    return EnsembleFit(f"LQD n={n_eff} ridge={ridge:g}", iv_fn)


@lru_cache(maxsize=1)
def ensemble() -> list[EnsembleFit]:
    """Eight fits of the same thinned band under different rules.

    One family at three resolutions and two ridge strengths (six members)
    plus the two other parametric families of Chapter 3 -- every member is
    calibrated by the reference implementation to the SAME mid quotes.
    """
    k, iv_mid, w_mid, t = thinned()
    members: list[EnsembleFit] = []
    for order in (8, 12, 16):
        for ridge in (1e-6, 1e-4):
            members.append(_lqd_member(k, w_mid, t, order, ridge))
    svi = fits.fit_svi(k, w_mid, t, iv_mid)
    members.append(EnsembleFit("SVI", svi.iv))
    mcs = fits.fit_mcs(k, w_mid, t, iv_mid)
    members.append(EnsembleFit("MCS", mcs.iv))
    return members
