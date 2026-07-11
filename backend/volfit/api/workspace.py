"""Serializable per-desk WORKSPACE — the user-authored state behind AppState.

State-scoping refactor (roadmap R1 item 9). AppState historically held every
piece of mutable state as one flat attribute soup: user-authored inputs
(settings, quote edits, priors, policies) mixed with process-local caches
(chain snapshots, fit records, version counters). Hosted single-tenant
instances (R4), durable filter state (R2/R4) and full replay fidelity all
need the user-authored subset to be ONE scoped, serializable object — that
object is ``Workspace``.

Design:

* ``Workspace`` is a plain attribute container: no locks, no behaviour.
  AppState keeps its single lock and delegates every scoped attribute through
  a ``ScopedField`` data descriptor, so each existing call site
  (``state._sessions`` and friends) reads/writes the workspace transparently
  and runtime behaviour is byte-identical to the pre-refactor layout.
* ``build_doc`` / ``restore_doc`` serialize a state's workspace to a plain
  JSON-safe dict and back. Floats survive exactly (JSON round-trips float64
  via shortest-repr), so a restored workspace produces byte-identical fits.
* Restoring is a state RESET: every chain-derived and per-ticker derived
  cache is dropped and every version counter is advanced past its current
  value, so no warm cache can ever serve a fit keyed against the
  pre-restore workspace. Universe tickers + custom expiry picks restore
  LAZILY (``AppState.restore_universe``) — no network at restore time.

IN the workspace: fit + options settings, per-ticker market settings and
event calendars, per-node forward policies, quote-edit and var-swap sessions
(with undo/redo), saved per-node priors, active fetched priors (+ ladder
source), observation-filter node states, lit/dark picks, graph edge
overrides + block rule, spot shifts, the viewed fit mode and the as-of
selection. NOT in it: provider handles, chain snapshots, fit/prepared
caches, calibrated pointers, the graph universe and all version counters —
process-local derived state that rebuilds from workspace + market data.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import (
    EventSpec,
    FitSettings,
    ForwardPolicy,
    GraphBlockRule,
    GraphEdgeInput,
    MarketSettings,
    OptionsSettings,
    SmilePoint,
)
from volfit.api.schemas_prior import PriorSurfaceSnapshot
from volfit.api.session import EditSession
from volfit.api.varswap_session import VarSwapSession
from volfit.models.lqd.basis import LQDParams

#: Bump when the doc layout changes incompatibly (restore stays lenient:
#: missing keys fall back to defaults, so older docs keep loading).
WORKSPACE_DOC_VERSION = 1


class ScopedField:
    """Data descriptor delegating an AppState attribute to its workspace.

    ``_sessions = ScopedField("sessions")`` in the AppState class body makes
    ``state._sessions`` read/write ``state._ws.sessions`` — every historical
    call site (including ``setattr`` restores and the mixins) keeps working
    while the whole scoped state can be serialized or swapped as one object.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj._ws, self.name)

    def __set__(self, obj, value) -> None:
        setattr(obj._ws, self.name, value)


class Workspace:
    """The user-authored state of one desk/workspace (see module docstring).

    Attribute types mirror the historical AppState fields one-to-one; the
    version counters live here too (they scope the workspace's cache keys)
    but are process-local and never serialized.
    """

    def __init__(self) -> None:
        self.fit_settings = FitSettings()
        self.settings_version = 0
        self.options = OptionsSettings()
        self.options_version = 0
        self.filter_version = 0
        #: (ticker, iso, fit_mode) -> volfit.api.observation_filter.NodeFilter
        self.filter_states: dict[tuple, object] = {}
        self.graph_edges: list[GraphEdgeInput] = []
        self.graph_block_rule: GraphBlockRule | None = None
        self.market_settings: dict[str, MarketSettings] = {}
        self.events: dict[str, list[EventSpec]] = {}
        self.events_version: dict[str, int] = {}
        self.forward_policies: dict[tuple[str, str], ForwardPolicy] = {}
        self.forwards_version: dict[str, int] = {}
        self.spot_shift: dict[str, float] = {}
        self.spot_version = 0
        self.spot_version_by_ticker: dict[str, int] = {}
        self.sessions: dict[tuple[str, str], EditSession] = {}
        self.varswap_sessions: dict[tuple[str, str], VarSwapSession] = {}
        #: (ticker, iso) -> volfit.api.state.PriorRecord (saved display priors)
        self.priors: dict[tuple[str, str], object] = {}
        self.active_prior: dict[str, PriorSurfaceSnapshot] = {}
        self.active_prior_source: dict[str, str] = {}
        self.active_prior_version: dict[str, int] = {}
        self.dark_nodes: set[tuple[str, str]] = set()
        self.last_fit_mode = "mid"
        #: volfit.api.state.AsOfSelection; assigned by AppState.__init__ /
        #: restore_doc (kept untyped here to avoid a module import cycle).
        self.asof = None


