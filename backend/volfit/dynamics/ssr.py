"""Skew-stickiness ratio (SSR) scenario engine.

How does the smile move when spot moves? The standard summary is the SSR

    SSR = (d sigma_atm / d ln F) / skew,

i.e. how much of the skew is realized as ATM vol change per unit log-spot
move. Canonical regimes:

  - sticky moneyness/delta : SSR = 0 (smile rides with the forward)
  - sticky strike          : SSR = 1 (vol fixed at fixed strike)
  - sticky local vol       : SSR ~ 2 for short-dated skews (Bergomi); here
                             implemented as the SSR = 2 shape rule, which is
                             exact in the short-maturity limit and a standard
                             desk approximation otherwise.

Implementation: the shifted smile in the *new* forward moneyness k is

    sigma_new(k) = sigma_old(k + delta) + (SSR - 1) * skew * delta,
    delta = log(F_new / F_old),

i.e. sticky-strike re-indexing plus a level adjustment so that
d sigma_atm = SSR * skew * delta exactly, while the smile shape is preserved.
"""

from __future__ import annotations

from enum import Enum

import numpy as np


class Regime(str, Enum):
    """Named vol-spot dynamics regimes (UI-facing values)."""

    STICKY_MONEYNESS = "sticky_moneyness"
    STICKY_STRIKE = "sticky_strike"
    STICKY_LOCAL_VOL = "sticky_local_vol"
    #: Exact dynamics: hold the extracted local-vol *grid* fixed in absolute
    #: strike and reprice through the Dupire PDE (volfit.api.localvol). The
    #: SSR is an output there; the 2.0 below is only its short-maturity limit
    #: for callers that resolve regimes to a number.
    STICKY_LOCAL_VOL_GRID = "sticky_local_vol_grid"


_REGIME_SSR = {
    Regime.STICKY_MONEYNESS: 0.0,
    Regime.STICKY_STRIKE: 1.0,
    Regime.STICKY_LOCAL_VOL: 2.0,
    Regime.STICKY_LOCAL_VOL_GRID: 2.0,
}


def ssr_of_regime(regime: Regime | str | float) -> float:
    """Resolve a regime name (or a custom numeric SSR) to its SSR value."""
    if isinstance(regime, (int, float)) and not isinstance(regime, bool):
        return float(regime)
    return _REGIME_SSR[Regime(regime)]


def shifted_smile(
    k: np.ndarray,
    vol_curve,
    atm_skew: float,
    spot_return: float,
    regime: Regime | str | float = Regime.STICKY_STRIKE,
) -> np.ndarray:
    """Smile after a spot move, evaluated at new-forward moneyness ``k``.

    ``vol_curve`` is the pre-move implied vol function sigma(k) (any
    SmileModel's implied_vol partial, or a plain callable); ``atm_skew`` its
    ATM slope s_0; ``spot_return`` the proportional move (F_new/F_old - 1).
    """
    k = np.asarray(k, dtype=float)
    delta = float(np.log1p(spot_return))
    ssr = ssr_of_regime(regime)
    return np.asarray(vol_curve(k + delta), dtype=float) + (ssr - 1.0) * atm_skew * delta
