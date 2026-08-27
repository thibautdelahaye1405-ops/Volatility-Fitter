"""Observation-filter state <-> workspace doc (split out of ``workspace.py``).

Two per-node observation-filter objects ride the workspace doc (Note 15,
V3.9 item 7 + the persistence rider), both keyed (ticker, iso, fit_mode):

* ``filterStates`` — the NodeFilter holders (``volfit.api.observation_filter``):
  one dict per holder, numpy -> lists; the ``curves`` overlay memo is dropped
  (rebuilt lazily by the diagnostics endpoint). ``_filter_doc`` /
  ``_filter_from`` are the exact pair; ``filter_states_docs`` /
  ``filter_states_from`` wrap them over the whole map (sorted keys, so the doc
  is deterministic).
* ``filterHistory`` — the history rings, delegated to
  ``volfit.api.filter_history`` (``history_docs`` / ``history_from_docs`` are
  re-exported here so ``workspace.py`` reads every filter glue from ONE
  sibling). Non-empty rings only; an absent key restores to empty rings.

Pure serialization: no locking, no state mutation — ``workspace.build_doc``
and ``restore_doc`` own both (the rings are installed AFTER the restore's
chain-cache clear, see there). Behaviour is byte-identical to the pre-split
in-file helpers.
"""

from __future__ import annotations

import numpy as np

from volfit.api.filter_history import history_docs, history_from_docs

__all__ = [
    "filter_states_docs",
    "filter_states_from",
    "history_docs",
    "history_from_docs",
]


# ------------------------------------------------------------ whole-map glue
def filter_states_docs(filter_states: dict) -> list[dict]:
    """The ``filterStates`` list: one ``_filter_doc`` per holder, sorted by
    (ticker, iso, mode) for a deterministic doc."""
    return [_filter_doc(k, h) for k, h in sorted(filter_states.items())]


def filter_states_from(items: list) -> dict:
    """Inverse of :func:`filter_states_docs`: ``{(ticker, iso, mode): NodeFilter}``."""
    out: dict[tuple, object] = {}
    for item in items or []:
        key = (item["ticker"], item["expiry"], item["mode"])
        out[key] = _filter_from(key, item)
    return out


# ------------------------------------------- observation-filter node states
def _filter_doc(key: tuple, holder) -> dict:
    """One NodeFilter holder as JSON (numpy -> lists; the ``curves`` overlay
    memo is dropped — it is rebuilt lazily by the diagnostics endpoint)."""
    ticker, iso, mode = key
    s = holder.state
    p, m, u = holder.prediction, holder.measurement, holder.update
    return {
        "ticker": ticker,
        "expiry": iso,
        "mode": mode,
        "dataVersion": int(holder.data_version),
        "sessionVersion": int(holder.session_version),
        "forward": float(holder.forward),
        "state": {
            "handleNames": list(s.handle_names),
            "mean": np.asarray(s.mean, dtype=float).tolist(),
            "cov": np.asarray(s.cov, dtype=float).tolist(),
            "timestamp": float(s.timestamp),
            "provenance": s.provenance,
            "resetReason": s.reset_reason,
        },
        "prediction": None if p is None else {
            "mean": np.asarray(p.mean, dtype=float).tolist(),
            "cov": np.asarray(p.cov, dtype=float).tolist(),
            "transportDistance": float(p.transport_distance),
            "qBreakdown": {
                k: np.asarray(v, dtype=float).tolist()
                for k, v in p.q_breakdown.items()
            },
        },
        "measurement": None if m is None else {
            "handles": np.asarray(m.handles, dtype=float).tolist(),
            "cov": np.asarray(m.cov, dtype=float).tolist(),
            "breakdown": {k: float(v) for k, v in m.breakdown.items()},
            "contaminated": bool(m.contaminated),
        },
        "update": None if u is None else {
            "innovation": np.asarray(u.innovation, dtype=float).tolist(),
            "innovationCov": np.asarray(u.innovation_cov, dtype=float).tolist(),
            "gain": np.asarray(u.gain, dtype=float).tolist(),
            "mean": np.asarray(u.mean, dtype=float).tolist(),
            "cov": np.asarray(u.cov, dtype=float).tolist(),
        },
    }


def _filter_from(key: tuple, doc: dict):
    from volfit.api.observation_filter import NodeFilter  # runtime (no cycle)
    from volfit.calib.observation_filter import (
        FilterMeasurement,
        FilterPrediction,
        FilterState,
        FilterUpdate,
    )

    s = doc["state"]
    state = FilterState(
        node_key=key,
        handle_names=tuple(s["handleNames"]),
        mean=np.asarray(s["mean"], dtype=float),
        cov=np.asarray(s["cov"], dtype=float),
        timestamp=float(s["timestamp"]),
        provenance=str(s["provenance"]),
        reset_reason=s.get("resetReason"),
    )
    p = doc.get("prediction")
    prediction = None if p is None else FilterPrediction(
        mean=np.asarray(p["mean"], dtype=float),
        cov=np.asarray(p["cov"], dtype=float),
        transport_distance=float(p["transportDistance"]),
        q_breakdown={
            k: np.asarray(v, dtype=float) for k, v in p.get("qBreakdown", {}).items()
        },
    )
    m = doc.get("measurement")
    measurement = None if m is None else FilterMeasurement(
        handles=np.asarray(m["handles"], dtype=float),
        cov=np.asarray(m["cov"], dtype=float),
        breakdown={k: float(v) for k, v in m.get("breakdown", {}).items()},
        contaminated=bool(m.get("contaminated", False)),
    )
    u = doc.get("update")
    update = None if u is None else FilterUpdate(
        innovation=np.asarray(u["innovation"], dtype=float),
        innovation_cov=np.asarray(u["innovationCov"], dtype=float),
        gain=np.asarray(u["gain"], dtype=float),
        mean=np.asarray(u["mean"], dtype=float),
        cov=np.asarray(u["cov"], dtype=float),
    )
    return NodeFilter(
        state=state,
        prediction=prediction,
        measurement=measurement,
        update=update,
        data_version=int(doc.get("dataVersion", 0)),
        session_version=int(doc.get("sessionVersion", 0)),
        forward=float(doc.get("forward", 0.0)),
    )