# ---------------------------------------------------------------- build_doc
def build_doc(state) -> dict:
    """Serialize the state's workspace to a JSON-safe dict.

    Version counters are deliberately NOT serialized — they are process-local
    cache keys; ``restore_doc`` advances them instead. Nested maps are sorted
    so the doc is deterministic (it may be embedded in hashed manifests).
    """
    with state._lock:
        ws = state._ws
        sessions = {k: s for k, s in ws.sessions.items() if s.version or s.edits}
        varswaps = {
            k: s
            for k, s in ws.varswap_sessions.items()
            if s.version or s.state.level is not None or s.state.excluded
        }
        priors = dict(ws.priors)
        active_prior = dict(ws.active_prior)
        active_src = dict(ws.active_prior_source)
        filter_states = dict(ws.filter_states)
        fit_settings, options = ws.fit_settings, ws.options
        market = dict(ws.market_settings)
        events = {t: list(v) for t, v in ws.events.items() if v}
        policies = dict(ws.forward_policies)
        edges = list(ws.graph_edges)
        rule = ws.graph_block_rule
        dark = sorted(ws.dark_nodes)
        shifts = dict(ws.spot_shift)
        last_mode = ws.last_fit_mode
        asof = ws.asof
        tickers = list(state._active_tickers)
        # Custom expiry picks: resolved ("custom" mode) plus still-pending
        # picks of a restored universe that never resolved its ladder yet.
        sels: dict[str, list[str]] = {}
        for t, mode in state._selection_mode.items():
            if mode == "custom" and state._selected.get(t):
                sels[t] = [d.isoformat() for d in state._selected[t]]
        for t, picks in state._pending_selections.items():
            sels.setdefault(t, [d.isoformat() for d in picks])
    return {
        "v": WORKSPACE_DOC_VERSION,
        "referenceDate": state.reference_date.isoformat(),
        "asOf": _asof_doc(asof),
        "universe": {"tickers": tickers, "selections": dict(sorted(sels.items()))},
        "fitSettings": fit_settings.model_dump(mode="json"),
        "options": options.model_dump(mode="json"),
        "marketSettings": {
            t: m.model_dump(mode="json") for t, m in sorted(market.items())
        },
        "forwardPolicies": _nested_docs(
            policies, lambda p: p.model_dump(mode="json")
        ),
        "events": {
            t: [e.model_dump(mode="json") for e in evs]
            for t, evs in sorted(events.items())
        },
        "sessions": _nested_docs(sessions, lambda s: s.to_doc()),
        "varSwapSessions": _nested_docs(varswaps, lambda s: s.to_doc()),
        "priors": _nested_docs(priors, _prior_record_doc),
        "activePriors": {
            t: snap.model_dump(mode="json") for t, snap in sorted(active_prior.items())
        },
        "activePriorSources": dict(sorted(active_src.items())),
        "darkNodes": [list(k) for k in dark],
        "graphEdges": [e.model_dump(mode="json") for e in edges],
        "graphBlockRule": rule.model_dump(mode="json") if rule is not None else None,
        "spotShifts": {t: float(v) for t, v in sorted(shifts.items())},
        "lastFitMode": last_mode,
        "filterStates": [
            _filter_doc(k, h) for k, h in sorted(filter_states.items())
        ],
    }


