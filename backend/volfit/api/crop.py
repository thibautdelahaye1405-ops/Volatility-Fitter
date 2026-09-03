"""Display crop of the stacked-IV curves to each maturity's realistic range.

Opt-in (OptionsSettings.stackCrop / stackCropTailProb, 2026-09-03): a curve
is not drawn where the slice's own risk-neutral distribution puts less than
a tail probability ε of mass beyond — [Q(ε), Q(1 − ε)] per expiry — because
a pricer that samples S_T (or the path) from the fitted surface never reads
the smile out there with probability 1 − O(ε): whatever arbitrage lives in
the far extrapolated wings (a calendar crossing, a flat tail extension, a
wing law beyond the last quote) moves prices by O(ε × payoff). Inside the
crop, arbitrage-freeness is the computational statement; outside, nothing is
computed. Traded strikes are realistic by definition, so the range is
widened to the quoted range and the quotes stay drawn regardless.

The payload carries the range at FIXED tail levels (``TAIL_U_LEVELS``, both
tails), and the frontend interpolates the Options ε in log10(u) — so the
level can change without a refit (the LV payload is cached by its affine key)
and the same table serves every ε. The quantiles come from the model's own
CDF: the parametric slice's numeric density on a grid that always covers the
display window (heavy fitted tails beyond ±8 ATM sd clamp at the window
edge = no crop), the LV lattice CDF of the converged-operator reprice.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import CropRanges

#: Tail-probability levels the crop table is sampled at, 1e-2 … 1e-12 (both
#: tails). OptionsSettings.stackCropTailProb is bounded to this span.
TAIL_U_LEVELS: list[float] = [10.0 ** -e for e in range(2, 13)]


def crop_ranges_from_cdf(
    k: np.ndarray, cdf: np.ndarray, k_quote_lo: float, k_quote_hi: float
) -> CropRanges:
    """The crop table of one slice from its CDF samples ``(k, cdf)`` (k
    ascending, cdf non-decreasing in [0, 1]): per level u, ``lo`` = the first
    node whose CDF reaches u (Q(u)), ``hi`` = the first node whose CDF reaches
    1 − u (Q(1 − u)), each widened to the quoted range. Monotone in u by
    construction (wider for smaller u); a tail the samples do not resolve
    clamps at the sample range's end."""
    k = np.asarray(k, dtype=float)
    c = np.clip(np.asarray(cdf, dtype=float), 0.0, 1.0)
    n = k.size
    lo: list[float] = []
    hi: list[float] = []
    for u in TAIL_U_LEVELS:
        i = min(int(np.searchsorted(c, u, side="left")), n - 1)
        j = min(int(np.searchsorted(c, 1.0 - u, side="left")), n - 1)
        lo.append(float(min(k[i], k_quote_lo)))
        hi.append(float(max(k[j], k_quote_hi)))
    return CropRanges(u=list(TAIL_U_LEVELS), lo=lo, hi=hi)


def crop_ranges_for_slice(slice_, k_quote_lo: float, k_quote_hi: float) -> CropRanges:
    """The crop table of a parametric slice (any SmileModel) from its numeric
    Breeden-Litzenberger density, on a grid reaching the display window on
    both sides so a clamp means "no crop", never a too-narrow one."""
    from volfit.api.service import K_DISPLAY_HI, K_DISPLAY_LO  # heavy module: lazy
    from volfit.models.diagnostics import numeric_density

    half = max(abs(float(K_DISPLAY_LO)), abs(float(K_DISPLAY_HI)))
    k, _, cdf = numeric_density(slice_, half_floor=half)
    return crop_ranges_from_cdf(k, cdf, k_quote_lo, k_quote_hi)
