"""Calibration / data-fetch workflow actions (the trigger model).

Implements the explicit, mode-gated triggers (ROADMAP workflow):

  * ``fetch_spots``   — probe the live provider spot for each ticker and apply it
    as a spot SHIFT to the market-following tickers, transporting the surface
    (no recalibration) — with ``sync_market_shifts`` in volfit.api.workflow_spot,
    re-exported here;
  * ``fetch_options`` — refetch the option chains (``state.refresh_chain``); when
    ``autoCalibrate`` is on, kick off a background calibration of the lit nodes;
  * ``calibrate``     — (re)calibrate a scope of lit nodes at the chain's own
    spot: a single node / one ticker synchronously, or ALL lit nodes in the
    background via the job manager (``state.calibration_jobs``). V3.5 item 9
    splits the background verb into stages: ``calibrate_all`` (parametric then
    LV, the historical combined action), ``calibrate_parametric_all`` and
    ``calibrate_lv_all`` — all composed from the SAME stage builders
    (volfit.api.workflow_stages), so a fit is byte-identical whichever verb
    produced it;
  * ``seed_priors``   — explicit prev-close prior seeding (built, calibrated and
    saved only on demand).

The unified snapshot verb (``POST /fetch/snapshot``: chains -> spot transport ->
optional cheap prior roll -> optional auto-calibrate, V3.7 item 15) lives in
volfit.api.workflow_fetch and composes the blocks above; the Spot panel's
per-ticker **Recalibrate** (the same verb for ONE ticker) lives in
volfit.api.workflow_ticker, likewise composed.

Calibration snapshot rule (``calibration_chains``, shared by every Calibrate
verb, global or per ticker): while the active source STREAMS, a fresh
SYNCHRONOUS snapshot of the book — quotes AND spot read together, never a
metered request; otherwise the LAST FETCHED chain (fetched once if absent).

A "lit" node (volfit AppState lit/dark designation) is one the user marks as an
observed source; those are the calibration targets. Dark nodes are graph
extrapolation targets and are not calibrated here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from volfit.api import fit_pool, service, workflow_stages
from volfit.api.schemas import (
    ActivityInfo,
    CalibrationStatus,
    FetchResult,
    SchedulerStatus,
)
from volfit.api.state import AppState
from volfit.api.workflow_spot import (  # noqa: F401  (re-exports: the scheduler + test seams)
    fetch_spots,
    sync_market_shifts,
)
from volfit.api.workflow_stages import (  # noqa: F401  (re-exports: test seams + callers)
    Group,
    _parametric_items,
    lit_nodes,
)


def _source_label(state: AppState) -> str:
    """Human-readable name of the active data source (for the fetch narration)."""
    from volfit.api.datasource import SOURCE_LABELS

    sid = state.active_source
    return SOURCE_LABELS.get(sid, sid.title())


# ----------------------------------------------------------------- status
def _stale_count(state: AppState, nodes: list[tuple[str, str]], fit_mode: str) -> int:
    return sum(1 for t, iso in nodes if service.node_dirty(state, t, iso, fit_mode))


def _lv_stale_tickers(state: AppState, nodes: list[tuple[str, str]], fit_mode: str) -> int:
    """Lit tickers whose LV (affine) surface is STALE (calibrated before, inputs
    drifted since) — the "Local-Vol only" badge count. 0 while Local-Vol is
    gated off (``localVolEnabled``), mirroring how the toggle hides the LV
    workspace; never-calibrated tickers are not counted (same semantics as the
    per-node ``staleNodes``)."""
    if not state.options().localVolEnabled:
        return 0
    from volfit.api.affine_fit import affine_dirty
    from volfit.api.schemas_affine import AffineFitRequest

    request = AffineFitRequest(fitMode=fit_mode)
    seen: list[str] = []
    for t, _iso in nodes:
        if t not in seen:
            seen.append(t)
    count = 0
    for ticker in seen:
        try:
            if affine_dirty(state, ticker, request):
                count += 1
        except Exception:
            pass  # a ticker mid-refetch / unavailable: skip, never break status
    return count


def status(state: AppState, fit_mode: str = "mid") -> CalibrationStatus:
    """Background-job state plus lit / stale node accounting."""
    job = state.calibration_jobs.status()
    nodes = lit_nodes(state)
    act = state.activity.snapshot()
    return CalibrationStatus(
        running=job.running,
        total=job.total,
        done=job.done,
        current=job.current,
        phase=job.phase,
        error=job.error,
        cancelled=job.cancelled,
        litNodes=len(nodes),
        staleNodes=_stale_count(state, nodes, fit_mode),
        lvStaleTickers=_lv_stale_tickers(state, nodes, fit_mode),
        spotVersion=state.spot_version,
        epoch=state.calib_epoch,
        activity=ActivityInfo(
            active=act.active,
            stage=act.stage,
            message=act.message,
            detail=act.detail,
            done=act.done,
            total=act.total,
            seq=act.seq,
        ),
    )


def scheduler_status(state: AppState) -> SchedulerStatus:
    """Scheduler modes + countdowns for the TopBar fetch controls."""
    opts = state.options()
    sched = getattr(state, "scheduler", None)
    return SchedulerStatus(
        running=bool(sched is not None and sched.is_running()),
        spotMode=opts.spotMode,
        optionsFetchMode=opts.optionsFetchMode,
        autoCalibrate=opts.autoCalibrate,
        localVolEnabled=opts.localVolEnabled,
        secondsToNextOptions=sched.seconds_to_next_options() if sched is not None else -1.0,
        secondsToNextSpot=sched.seconds_to_next_spot() if sched is not None else -1.0,
        unifiedFetch=bool(opts.schedulerUnifiedFetch),
    )


# -------------------------------------------------------------- calibrate
def calibration_chains(state: AppState, tickers: list[str]) -> bool:
    """Load the chain each Calibrate verb fits ON (the ONE rule, global and
    per-ticker verbs alike). Returns whether a streaming snapshot was taken.

    * The active source STREAMS: a fresh SYNCHRONOUS snapshot of the book —
      ``refresh_chain`` serves quotes AND spot from the book, read together, so
      the fit is anchored at the spot its quotes were quoted against. The
      calibrated pointers are preserved (the previous fit stays, stale, until
      the job lands).
    * No stream: the LAST FETCHED chain — no request. Fetched once only if
      absent (the gated workflow: "press Calibrate before Fetch" still works;
      before it the ladder is empty and ``lit_nodes`` would find nothing).
    Best-effort per ticker — an unreachable feed is skipped, as ``lit_nodes``
    already tolerates."""
    streaming = state.is_streaming()
    source = _source_label(state)
    for ticker in tickers:
        try:
            if streaming:
                with state.activity.activity(
                    "fetch", f"Snapshotting {ticker} quotes + spot from the {source} book"
                ):
                    state.refresh_chain(ticker)
            else:
                state.ensure_chain(ticker)
        except Exception:
            pass
    return streaming


def _start_stages(state: AppState, stages: list[list[Group]]) -> bool:
    """Pool-wrap and launch calibration stages on the ONE background job.

    Shared launcher for every background Calibrate verb: each group's thunks
    ship their CPU-heavy fits to the fit process pool (``fit_pool.pooled_thunk``)
    while the chain inside a group stays sequential, so a multi-ticker Calibrate
    scales with the configured workers (VOLFIT_CALIB_WORKERS; 1 = the historical
    serial behaviour, byte-identical fits either way). Prewarm keeps the
    historical gate: workers spin up only when the FIRST stage has groups.
    Returns False (without starting) if a job is already running — the global
    one-job-at-a-time contract holds across all three verbs."""
    workers = fit_pool.configured_workers()

    def pooled(items):  # background work: the heavy fits are pool-eligible
        if workers <= 1:
            return items
        return [(label, phase, fit_pool.pooled_thunk(t)) for label, phase, t in items]

    wrapped = [
        [(ticker, pooled(items)) for ticker, items in groups] for groups in stages
    ]
    if workers > 1 and wrapped and wrapped[0]:
        fit_pool.prewarm()  # workers import volfit while the de-Am prep runs
    return state.calibration_jobs.start_stages(wrapped, workers=workers)


def calibrate_all(state: AppState, fit_mode: str = "mid") -> bool:
    """Start a BACKGROUND calibration of every lit node, then (when Local-Vol is
    enabled) each lit ticker's LV (affine) surface. Items carry a coarse ``phase``
    ("Parametric" | "LV") so the UI can show "Calibrating Parametric" then
    "Calibrating LV". When ``enforceCalendar`` is on the parametric items are
    calendar-coupled per ticker (``_coupled_ticker_items``); else they are
    independent per node. False if a job is already running.

    The stage barrier is kept: LV starts only after every parametric group
    finished (its cold-start seed reads the LQD fits). Composes EXACTLY the
    stage builders of volfit.api.workflow_stages — same order, same gating as
    the historical single verb (semantics locked by test_api_workflow /
    test_calibration_workflow / test_gated_workflow)."""
    calibration_chains(state, state.active_tickers())  # the calibration snapshot
    stages = [workflow_stages.parametric_stage(state, fit_mode)]
    if state.options().localVolEnabled:
        lv_groups = workflow_stages.lv_stage(state, fit_mode)
        if lv_groups:
            stages.append(lv_groups)
    return _start_stages(state, stages)


def calibrate_parametric_all(state: AppState, fit_mode: str = "mid") -> bool:
    """Background-calibrate every lit node's PARAMETRIC slice only (V3.5 item 9).

    The fast common loop: identical parametric stage (groups, item order,
    warm-start / calendar chains) as ``calibrate_all``, with no LV stage — each
    ticker's LV (affine) pointer is left untouched, so the LV surface goes /
    stays STALE until an LV calibrate. False if a job is already running."""
    calibration_chains(state, state.active_tickers())  # the calibration snapshot
    return _start_stages(state, [workflow_stages.parametric_stage(state, fit_mode)])


def calibrate_lv_all(state: AppState, fit_mode: str = "mid") -> bool:
    """Background-calibrate every lit ticker's LV (affine) surface ONLY.

    No parametric stage and no parametric barrier: the LV cold-start
    ``_parametric_seed`` is best-effort by construction (affine_fit) — with
    fewer than two warm parametric slices it falls back to the flat seed. By
    the theta0/theta_ref decoupling the seed changes only the starting point,
    never the regularization or the converged optimum, so an LV-only fit lands
    the same surface as a seeded one; ITERATE COUNTS MAY DIFFER vs a run seeded
    by a just-finished parametric stage (recorded, accepted). Runs regardless
    of ``localVolEnabled`` — the explicit verb needs no Options round-trip; the
    toggle keeps gating only the combined ``calibrate_all`` (wire compat) and
    the Local-Vol workspace tab. False if a job is already running."""
    calibration_chains(state, state.active_tickers())  # the calibration snapshot
    return _start_stages(state, [workflow_stages.lv_stage(state, fit_mode)])


def calibrate_ticker(state: AppState, ticker: str, fit_mode: str = "mid") -> int:
    """Synchronously (re)calibrate one ticker's lit expiries + its LV surface.

    Honours ``enforceCalendar`` (calendar-couples the expiries) by running the
    same work items as the background path, just inline."""
    calibration_chains(state, [ticker])  # the calibration snapshot
    nodes = lit_nodes(state, [ticker])
    for _, _, thunk in _parametric_items(state, nodes, fit_mode):
        thunk()
    if nodes and state.options().localVolEnabled:
        workflow_stages._affine_thunk(state, ticker, fit_mode)()  # also (re)build the LV surface
    return len(nodes)


def calibrate_one(state: AppState, ticker: str, expiry_iso: str, fit_mode: str = "mid") -> None:
    """Synchronously (re)calibrate a single node (re-anchoring its spot)."""
    service.calibrate_node(state, ticker, expiry_iso, fit_mode)


# ------------------------------------------------------------------ fetch
def _refresh_chains(state: AppState, chosen: list[str]) -> tuple[list[str], dict[str, float]]:
    """The chain-refresh block shared by ``fetch_options`` and the unified
    ``fetch_snapshot`` (volfit.api.workflow_fetch): concurrently refetch each
    chosen ticker's chain (≤8-wide pool) and return (fetched tickers in chosen
    order, ticker -> chain spot). ``refresh_chain`` marks the nodes stale and
    bumps the data version while PRESERVING the calibrated pointers + spot
    shift (the frozen-until-Calibrate contract)."""
    source = _source_label(state)

    def _refresh_one(ticker: str) -> tuple[str, float | None]:
        """Refetch one ticker's chain (blocking network); None spot on failure.

        Each ticker is independent — ``refresh_chain`` touches only that ticker's
        snapshot/forwards/version under the per-call lock and does its network
        I/O outside it, and the activity reporter + provider HTTP client are
        thread-safe — so the chains can be fetched concurrently instead of
        serially (turning Σ per-ticker latency into the slowest single fetch)."""
        try:
            with state.activity.activity("fetch", f"Fetching {ticker} quotes from {source}"):
                return ticker, float(state.refresh_chain(ticker))
        except Exception:
            return ticker, None

    spots: dict[str, float] = {}
    fetched: list[str] = []
    if chosen:
        # pool.map preserves input order, so ``fetched`` keeps the chosen order.
        with ThreadPoolExecutor(max_workers=min(8, len(chosen))) as pool:
            for ticker, spot in pool.map(_refresh_one, chosen):
                if spot is not None:
                    spots[ticker] = spot
                    fetched.append(ticker)
    return fetched, spots


def fetch_options(
    state: AppState, tickers: list[str] | None = None, fit_mode: str = "mid"
) -> FetchResult:
    """Refetch option chains; auto-calibrate the lit nodes when enabled.

    Each ticker's chain is refetched (marking its nodes stale); if
    ``autoCalibrate`` is on, a background calibration of ALL lit nodes is then
    started. Otherwise the nodes stay stale until the user presses Calibrate.
    """
    chosen = tickers if tickers is not None else state.active_tickers()
    fetched, spots = _refresh_chains(state, chosen)
    sync_market_shifts(state, fetched)  # market-following tickers move to the new chain spot
    started = False
    if state.options().autoCalibrate and fetched:
        started = calibrate_all(state, fit_mode)
    return FetchResult(tickers=fetched, spots=spots, calibrationStarted=started)


def stream_refit(state: AppState, fit_mode: str = "mid") -> bool:
    """The streaming throttled refit: refetch each ticker's chain (served from the
    live WS book) and recalibrate ALL lit nodes in the background.

    Gated by ``autoCalibrate`` — it is the master switch for unattended refits, so
    with it OFF this is a no-op (the surface still tracks spot via the transport
    poll; nodes stay frozen/stale until an explicit Calibrate), matching
    ``fetch_options``. Returns False if disabled, nothing fetched, or a calibration
    job is already running (the throttle then skips this cycle).
    """
    if not state.options().autoCalibrate:
        return False
    source = _source_label(state)
    fetched = False
    for ticker in state.active_tickers():
        try:
            with state.activity.activity("fetch", f"Streaming {ticker} quotes from {source}"):
                state.refresh_chain(ticker)  # reads the live book under streaming
            fetched = True
        except Exception:
            continue
    return calibrate_all(state, fit_mode) if fetched else False


# ------------------------------------------------------------------ priors
def seed_priors(state: AppState, tickers: list[str] | None = None, fit_mode: str = "mid") -> int:
    """Explicitly seed previous-close priors for lit nodes lacking a saved one.

    For each such node: switch the as-of to the provider's previous close, fetch +
    calibrate that chain, save the LQD fit as the node's prior, then restore the
    live as-of. Returns the number of priors seeded. Skips nodes that already have
    a saved prior and tickers whose provider has no previous-close history.
    """
    from volfit.api.state import AsOfSelection
    from volfit.models.lqd.basis import LQDParams  # noqa: F401  (type clarity)
    from volfit.api.state import PriorRecord

    chosen = tickers if tickers is not None else state.active_tickers()
    if "prev_close" not in state.provider.historical_modes():
        return 0
    seeded = 0
    live = state.as_of
    try:
        for ticker in chosen:
            nodes = [
                (t, iso) for t, iso in lit_nodes(state, [ticker])
                if state.get_prior((t, iso)) is None
            ]
            if not nodes:
                continue
            state.set_as_of(AsOfSelection(mode="prev_close"))
            for t, iso in nodes:
                try:
                    record = service._compute_fit(state, t, iso, fit_mode)
                except Exception:
                    continue
                prior = PriorRecord(
                    curve=service.model_curve(record),
                    params=record.result.params,
                    t=record.prepared.t,
                )
                state.save_prior((t, iso), prior)
                seeded += 1
            state.set_as_of(live)  # restore between tickers (set_as_of clears caches)
    finally:
        state.set_as_of(live)
    return seeded
