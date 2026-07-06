"""Calibration / data-fetch workflow actions (the trigger model).

Implements the explicit, mode-gated triggers (ROADMAP workflow):

  * ``fetch_spots``   — probe the live provider spot for each ticker and apply it
    as a spot SHIFT, transporting the surface (no recalibration);
  * ``fetch_options`` — refetch the option chains (``state.refresh_chain``); when
    ``autoCalibrate`` is on, kick off a background calibration of the lit nodes;
  * ``calibrate``     — (re)calibrate a scope of lit nodes at the chain's own
    spot: a single node / one ticker synchronously, or ALL lit nodes in the
    background via the job manager (``state.calibration_jobs``);
  * ``seed_priors``   — explicit prev-close prior seeding (built, calibrated and
    saved only on demand).

A "lit" node (volfit AppState lit/dark designation) is one the user marks as an
observed source; those are the calibration targets. Dark nodes are graph
extrapolation targets and are not calibrated here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from volfit.api import fit_pool, service
from volfit.api.schemas import (
    ActivityInfo,
    CalibrationStatus,
    FetchResult,
    LiveSpot,
    SchedulerStatus,
    SpotShiftRequest,
)
from volfit.api.spot import set_shift as _set_spot_shift
from volfit.api.state import AppState


def _source_label(state: AppState) -> str:
    """Human-readable name of the active data source (for the fetch narration)."""
    from volfit.api.datasource import SOURCE_LABELS

    sid = state.active_source
    return SOURCE_LABELS.get(sid, sid.title())


# --------------------------------------------------------------- lit nodes
def lit_nodes(state: AppState, tickers: list[str] | None = None) -> list[tuple[str, str]]:
    """Every lit (ticker, expiry-ISO) node, the calibration set, nearest first."""
    chosen = tickers if tickers is not None else state.active_tickers()
    out: list[tuple[str, str]] = []
    for ticker in chosen:
        try:
            expiries = sorted(state.forwards(ticker))
        except Exception:
            continue  # a ticker unavailable on the active feed is skipped
        for expiry in expiries:
            iso = expiry.isoformat()
            if state.node_lit(ticker, iso):
                out.append((ticker, iso))
    return out


def _stale_count(state: AppState, nodes: list[tuple[str, str]], fit_mode: str) -> int:
    return sum(1 for t, iso in nodes if service.node_dirty(state, t, iso, fit_mode))


# ----------------------------------------------------------------- status
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
    )


# -------------------------------------------------------------- calibrate
def _affine_thunk(state: AppState, ticker: str, fit_mode: str):
    """A work-item thunk that re-calibrates one ticker's LV (affine) surface,
    re-anchored at the chain spot. Swallows the too-few-quotes case (a ticker
    with < 2 fittable expiries simply has no LV surface)."""
    from volfit.api.affine_fit import calibrate_affine_surface
    from volfit.api.schemas_affine import AffineFitRequest

    def thunk() -> None:
        state.set_spot_shift(ticker, 0.0)  # re-anchor at the chain's own spot
        try:
            with state.activity.activity(
                "localvol", f"Calibrating {ticker} local-vol surface", "Dupire fit"
            ):
                calibrate_affine_surface(state, ticker, AffineFitRequest(fitMode=fit_mode))
        except ValueError:
            pass  # < 2 expiries with quotes: no LV surface for this ticker

    return thunk


def _independent_ticker_items(
    state: AppState, ticker: str, isos: list[str], fit_mode: str
) -> list[tuple[str, str, object]]:
    """INDEPENDENT (no calendar coupling) per-node items for one ticker that still
    warm-start each expiry from the previous, shorter-T expiry's freshly-fit LQD
    params.

    Adjacent maturities have nearly the same smile, so the seed lands trf close to
    the optimum and cuts its (P+1)-eval Jacobian iterations. The sweep stays
    deterministic — fixed ascending-T order, every expiry recomputed from scratch
    each pass — so a node's committed fit is identical regardless of edit history
    (the single-node Calibrate / undo path is untouched and cold-starts). ``isos``
    must be ascending-T (``lit_nodes`` is nearest-first)."""
    ctx: dict = {"prev": None}

    def make(iso: str):
        def thunk() -> None:
            record = service.calibrate_node(state, ticker, iso, fit_mode, init=ctx["prev"])
            ctx["prev"] = record.result.params  # seed the next, longer expiry

        return thunk

    return [(f"{ticker} {iso}", "Parametric", make(iso)) for iso in isos]


def _coupled_ticker_items(
    state: AppState, ticker: str, isos: list[str], fit_mode: str
) -> list[tuple[str, str, object]]:
    """Per-expiry calibration items for one ticker that thread the previous
    (shorter-T) expiry's slice as a calendar floor (enforceCalendar ON).

    The items stay per-expiry so the progress display keeps node granularity, but
    they share a context that — on first touch — re-anchors the ticker at its own
    chain spot and builds the prepared-quote plan, then each item fits + commits
    its slice (``service.fit_and_commit_slice``) and hands its result to the next,
    longer expiry. ``isos`` must be ascending-T (``lit_nodes`` is nearest-first).

    Caveat (documented follow-up): a later INDEPENDENT recompute of one node via
    ``service._compute_fit`` (e.g. autoCalibrate ON + a single input change) has no
    cross-expiry context, so the calendar coupling only holds until such a refit.
    Under the default trigger-gated workflow the coupled fit stays frozen/displayed
    until the next explicit Calibrate.
    """
    ctx: dict = {"plan": None, "prev": None, "prev_display": None}

    def ensure_plan() -> dict:
        if ctx["plan"] is None:
            state.set_spot_shift(ticker, 0.0)  # re-anchor at the chain's own spot
            want = set(isos)
            ctx["plan"] = {
                iso: prepared
                for iso, prepared in service.surface_inputs(state, ticker, fit_mode)
                if iso in want
            }
        return ctx["plan"]

    def make(iso: str):
        def thunk() -> None:
            prepared = ensure_plan().get(iso)
            if prepared is None:
                return  # expiry left the chain between build and run
            record = service.fit_and_commit_slice(
                state, ticker, iso, prepared, ctx["prev"], True, fit_mode,
                ctx["prev_display"],
            )
            ctx["prev"] = record.result
            ctx["prev_display"] = record.display  # overlay calendar floor for next-T

        return thunk

    return [(f"{ticker} {iso}", "Parametric", make(iso)) for iso in isos]


def _parametric_groups(
    state: AppState, nodes: list[tuple[str, str]], fit_mode: str
) -> list[tuple[str, list[tuple[str, str, object]]]]:
    """Per-ticker parametric calibration groups for a set of lit nodes.

    Each group is one ticker's ordered item chain — calendar-coupled when
    ``enforceCalendar`` is on, else independent-but-warm-started — so groups
    can run CONCURRENTLY (tickers are independent) while the chain inside a
    group stays sequential (the warm-start / calendar threading needs the
    previous, shorter expiry's fresh fit)."""
    by_ticker: dict[str, list[str]] = {}
    for t, iso in nodes:  # nodes are nearest-first, so each list is ascending-T
        by_ticker.setdefault(t, []).append(iso)
    coupled = state.options().enforceCalendar
    return [
        (
            ticker,
            _coupled_ticker_items(state, ticker, isos, fit_mode)
            if coupled
            else _independent_ticker_items(state, ticker, isos, fit_mode),
        )
        for ticker, isos in by_ticker.items()
    ]


def _parametric_items(
    state: AppState, nodes: list[tuple[str, str]], fit_mode: str
) -> list[tuple[str, str, object]]:
    """Parametric calibration items for a set of lit nodes, flattened in the
    historical ticker-then-ascending-T order (the sync ``calibrate_ticker``
    path and tests; the background job runs the grouped form)."""
    return [
        item for _t, items in _parametric_groups(state, nodes, fit_mode) for item in items
    ]


def _ensure_chains(state: AppState, tickers: list[str]) -> None:
    """Calibrate's auto-fetch: load each ticker's chain so its lit nodes resolve.

    In the gated workflow a plain read never fetches, so before Calibrate the
    expiry ladder (``state.forwards``) is empty and ``lit_nodes`` would find
    nothing. Fetching here makes "press Calibrate before Fetch" do the sensible
    thing (fetch then fit). Best-effort per ticker — an unreachable feed is
    skipped, exactly as ``lit_nodes`` already tolerates."""
    for ticker in tickers:
        try:
            state.ensure_chain(ticker)
        except Exception:
            pass


def calibrate_all(state: AppState, fit_mode: str = "mid") -> bool:
    """Start a BACKGROUND calibration of every lit node, then (when Local-Vol is
    enabled) each lit ticker's LV (affine) surface. Items carry a coarse ``phase``
    ("Parametric" | "LV") so the UI can show "Calibrating Parametric" then
    "Calibrating LV". When ``enforceCalendar`` is on the parametric items are
    calendar-coupled per ticker (``_coupled_ticker_items``); else they are
    independent per node. False if a job is already running.

    The parametric stage runs its per-ticker groups CONCURRENTLY: each group's
    thunks ship their slice fits to the fit process pool (``fit_pool.pooled_thunk``)
    while the warm-start chain stays sequential inside its group, so a
    multi-ticker Calibrate scales with the configured workers
    (VOLFIT_CALIB_WORKERS; 1 = the historical serial behaviour, byte-identical
    fits either way). The LV stage keeps the historical serial order after a
    barrier — the affine fits run in-process (Numba) and are not pooled yet."""
    _ensure_chains(state, state.active_tickers())  # auto-fetch so lit nodes resolve
    workers = fit_pool.configured_workers()
    groups = []
    for ticker, items in _parametric_groups(state, lit_nodes(state), fit_mode):
        if workers > 1:  # background work: slice fits are pool-eligible
            items = [(label, phase, fit_pool.pooled_thunk(t)) for label, phase, t in items]
        groups.append((ticker, items))
    stages: list[list[tuple[str, list]]] = [groups]
    if state.options().localVolEnabled:
        lv_items = [
            (f"{ticker} · LV surface", "LV", _affine_thunk(state, ticker, fit_mode))
            for ticker in _lit_tickers(state)
        ]
        if lv_items:
            stages.append([("LV", lv_items)])
    if workers > 1 and groups:
        fit_pool.prewarm()  # workers import volfit while the de-Am prep runs
    return state.calibration_jobs.start_stages(stages, workers=workers)


def _lit_tickers(state: AppState) -> list[str]:
    """Active tickers that have at least one lit node (LV calibration targets)."""
    seen: list[str] = []
    for t, _ in lit_nodes(state):
        if t not in seen:
            seen.append(t)
    return seen


def calibrate_ticker(state: AppState, ticker: str, fit_mode: str = "mid") -> int:
    """Synchronously (re)calibrate one ticker's lit expiries + its LV surface.

    Honours ``enforceCalendar`` (calendar-couples the expiries) by running the
    same work items as the background path, just inline."""
    _ensure_chains(state, [ticker])  # auto-fetch so lit nodes resolve (gated workflow)
    nodes = lit_nodes(state, [ticker])
    for _, _, thunk in _parametric_items(state, nodes, fit_mode):
        thunk()
    if nodes and state.options().localVolEnabled:
        _affine_thunk(state, ticker, fit_mode)()  # also (re)build the LV surface
    return len(nodes)


def calibrate_one(state: AppState, ticker: str, expiry_iso: str, fit_mode: str = "mid") -> None:
    """Synchronously (re)calibrate a single node (re-anchoring its spot)."""
    service.calibrate_node(state, ticker, expiry_iso, fit_mode)


# ------------------------------------------------------------------ fetch
def fetch_spots(state: AppState, tickers: list[str] | None = None) -> dict[str, LiveSpot]:
    """Probe the live provider spot per ticker and apply it as a spot shift.

    Pure transport (no recalibration): the implied return vs the calibration
    anchor becomes the spot shift, moving the smile / term / LV grid. Returns the
    per-ticker probe so the UI can show the live level.
    """
    chosen = tickers if tickers is not None else state.active_tickers()
    source = _source_label(state)
    out: dict[str, LiveSpot] = {}
    for ticker in chosen:
        try:
            with state.activity.activity("fetch", f"Fetching {ticker} spot from {source}"):
                anchor = float(state.anchor_spot(ticker))
                live = float(state.live_spot(ticker))
        except Exception:
            continue
        ret = (live / anchor - 1.0) if anchor > 0.0 else 0.0
        _set_spot_shift(state, ticker, SpotShiftRequest(spotReturn=ret))
        out[ticker] = LiveSpot(ticker=ticker, anchorSpot=anchor, liveSpot=live, spotReturn=ret)
    return out


def fetch_options(
    state: AppState, tickers: list[str] | None = None, fit_mode: str = "mid"
) -> FetchResult:
    """Refetch option chains; auto-calibrate the lit nodes when enabled.

    Each ticker's chain is refetched (marking its nodes stale); if
    ``autoCalibrate`` is on, a background calibration of ALL lit nodes is then
    started. Otherwise the nodes stay stale until the user presses Calibrate.
    """
    chosen = tickers if tickers is not None else state.active_tickers()
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
