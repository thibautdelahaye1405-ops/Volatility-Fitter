"""The fit's aggregate quote weight per moneyness band — the Quality lens's
"Wgt" column (quote-weighting arc rider, 2026-09-10).

The weighting scheme (``FitSettings.weightScheme``) shapes what the least
squares sums along the smile; the Weights strip draws it per quote, and this
module reports the same weights POOLED into five bands so a whole universe
reads at a glance beside the RMS: which slices are wing-heavy, which are
ATM-only. Bands are in STANDARDIZED moneyness z = k / (σ_atm √τ) so a
two-day and a one-year slice compare — the ATM band is one σ√τ wide, the
deep bands start two σ√τ out:

    deep put   z <  −2
    put        −2 ≤ z < −0.5
    ATM        −0.5 ≤ z ≤ 0.5
    call       0.5 < z ≤ 2
    deep call  z >  2

Shares are the band's summed weight over the total (they sum to 1); the
weights are exactly the fit's — ``volfit.calib.weights.resolve_weights`` on
the prepared (edited) quotes, unit weights under ``equal``.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.weights import resolve_weights

#: Band edges in standardized moneyness (open on the deep sides).
BUCKET_EDGES: tuple[float, ...] = (-2.0, -0.5, 0.5, 2.0)
#: Wire order of the five shares.
BUCKET_LABELS: tuple[str, ...] = ("deepPut", "put", "atm", "call", "deepCall")


def weight_bucket_shares(
    k: np.ndarray, w_mid: np.ndarray, atm_vol: float, tau: float, scheme: str,
) -> list[float] | None:
    """Five weight shares by standardized-moneyness band, or None when the
    slice cannot be standardized (no quotes, no ATM vol, zero maturity)."""
    k = np.asarray(k, dtype=float)
    if k.size == 0 or not (atm_vol > 0.0) or not (tau > 0.0):
        return None
    weights = resolve_weights(scheme, k, np.asarray(w_mid, dtype=float))
    w = np.ones(k.size) if weights is None else np.asarray(weights, dtype=float)
    total = float(w.sum())
    if not (total > 0.0):
        return None
    z = k / (float(atm_vol) * np.sqrt(float(tau)))
    # searchsorted with side="right" puts z == −0.5 in the ATM band and z == 0.5
    # in the ATM band too (the closed ATM interval of the module docstring).
    band = np.searchsorted(np.asarray(BUCKET_EDGES), z, side="right")
    band = np.where((band == 3) & (z == 0.5), 2, band)  # z == 0.5 stays ATM
    sums = np.bincount(band, weights=w, minlength=len(BUCKET_LABELS))
    return [round(float(s) / total, 4) for s in sums[: len(BUCKET_LABELS)]]