# -------------------------------------------------------------- restore_doc
def restore_doc(state, doc: dict) -> None:
    """Install a serialized workspace into ``state`` (a state RESET — see the
    module docstring for cache/version semantics). Lenient on missing keys so
    older/partial docs restore to defaults instead of failing."""
    from volfit.api.state import AsOfSelection  # runtime import (no cycle)

    ws = Workspace()
    ws.fit_settings = FitSettings.model_validate(doc.get("fitSettings", {}))
    ws.options = OptionsSettings.model_validate(doc.get("options", {}))
    ws.market_settings = {
        t: MarketSettings.model_validate(m)
        for t, m in doc.get("marketSettings", {}).items()
    }
    ws.forward_policies = {
        (t, iso): ForwardPolicy.model_validate(p)
        for t, per in doc.get("forwardPolicies", {}).items()
        for iso, p in per.items()
    }
    ws.events = {
        t: [EventSpec.model_validate(e) for e in evs]
        for t, evs in doc.get("events", {}).items()
    }
    ws.sessions = _load_nested(doc.get("sessions", {}), _session_from)
    ws.varswap_sessions = _load_nested(doc.get("varSwapSessions", {}), _varswap_from)
    ws.priors = _load_nested(doc.get("priors", {}), _prior_record_from)
    ws.active_prior = {
        t: PriorSurfaceSnapshot.model_validate(b)
        for t, b in doc.get("activePriors", {}).items()
    }
    ws.active_prior_source = dict(doc.get("activePriorSources", {}))
    ws.dark_nodes = {(t, iso) for t, iso in doc.get("darkNodes", [])}
    ws.graph_edges = [
        GraphEdgeInput.model_validate(e) for e in doc.get("graphEdges", [])
    ]
    rule = doc.get("graphBlockRule")
    ws.graph_block_rule = GraphBlockRule.model_validate(rule) if rule else None
    ws.spot_shift = {t: float(v) for t, v in doc.get("spotShifts", {}).items()}
    ws.last_fit_mode = str(doc.get("lastFitMode", "mid"))
    ws.asof = _asof_from(doc.get("asOf") or {}, AsOfSelection)
    for item in doc.get("filterStates", []):
        key = (item["ticker"], item["expiry"], item["mode"])
        ws.filter_states[key] = _filter_from(key, item)

    with state._lock:
        old = state._ws
        # Advance EVERY counter past its current value: caches that survive
        # the clears below (per-ticker derived grids, client refresh signals)
        # must never key-collide with the pre-restore workspace.
        ws.settings_version = old.settings_version + 1
        ws.options_version = old.options_version + 1
        ws.filter_version = old.filter_version + 1
        ws.spot_version = old.spot_version + 1
        ws.spot_version_by_ticker = _bumped(old.spot_version_by_ticker, ws.spot_shift)
        ws.events_version = _bumped(old.events_version, ws.events)
        ws.forwards_version = _bumped(
            old.forwards_version,
            set(ws.market_settings) | {t for t, _ in ws.forward_policies},
        )
        ws.active_prior_version = _bumped(
            old.active_prior_version,
            set(ws.active_prior) | set(ws.active_prior_source),
        )
        state._clear_chain_caches()
        for attr in ("_localvol_cache", "_affine_cache"):
            cache = getattr(state, attr, None)
            if cache is not None:
                cache.clear()
        # Expiry ladders re-resolve on the restored universe: a stale resolved
        # selection would make _ensure_selection ignore the restored picks.
        state._available.clear()
        state._selected.clear()
        state._selection_mode.clear()
        state._ws = ws

    uni = doc.get("universe") or {}
    if uni.get("tickers"):
        state.restore_universe(uni["tickers"], uni.get("selections") or {})
    state.log_event(
        "workspace_restore",
        payload={
            "tickers": len(uni.get("tickers", [])),
            "sessions": len(ws.sessions),
            "activePriors": len(ws.active_prior),
            "filterStates": len(ws.filter_states),
        },
    )


def _bumped(old: dict, new_keys) -> dict:
    """Every old counter +1, new keys starting at 1 (strictly past current)."""
    return {k: old.get(k, 0) + 1 for k in set(old) | set(new_keys)}


# ------------------------------------------------------------------ helpers
def _nested_docs(d: dict, fn) -> dict:
    """{(ticker, iso): v} -> {ticker: {iso: fn(v)}}, sorted for determinism."""
    out: dict[str, dict] = {}
    for (ticker, iso), value in sorted(d.items()):
        out.setdefault(ticker, {})[iso] = fn(value)
    return out


def _load_nested(doc: dict, fn) -> dict:
    return {
        (ticker, iso): fn(v)
        for ticker, per in doc.items()
        for iso, v in per.items()
    }


def _session_from(doc: dict) -> EditSession:
    s = EditSession()
    s.load_doc(doc)
    return s


def _varswap_from(doc: dict) -> VarSwapSession:
    s = VarSwapSession()
    s.load_doc(doc)
    return s


def _asof_doc(sel) -> dict:
    return {
        "mode": sel.mode,
        "on": sel.on.isoformat() if sel.on is not None else None,
        "ts": sel.ts.isoformat() if sel.ts is not None else None,
        "day": sel.day.isoformat() if sel.day is not None else None,
        "moment": sel.moment,
        "offset": sel.offset,
    }


def _asof_from(doc: dict, cls):
    from datetime import date, datetime

    return cls(
        mode=str(doc.get("mode", "live")),
        on=date.fromisoformat(doc["on"]) if doc.get("on") else None,
        ts=datetime.fromisoformat(doc["ts"]) if doc.get("ts") else None,
        day=date.fromisoformat(doc["day"]) if doc.get("day") else None,
        moment=doc.get("moment"),
        offset=doc.get("offset"),
    )


def _prior_record_doc(rec) -> dict:
    return {
        "curve": [p.model_dump(mode="json") for p in rec.curve],
        "params": {
            "L": float(rec.params.L),
            "R": float(rec.params.R),
            "a": np.asarray(rec.params.a, dtype=float).tolist(),
        },
        "t": float(rec.t),
    }


def _prior_record_from(doc: dict):
    from volfit.api.state import PriorRecord  # runtime import (no cycle)

    p = doc.get("params", {})
    return PriorRecord(
        curve=[SmilePoint.model_validate(q) for q in doc.get("curve", [])],
        params=LQDParams(
            L=float(p.get("L", 0.0)),
            R=float(p.get("R", 0.0)),
            a=np.asarray(p.get("a", []), dtype=float),
        ),
        t=float(doc.get("t", 0.0)),
    )


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
