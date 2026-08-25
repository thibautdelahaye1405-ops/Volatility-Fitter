"""Response models for GET /smiles/{ticker}/{expiry}/weights (V3.4 item 5).

Per-quote calibration-weight inspection: the live scheme, the Voronoi strike
spacing and the pre-normalization economic weight behind every final mean-1
weight the least squares actually uses (volfit.calib.weights). Entries are
aligned to ``QuoteBand.index`` (the full prepared array — excluded quotes are
listed with weight 0 so the UI can outline them). Built from prepared quotes
plus session edits only; reading NEVER triggers a fit (the schemas_quality
doctrine). Mirrors the schemas.py / schemas_quality.py module split
(file-size policy).
"""

from __future__ import annotations

from pydantic import BaseModel


class WeightEntry(BaseModel):
    """One prepared quote's weight decomposition (index == QuoteBand.index)."""

    index: int
    k: float  # log-moneyness of the quote
    #: Voronoi cell width s_i in k, over the INCLUDED (post-edit) quotes —
    #: the "quote crowding" is its inverse. 0 for excluded quotes and when
    #: fewer than 2 quotes remain (no cell exists).
    spacing: float
    #: Pre-normalization economic weight of the scheme's shape: max(TV_i, eps)
    #: for "tv_density", the Black-vega profile phi(d+) for "vega_density", the
    #: OTM |forward delta| for "delta_density", 1.0 for "equal"; 0 for excluded
    #: quotes.
    weightRaw: float
    #: Final mean-1 weight the fit uses (ones materialized for "equal");
    #: 0 for excluded quotes (they are not fitted).
    weight: float
    excluded: bool


class WeightsData(BaseModel):
    """Per-quote weights of one (ticker, expiry) node under the live scheme."""

    ticker: str
    expiry: str  # ISO date, as requested
    scheme: str  # FitSettings.weightScheme (equal | tv_density | vega_density | delta_density)
    maxMult: float  # cap on the spacing multiplier s_i / s_bar (density schemes)
    meanNormalized: bool = True  # included weights are normalized to mean 1
    entries: list[WeightEntry] = []
