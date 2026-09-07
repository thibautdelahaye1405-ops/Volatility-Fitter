"""The ANCHORING AXIS of one smile node (2026-09-07).

Shadow fits of the DISPLAYED family that differ from the production fit in
the anchoring blocks ALONE:

    free     no persistence prior, no filter block — the pure market fit;
    prior    the persistence targets as resolved with the filter OFF (the full
             body prior, whatever the live filter mode);
    filter   the persistence targets as resolved with the filter ACTIVE (Note
             15 §6.3 auto-exclusion applied) + the Kalman prediction block
             FORCED from the kept state — under filter mode ``overlay`` this
             is a PREVIEW of the active MAP from the state the overlay keeps;
             under ``active`` it is production.

The axis is derived by SUBTRACTION from the live Options — never a settings
surface: the production fit is whatever Options says, and a cell exists only
when its input exists (an active prior node for ``prior``, a usable filter
state for ``filter``; ``free`` always). The cell that coincides with
production is tagged (``AnchoringPlan.production``) and, when the committed
record is fresh, REUSED rather than refit.

Every other cell is a pure function call through the production task
builder (service.single_node_task with ``anchoring=cell``): the same edited
quotes, band, weights, var-swap quote, calendar-on-refit neighbours and
prepass — every production input but the anchoring blocks — run INLINE and
NEVER committed: no calibrated-pointer move, no fit-cache entry, no
filter-state update (the commit hook is not run). Rows + records land in the
Compare side cache (compare.CompareCache) keyed (fit_key, "anchoring", cell),
so any input change invalidates for free and a re-toggle costs nothing.

The PULL columns (``attach_pull``) read each cell against the ``free`` cell:
ATM vol distance in vol bp, skew distance, and the RMS distance of the two
curves over the quoted range in vol bp — literally what the prior or the
filter bought on this node.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from volfit.api import service
from volfit.api.displayed import displayed_slice
from volfit.api.filter_mode import resolve_filter_mode
from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.schemas import AnchoringInfo
from volfit.api.schemas_compare import CompareModelFit
from volfit.api.state import AppState, FitRecord
from volfit.calib.fit_task import run_slice_fit
from volfit.calib.weights import resolve_weights

#: The cells, in wire / chip order.
ANCHORING_CELLS: tuple[str, ...] = ("free", "prior", "filter")
_PRODUCTION = "production"


def parse_anchoring(csv: str) -> tuple[str, ...]:
    """``"free,prior"`` -> ("free", "prior"), wire order, deduplicated; ""
    -> (). ValueError names an unknown cell (the router answers 422)."""
    wanted: list[str] = []
    for name in (c.strip().lower() for c in csv.split(",")):
        if name and name not in wanted:
            wanted.append(name)
    unknown = [c for c in wanted if c not in ANCHORING_CELLS]
    if unknown:
        raise ValueError(f"anchoring must be a CSV subset of {list(ANCHORING_CELLS)}; unknown: {unknown}")
    return tuple(c for c in ANCHORING_CELLS if c in wanted)


@dataclass(frozen=True)
class AnchoringPlan:
    """Which cells exist on a node, which one is production, and why not."""

    available: tuple[str, ...]
    production: str | None  # the cell the production fit coincides with
    family: str  # the displayed family id ("lqd" | "svi" | "sigmoid")
    filter_mode: str
    prior_mode: str
    notes: dict[str, str] = field(default_factory=dict)  # cell -> why unavailable

    def info(self, requested: tuple[str, ...] = ()) -> AnchoringInfo:
        return AnchoringInfo(
            requested=list(requested), available=list(self.available),
            production=self.production, family=self.family,
            filterMode=self.filter_mode, priorMode=self.prior_mode, notes=dict(self.notes),
        )


def resolve_anchoring(
    state: AppState, ticker: str, iso: str, fit_mode: str, prepared
) -> AnchoringPlan:
    """Availability by INPUT existence (never by fitting), production by the
    live mode: filter active with a prediction -> "filter"; otherwise "prior"
    when an active prior node exists under a calibration-prior mode, else
    "free". The lone edge — filter active but no prediction (first fit / a
    due reset) — is production = persistence-under-active, which is "free"
    only when that resolves to nothing; else no cell coincides (None)."""
    from volfit.api import observation_filter as ofilt
    from volfit.api import prior_transport

    opts = state.options()
    fplan = resolve_filter_mode(opts)
    notes: dict[str, str] = {}
    # + Prior: a calibration-prior mode AND an active prior node for this expiry.
    off_opts = opts.model_copy(update={"observationFilterMode": "off"})
    if not resolve_prior_mode(off_opts).any_calibration_prior:
        notes["prior"] = f"prior persistence mode '{opts.priorPersistenceMode}' adds no calibration prior"
        prior_ok = False
    elif prior_transport.prior_node(state.active_prior(ticker), iso) is None:
        notes["prior"] = "no active prior for this node — save or fetch a prior first"
        prior_ok = False
    else:
        prior_ok = True
    # + Filter: a kept state with a usable prediction (mode gate lifted).
    if not fplan.enabled:
        notes["filter"] = "observation filter is off — no per-node state is kept"
        filter_ok = False
    elif ofilt.active_prediction_target(state, ticker, iso, fit_mode, prepared, force=True) is None:
        notes["filter"] = "no usable filter state for this node yet — calibrate once with the filter on (a due reset also clears it)"
        filter_ok = False
    else:
        filter_ok = True
    available = ("free",) + (("prior",) if prior_ok else ()) + (("filter",) if filter_ok else ())

    if fplan.active:
        if filter_ok:
            production: str | None = "filter"
        else:
            k, w, _ = service.edited_fit_inputs(state, ticker, iso, prepared, None)
            weights = resolve_weights(state.fit_settings().weightScheme, k, w)
            pt = service.prior_targets(state, ticker, iso, k, weights, prepared, fit_mode)
            if pt.prior_anchor is None and pt.operator_prior is None and pt.prior_var_swap is None:
                production = "free"
            else:
                production = None
                notes[_PRODUCTION] = (
                    "the filter is active but has no prediction for this node: the production "
                    "fit carries the surviving deep-tail persistence alone — no cell coincides"
                )
    else:
        production = "prior" if prior_ok else "free"
    return AnchoringPlan(
        available=available, production=production, family=state.fit_settings().model,
        filter_mode=opts.observationFilterMode, prior_mode=opts.priorPersistenceMode, notes=notes,
    )


def _cache_key(state: AppState, ticker: str, iso: str, fit_mode: str, cell: str) -> tuple:
    return (service.fit_key(state, ticker, iso, fit_mode), "anchoring", cell)


def _fresh_committed(state: AppState, ticker: str, iso: str, fit_mode: str) -> FitRecord | None:
    """The committed record when its fit_key equals the live key (read-only)."""
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    if ptr is None or ptr[0] != service.fit_key(state, ticker, iso, fit_mode):
        return None
    return state.get_fit(ptr[0])


def anchoring_cell(
    state: AppState, ticker: str, iso: str, fit_mode: str, prepared,
    plan: AnchoringPlan, cell: str | None,
) -> tuple[CompareModelFit, FitRecord]:
    """(row, record) of one cell of the displayed family — cached, the fresh
    committed record reused for the production cell, else a shadow fit.

    ``cell=None`` means PRODUCTION routing (``anchoring=None`` in the task
    builder): the displayed family's production fit whether or not a named
    cell coincides with it; the row's ``anchoring`` then names that cell (or
    stays None). A named cell must be in ``plan.available`` (ValueError)."""
    from volfit.api.compare import _model_row, compare_cache

    if cell is not None and cell not in plan.available:
        raise ValueError(f"anchoring cell '{cell}' is not available on this node: {plan.notes.get(cell, '')}")
    is_production = cell is None or cell == plan.production
    name = _PRODUCTION if is_production else cell
    key = _cache_key(state, ticker, iso, fit_mode, name)
    cache = compare_cache(state)
    row = cache.get(key)
    record = cache.slices.get(key)
    if row is not None and record is not None:
        return row, record

    k, w, _ = service.edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(state.fit_settings().weightScheme, k, w)
    band = service.edited_band(state, ticker, iso, prepared, fit_mode)
    committed = _fresh_committed(state, ticker, iso, fit_mode) if is_production else None
    if committed is not None:
        record, fit_ms = committed, None
    else:
        prev_ctx, next_ctx = service.single_node_calendar_context(state, ticker, iso, fit_mode)
        task = service.single_node_task(
            state, ticker, iso, prepared, fit_mode, prev_ctx, next_ctx,
            anchoring=None if is_production else cell,
        )
        t0 = time.perf_counter()
        outcome = run_slice_fit(task)  # inline, never committed
        fit_ms = (time.perf_counter() - t0) * 1e3
        record = FitRecord(prepared=prepared, result=outcome.result, display=outcome.display)
    family = plan.family
    row = _model_row(
        family, displayed_slice(record), prepared, k, w, weights, band,
        fit_ms=fit_ms, reused=committed is not None,
    )
    row.anchoring = plan.production if is_production else cell
    cache.put(key, row, record)
    return row, record


def attach_pull(rows: dict[str, CompareModelFit], prepared) -> None:
    """Fill the pull columns of every row against the ``free`` row (no-op
    without it): ATM distance (vol bp), skew distance, curve RMS distance
    over the quoted range (vol bp). The free row reads zero on all three."""
    free = rows.get("free")
    if free is None or not free.ok:
        return
    k_lo, k_hi = float(np.min(prepared.k)), float(np.max(prepared.k))
    free_k = np.array([p.k for p in free.curve])
    free_v = np.array([p.vol for p in free.curve])
    inside = (free_k >= k_lo) & (free_k <= k_hi)
    for row in rows.values():
        if not row.ok:
            continue
        if row.atmVol is not None and free.atmVol is not None:
            row.pullAtmBp = round((row.atmVol - free.atmVol) * 1e4, 2)
        if row.skew is not None and free.skew is not None:
            row.pullSkew = round(row.skew - free.skew, 5)
        v = np.array([p.vol for p in row.curve])
        if v.shape == free_v.shape and inside.any():
            d = (v - free_v)[inside]
            row.pullCurveBp = round(float(np.sqrt(np.mean(d * d))) * 1e4, 2)


def append_cells(
    state: AppState, ticker: str, iso: str, fit_mode: str, prepared,
    plan: AnchoringPlan, cells: tuple[str, ...], response,
) -> None:
    """Append the requested AVAILABLE cells of the displayed family to a
    compare response, each once: the production cell is the family's plain
    row (already in the response when that family was asked — never
    duplicated), ``free`` is fitted whenever any cell is (the pull
    reference), a cell's fit break is a row (ok=False), never a 500."""
    from volfit.api.compare import _LABELS

    wanted = [c for c in cells if c in plan.available]
    if not wanted:
        return
    rows: dict[str, CompareModelFit] = {}
    # The family's plain row IS the production cell: it joins the pull set
    # whenever any cell is asked, so the table reads production vs free too.
    plain = next((r for r in response.models if r.model == plan.family), None)
    if plain is not None and plan.production is not None:
        rows[plan.production] = plain
    for cell in ["free"] + [c for c in wanted if c != "free"]:
        if cell in rows:
            continue
        try:
            rows[cell], _ = anchoring_cell(state, ticker, iso, fit_mode, prepared, plan, cell)
        except Exception as exc:  # noqa: BLE001 - a fit break is a row, not a 500
            rows[cell] = CompareModelFit(
                model=plan.family, label=_LABELS[plan.family], ok=False,
                error=type(exc).__name__ + ": " + str(exc)[:160], anchoring=cell,
            )
    attach_pull(rows, prepared)
    for cell in wanted:
        if rows[cell] not in response.models:
            response.models.append(rows[cell])


def display_record(
    state: AppState, ticker: str, iso: str, fit_mode: str, record: FitRecord, anchoring: str | None
) -> tuple[FitRecord, str | None]:
    """The record a node VIEW should draw under an anchoring switch:
    ``(record, None)`` for production / an unavailable cell / the cell that
    IS production; else the shadow cell's UN-transported record and the cell
    name. Callers apply the spot-move transport exactly as fit_or_get does."""
    if anchoring is None or anchoring == _PRODUCTION:
        return record, None
    plan = resolve_anchoring(state, ticker, iso, fit_mode, record.prepared)
    if anchoring not in plan.available or anchoring == plan.production:
        return record, None
    _row, shadow = anchoring_cell(state, ticker, iso, fit_mode, record.prepared, plan, anchoring)
    return shadow, anchoring
