"""Series FILES — ``volfit-series/1`` export / import (SERIES ARC S6, D12).

Bundle::

    { "schema": "volfit-series/1", "savedAt", "app": {version},
      "series": <SeriesDoc as JSON: id, spec (lanes inside), baseFit,
                 baseOptions, progress, frames (the index)>,
      "chains": [ { "idx", "spot", "timestamp",
                    "chain": <export_inputs.ExportChain> } ],   # one per stored frame
      "fits":   [ <LaneFitDoc as JSON> ],                        # every stored fit
      "carries": { laneId: <the lane's carry doc> } }             # prior + filter docs

* ``export_series`` reads the store only (frames' chains through the same
  ``export_chain`` the snapshot file uses, fits and carries verbatim).
* ``import_series_file`` validates the envelope and RECREATES the series
  under its own id: the chains are saved as series-OWNED snapshot rows
  (``chain_from_doc``, the exact inverse), the frame index re-pointed at
  them, the fits and carries written back — so export → delete → import is
  byte-identical on everything the store keeps. An id already present is
  left untouched (idempotent: the existing document is returned).
"""

from __future__ import annotations

from datetime import datetime, timezone

from volfit import __version__
from volfit.api.export_inputs import export_chain
from volfit.api.schemas_series import LaneFitDoc, SeriesDoc
from volfit.api.series_store import SeriesStore
from volfit.data.file import chain_from_doc
from volfit.data.store import VolStore

SERIES_SCHEMA = "volfit-series/1"


class SeriesFormatError(ValueError):
    """A bundle this server cannot read."""


class UnknownSeriesError(KeyError):
    pass


# ------------------------------------------------------------------ export

def export_series(state, series_id: str) -> dict:
    if state.store_path is None:
        raise RuntimeError("series need a store: set VOLFIT_DB")
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(series_id)
        if doc is None:
            raise UnknownSeriesError(series_id)
        chains = []
        for frame in doc.frames:
            if frame.snapshotId is None:
                continue
            chain = store.load_snapshot(frame.snapshotId)
            chains.append({
                "idx": frame.idx, "spot": float(chain.spot),
                "timestamp": chain.timestamp.isoformat(),
                "chain": export_chain(chain).model_dump(),
            })
        fits = [f.model_dump(mode="json") for f in series.fits(series_id)]
        carries = {lane.id: series.lane_filter(series_id, lane.id) for lane in doc.spec.lanes}
    return {
        "schema": SERIES_SCHEMA,
        "savedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "app": {"version": __version__},
        "series": doc.model_dump(mode="json"),
        "chains": chains,
        "fits": fits,
        "carries": {k: v for k, v in carries.items() if v is not None},
    }


# ------------------------------------------------------------------ import

def _check(bundle: dict) -> None:
    if not isinstance(bundle, dict):
        raise SeriesFormatError("not a JSON object")
    tag = bundle.get("schema")
    if not isinstance(tag, str) or "/" not in tag:
        raise SeriesFormatError(f'missing "schema" tag (expected {SERIES_SCHEMA})')
    family, major = tag.split("/", 1)
    if family != "volfit-series":
        raise SeriesFormatError(f"not a series file (schema {tag})")
    if major != "1":
        raise SeriesFormatError(f"unsupported series schema {tag} (this server reads {SERIES_SCHEMA})")
    if not isinstance(bundle.get("series"), dict):
        raise SeriesFormatError("the bundle carries no series document")


def import_series_file(state, bundle: dict) -> SeriesDoc:
    """Recreate the bundle's series in the app store (see the module doc)."""
    if state.store_path is None:
        raise RuntimeError("series need a store: set VOLFIT_DB")
    _check(bundle)
    try:
        doc = SeriesDoc.model_validate(bundle["series"])
        fits = [LaneFitDoc.model_validate(f) for f in bundle.get("fits") or []]
    except Exception as exc:  # noqa: BLE001 — a malformed document is a format error
        raise SeriesFormatError(f"malformed series document: {exc}") from None
    ticker = doc.spec.ticker
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        existing = series.get(doc.id)
        if existing is not None:
            return existing
        by_idx: dict[int, int] = {}
        for entry in bundle.get("chains") or []:
            try:
                chain = chain_from_doc(ticker, float(entry["spot"]), str(entry["timestamp"]),
                                       entry["chain"])
            except Exception as exc:  # noqa: BLE001
                raise SeriesFormatError(f"malformed chain at frame {entry.get('idx')}: {exc}") from None
            by_idx[int(entry["idx"])] = store.save_snapshot(chain, source=doc.spec.source,
                                                            series_id=doc.id)
        frames = [f.model_copy(update={"snapshotId": by_idx.get(f.idx)}) for f in doc.frames]
        series.create(doc.model_copy(update={"frames": frames}))
        for fit in fits:
            series.save_fit(doc.id, fit)
        for lane_id, carry in (bundle.get("carries") or {}).items():
            if carry is not None and any(lane.id == lane_id for lane in doc.spec.lanes):
                series.set_lane_filter(doc.id, lane_id, carry)
        stored = series.get(doc.id)
    assert stored is not None
    return stored
