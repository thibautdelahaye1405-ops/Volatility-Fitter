"""Per-quote calibration-weight inspection of one smile node (V3.4 item 5).

Backs GET /smiles/{ticker}/{expiry}/weights: for every prepared quote, the
Voronoi spacing s_i, the pre-normalization economic weight and the final
mean-1 weight of the live FitSettings.weightScheme — decomposed by
``volfit.calib.weights.weight_components`` (the scheme is never re-implemented
here). Weights are computed on the POST-EDIT arrays (exactly the fit's inputs,
service._slice_task) and remapped back to the full prepared/QuoteBand index
space; excluded quotes are listed with weight 0.

POLL-SAFE by construction: prepared quotes + session edits only — reading
never touches ``fit_or_get`` or the calibrated pointers (the quality.py
doctrine), so it is as cheap as a status poll. Lives outside service.py for
the file-size policy (the table.py pattern).
"""

from __future__ import annotations

import numpy as np

from volfit.api.quotes import apply_edits
from volfit.api.schemas_weights import WeightEntry, WeightsData
from volfit.api.service import prepare_slice
from volfit.api.state import AppState
from volfit.calib.weights import DEFAULT_MAX_MULT, weight_components


def weights_payload(state: AppState, ticker: str, expiry_iso: str) -> WeightsData:
    """Assemble the weight inspection for one (ticker, expiry) node.

    The weight scheme is orthogonal to the fit mode (the mode picks each
    quote's target, the scheme how much it matters — volfit.calib.weights), so
    no fit_mode enters the computation. Raises UnknownNodeError (-> 404) for
    an unknown node; a fetched-but-unfittable node yields an empty payload.
    """
    expiry = state.resolve_expiry(ticker, expiry_iso)  # UnknownNodeError -> 404
    iso = expiry.isoformat()
    scheme = state.fit_settings().weightScheme
    prepared = prepare_slice(state, ticker, iso)
    if prepared is None:  # no chain / no forward yet: an empty, honest payload
        return WeightsData(
            ticker=ticker, expiry=expiry_iso, scheme=scheme,
            maxMult=DEFAULT_MAX_MULT, entries=[],
        )

    session = state.session_if_exists((ticker, iso))
    edits = {} if session is None else session.edits
    # The fit's own post-edit inputs (excluded masked, amended mids re-leveled).
    k, w, _ = apply_edits(prepared, edits, None)
    comps = weight_components(scheme, k, w)

    # Remap the post-edit rows back to the FULL prepared index space: the kept
    # rows are the prepared indices apply_edits retains, in order, so
    # comps.*[j] belongs to prepared index included[j] (== QuoteBand.index).
    keep = np.ones(prepared.k.size, dtype=bool)
    for index, edit in edits.items():
        if index < prepared.k.size and edit.excluded:
            keep[index] = False
    position = {int(full): j for j, full in enumerate(np.flatnonzero(keep))}

    entries: list[WeightEntry] = []
    for i in range(int(prepared.k.size)):
        j = position.get(i)
        entries.append(
            WeightEntry(
                index=i,
                k=float(prepared.k[i]),
                spacing=float(comps.spacing[j]) if j is not None else 0.0,
                weightRaw=float(comps.raw[j]) if j is not None else 0.0,
                weight=float(comps.weights[j]) if j is not None else 0.0,
                excluded=j is None,
            )
        )
    return WeightsData(
        ticker=ticker, expiry=expiry_iso, scheme=comps.scheme,
        maxMult=comps.max_mult, entries=entries,
    )
