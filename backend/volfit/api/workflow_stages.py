"""Calibration stage/item builders for the workflow triggers (V3.5 item 9).

Factored out of ``volfit.api.workflow`` so the Calibrate verbs can compose the
two stages independently:

  * ``parametric_stage`` — per-ticker ordered chains of parametric slice fits
    over every lit node (calendar-coupled / symmetric / independent-warm-start
    per the Options), the historical stage 1 of ``calibrate_all``;
  * ``lv_stage``         — one LV (affine) surface item per lit ticker, the
    historical stage 2.

BYTE-IDENTITY CONTRACT: the per-ticker item ORDER inside a group must never
change — the warm-start and calendar chains consume ``lit_nodes``'s
ascending-T order, and a committed fit must be identical regardless of which
Calibrate verb produced it. These builders return UNPOOLED items; the caller
(``workflow._start_stages``) wraps them for the fit process pool exactly as
the historical ``calibrate_all`` did.
"""

from __future__ import annotations

from volfit.api import service
from volfit.api.state import AppState

#: One unit of background work: (display label, coarse UI phase, thunk) — the
#: shape volfit.api.jobs consumes.
Item = tuple[str, str, object]
Group = tuple[str, list[Item]]


# --------------------------------------------------------------- lit nodes
def lit_nodes(state: AppState, tickers: list[str] | None = None) -> list[tuple[str, str]]:
    """Every lit (ticker, expiry-ISO) node, the calibration set, nearest first."""
    chosen = tickers if tickers is not None else state.active_tickers()
    out: list[tuple[str, str]] = []
    for ticker in chosen:
        try:
            # settlement-instant order (same-date AM before PM) — the coupled
            # calibration items consume this list as their ascending-T chain
            expiries = service.ordered_expiries(state, ticker, state.forwards(ticker))
        except Exception:
            continue  # a ticker unavailable on the active feed is skipped
        for expiry in expiries:
            iso = expiry.isoformat()
            if state.node_lit(ticker, iso):
                out.append((ticker, iso))
    return out


def lit_tickers(state: AppState) -> list[str]:
    """Active tickers that have at least one lit node (LV calibration targets)."""
    seen: list[str] = []
    for t, _ in lit_nodes(state):
        if t not in seen:
            seen.append(t)
    return seen


# ------------------------------------------------------------- item chains
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
) -> list[Item]:
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


def _symmetric_ticker_items(
    state: AppState, ticker: str, isos: list[str], fit_mode: str
) -> list[Item]:
    """Symmetric-solver calibration items for one ticker (enforceCalendar ON,
    surfaceSolver "symmetric"): one independent phase-A fit+commit item per
    expiry (progress keeps node granularity) plus a single trailing screen +
    component-repair item (volfit.api.surface_symmetric.phase_b_repair) that
    re-commits only the repaired slices."""
    from volfit.api import surface_symmetric

    ctx = surface_symmetric.new_context()
    box: dict = {"plan": None}

    def ensure_plan() -> dict:
        if box["plan"] is None:
            state.set_spot_shift(ticker, 0.0)  # re-anchor at the chain's own spot
            want = set(isos)
            box["plan"] = {
                iso: prepared
                for iso, prepared in service.surface_inputs(state, ticker, fit_mode)
                if iso in want
            }
        return box["plan"]

    def make(iso: str):
        def thunk() -> None:
            prepared = ensure_plan().get(iso)
            if prepared is None:
                return  # expiry left the chain between build and run
            surface_symmetric.phase_a_slice(
                state, ticker, iso, prepared, fit_mode, ctx
            )

        return thunk

    def repair() -> None:
        surface_symmetric.phase_b_repair(state, ticker, fit_mode, ctx)

    items = [(f"{ticker} {iso}", "Parametric", make(iso)) for iso in isos]
    items.append((f"{ticker} calendar repair", "Parametric", repair))
    return items


def _coupled_ticker_items(
    state: AppState, ticker: str, isos: list[str], fit_mode: str
) -> list[Item]:
    """Per-expiry calibration items for one ticker that thread the previous
    (shorter-T) expiry's slice as a calendar floor (enforceCalendar ON).

    The items stay per-expiry so the progress display keeps node granularity, but
    they share a context that — on first touch — re-anchors the ticker at its own
    chain spot and builds the prepared-quote plan, then each item fits + commits
    its slice (``service.fit_and_commit_slice``) and hands its result to the next,
    longer expiry. ``isos`` must be ascending-T (``lit_nodes`` is nearest-first).

    Caveat: a later INDEPENDENT recompute of one node via
    ``service._compute_fit`` (e.g. autoCalibrate ON + a single input change) has no
    cross-expiry context by default, so the calendar coupling only holds until such
    a refit; under the default trigger-gated workflow the coupled fit stays
    frozen/displayed until the next explicit Calibrate. The opt-in
    ``OptionsSettings.calendarOnRefit`` closes the gap: with it (and
    ``enforceCalendar``) a single-node refit threads the adjacent FRESH committed
    slices as its confined floor/ceiling and fingerprints them into its fit key.
    """
    ctx: dict = {"plan": None, "prev": None, "prev_display": None, "prev_k": None}

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
                ctx["prev_display"], ctx["prev_k"],
            )
            ctx["prev"] = record.result
            ctx["prev_display"] = record.display  # overlay calendar floor for next-T
            ctx["prev_k"] = service.retained_k(state, ticker, iso, prepared)

        return thunk

    return [(f"{ticker} {iso}", "Parametric", make(iso)) for iso in isos]


# ----------------------------------------------------------------- stages
def _parametric_groups(
    state: AppState, nodes: list[tuple[str, str]], fit_mode: str
) -> list[Group]:
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
    symmetric = coupled and state.options().surfaceSolver == "symmetric"

    def items(ticker: str, isos: list[str]):
        if symmetric:
            return _symmetric_ticker_items(state, ticker, isos, fit_mode)
        if coupled:
            return _coupled_ticker_items(state, ticker, isos, fit_mode)
        return _independent_ticker_items(state, ticker, isos, fit_mode)

    return [(ticker, items(ticker, isos)) for ticker, isos in by_ticker.items()]


def _parametric_items(
    state: AppState, nodes: list[tuple[str, str]], fit_mode: str
) -> list[Item]:
    """Parametric calibration items for a set of lit nodes, flattened in the
    historical ticker-then-ascending-T order (the sync ``calibrate_ticker``
    path and tests; the background job runs the grouped form)."""
    return [
        item for _t, items in _parametric_groups(state, nodes, fit_mode) for item in items
    ]


def parametric_stage(state: AppState, fit_mode: str) -> list[Group]:
    """Stage 1: per-ticker parametric groups over every lit node (unpooled)."""
    return _parametric_groups(state, lit_nodes(state), fit_mode)


def lv_stage(state: AppState, fit_mode: str) -> list[Group]:
    """Stage 2: one LV (affine) surface item per lit ticker (unpooled).

    Identical items to the historical ``calibrate_all`` stage 2 — same labels,
    same "LV" phase, same per-ticker order (first-lit-node order)."""
    return [
        (ticker, [(f"{ticker} · LV surface", "LV", _affine_thunk(state, ticker, fit_mode))])
        for ticker in lit_tickers(state)
    ]
