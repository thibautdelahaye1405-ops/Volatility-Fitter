"""Per-application state and caches behind the volfit API (ROADMAP Phase 5).

Everything heavy is computed at most once: chain snapshots, parity-implied
forwards, per-(ticker, expiry, fit-mode, session-version) slice calibrations,
saved priors (display curve + fitted LQD params, so prior densities can be
rebuilt) and the lazily-built graph smile universe. Chains are fetched once
per process (live providers included — a snapshot is one observation) and
quote edits bump their session's version (a new cache key), so caches never
need invalidation. A single lock guards the
mutable dicts because WebSocket surface fits run on worker threads; the
universe build happens outside that lock (it re-enters the fit cache) and is
idempotent, so a rare double build is harmless.
"""

from __future__ import annotations

import math
import os
import threading
import warnings
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from volfit.api.fit_models import DisplayFit
from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import (
    EventSpec,
    FitSettings,
    ForwardPolicy,
    GraphBlockRule,
    GraphEdgeInput,
    GraphMessageConfigEnvelope,
    GraphMessageEdge,
    MarketSettings,
    OptionsSettings,
    SmilePoint,
)
from volfit.api.session import EditSession
from volfit.api.settings_persist import (
    clear_defaults,
    has_defaults,
    load_defaults,
    load_graph_block_rule,
    load_graph_edges,
    load_graph_idio,
    load_graph_message_config,
    load_graph_message_edges,
    save_defaults,
    save_graph_block_rule,
    save_graph_edges,
    save_graph_idio,
    save_graph_message_config,
    save_graph_message_edges,
)
from volfit.api.workspace import ScopedField, Workspace, build_doc, restore_doc
from volfit.graph.idio import IdioHistory
from volfit.api.varswap_session import VarSwapSession
from volfit.data.dividends import (
    Dividend,
    DividendModel,
    forward_consistent_cash_schedule,
    theoretical_forward,
)
from volfit.api.state_universe import UniverseMixin, UnknownNodeError  # noqa: F401 (re-export)
from volfit.data import governance
from volfit.data.forwards import ImpliedForward, ResolvedForward, implied_forwards
from volfit.data.provider import AsOf, OptionChainProvider, SyntheticProvider
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult

if TYPE_CHECKING:  # type-only: avoids a runtime import cycle with schemas_prior
    from volfit.api.schemas_prior import PriorSurfaceSnapshot

#: Year-fraction day count used across the API (ACT/365 fixed).
DAYS_PER_YEAR = 365.0

#: Sources whose live chains are NOT auto-captured to the VolStore. Massive and
#: Bloomberg have their own history channels (flat files / Terminal), so saving a
#: snapshot per fetch just bloats the store; intraday replay for them comes from
#: those channels, not the auto-capture. Yahoo (no history feed) still captures.
NO_AUTO_CAPTURE_SOURCES = frozenset({"massive", "bloomberg"})


@dataclass(frozen=True)
class FitRecord:
    """One cached slice calibration plus the inputs it was fitted to.

    ``result`` is always the LQD fit (the analytic backbone). ``display`` is
    the chosen non-LQD overlay fit when the hyperparameter panel selects
    SVI/sigmoid (volfit.api.fit_models); None means the LQD fit is displayed.
    """

    prepared: PreparedQuotes
    result: CalibrationResult
    display: DisplayFit | None = None


@dataclass(frozen=True)
class PriorRecord:
    """A saved prior: the display curve the Smile Viewer charts plus the
    fitted LQD parameters (and expiry year fraction) that produced it, so
    the prior's density/quantile function can be rebuilt via build_slice."""

    curve: list[SmilePoint]
    params: LQDParams
    t: float


@dataclass(frozen=True)
class AsOfSelection:
    """Which point in time the app serves chains as-of (global).

    - ``"live"``       latest from the active provider (default);
    - ``"prev_close"`` the provider's prior-session close;
    - ``"eod"``        the provider's close for the trading day ``on``;
    - ``"captured"``   replay the stored snapshot nearest at-or-before ``ts``
                       (any provider, from the VolStore capture history);
    - ``"intraday"``   the provider's chain at instant ``ts`` (Massive only).

    ``day`` / ``moment`` / ``offset`` are display-only metadata recording the
    high-level (date, moment) the as-of dropdown resolved this selection from
    ("close" / "latest" / "before_close" N minutes), so the UI can label and
    re-highlight the active pick. They never affect chain fetching.
    """

    mode: str = "live"
    on: date | None = None  # eod
    ts: datetime | None = None  # captured / intraday
    day: date | None = None  # the dropdown day this resolved from
    moment: str | None = None  # "close" | "latest" | "before_close"
    offset: int | None = None  # minutes-before-close for "before_close"


class AppState(UniverseMixin):
    """Provider handle plus all caches; one instance per FastAPI app.

    Universe management and per-ticker expiry selection are provided by
    UniverseMixin (volfit.api.state_universe); this class owns the caches the
    mixin operates on, plus market data, fit settings, forwards and sessions.

    STATE SCOPING (R1 item 9): the user-authored subset — settings, quote/
    var-swap edit sessions, priors, policies, filter states, graph overrides —
    lives in one serializable ``Workspace`` object (``self._ws``, see
    volfit.api.workspace). The attributes below delegate to it through
    ``ScopedField`` descriptors so every historical call site keeps its name;
    ``workspace_doc()`` / ``restore_workspace()`` serialize and swap the whole
    scoped state (hosting, durable filter state, replay fidelity).
    """

    # Workspace-scoped attributes (each delegates to self._ws — one line per
    # field so the scoped set is explicit and greppable).
    _fit_settings = ScopedField("fit_settings")
    _settings_version = ScopedField("settings_version")
    _options = ScopedField("options")
    _options_version = ScopedField("options_version")
    _filter_version = ScopedField("filter_version")
    _filter_states = ScopedField("filter_states")
    _graph_edges = ScopedField("graph_edges")
    _graph_block_rule = ScopedField("graph_block_rule")
    _graph_message_edges = ScopedField("graph_message_edges")
    _market_settings = ScopedField("market_settings")
    _events = ScopedField("events")
    _events_version = ScopedField("events_version")
    _forward_policies = ScopedField("forward_policies")
    _forwards_version = ScopedField("forwards_version")
    _spot_shift = ScopedField("spot_shift")
    _spot_version = ScopedField("spot_version")
    _spot_version_by_ticker = ScopedField("spot_version_by_ticker")
    _sessions = ScopedField("sessions")
    _varswap_sessions = ScopedField("varswap_sessions")
    _priors = ScopedField("priors")
    _active_prior = ScopedField("active_prior")
    _active_prior_source = ScopedField("active_prior_source")
    _active_prior_version = ScopedField("active_prior_version")
    _dark_nodes = ScopedField("dark_nodes")
    _last_fit_mode = ScopedField("last_fit_mode")
    _asof = ScopedField("asof")

    def __init__(
        self,
        reference_date: date,
        provider: OptionChainProvider | None = None,
        store_path: str | os.PathLike | None = None,
        providers: dict[str, OptionChainProvider] | None = None,
        active_source: str | None = None,
        gated: bool = False,
    ) -> None:
        self.reference_date = reference_date
        #: The serializable user-authored WORKSPACE (R1 item 9). Created FIRST:
        #: every ScopedField assignment below lands on it.
        self._ws = Workspace()
        #: Trigger-gated workflow (the live server; serve.py passes True). When on,
        #: READS never touch the feed or calibrate: ``snapshot`` serves cached-only
        #: (empty until an explicit Fetch), and ``service.displayed_base`` does NOT
        #: bootstrap a fit (the smile stays "no fit" until an explicit Calibrate).
        #: Quotes/spot are fetched only by ``refresh_chain``/``fetch_spots`` (the
        #: Fetch buttons) and ``ensure_chain`` (Calibrate's auto-fetch). Off (the
        #: default, used by the test app) keeps the historical lazy-fetch/bootstrap
        #: behaviour, so the existing suite is byte-identical.
        self._gated = gated
        #: Available market-data sources keyed by id ("yahoo"/"bloomberg"/
        #: "massive"/"synthetic"). `self.provider` is the *active* one; the Data
        #: Source selector switches `_active_source` at runtime.
        if providers:
            self._providers = dict(providers)
            self._active_source = active_source or next(iter(self._providers))
        else:
            one = provider or SyntheticProvider(reference_date=reference_date)
            self._providers = {_source_id_of(one): one}
            self._active_source = next(iter(self._providers))
        #: Cached (monotonic_ts, (level, detail)) feed status per source.
        self._status_cache: dict[str, tuple[float, tuple[str, str]]] = {}
        #: Global as-of selection (live by default); historical/captured chains
        #: flow through snapshot() exactly like live ones.
        self._asof = AsOfSelection()
        #: SQLite path for fit-history persistence (volfit.api.history);
        #: None (the default) keeps the API side-effect free.
        self.store_path = store_path
        #: The curated universe (mutable): starts as the provider's watchlist,
        #: the user adds/removes tickers via the universe-management API.
        self._active_tickers: list[str] = list(self.provider.list_tickers())
        #: Per-ticker expiry selection: all the provider lists (``_available``),
        #: the subset actually fetched/fitted (``_selected``), and whether that
        #: subset follows the default rule ("auto") or the user's picks ("custom").
        self._available: dict[str, list[date]] = {}
        self._selected: dict[str, list[date]] = {}
        self._selection_mode: dict[str, str] = {}
        #: Custom expiry picks of a restored saved universe, applied LAZILY on
        #: first resolve (so startup stays network-free): once a ticker's ladder
        #: loads, ``_ensure_selection`` intersects these with it instead of the
        #: default rule. Empty in the normal (non-restored) start.
        self._pending_selections: dict[str, list[date]] = {}
        self._snapshots: dict[str, ChainSnapshot] = {}
        self._forwards: dict[str, dict[date, ImpliedForward]] = {}
        #: Joint borrow/de-Am fixed-point reads (R2 item 11 increment 2),
        #: cached per (ticker, expiry) — the solve runs a de-Am per iteration,
        #: too heavy to repeat per prepared-quotes call. Lives and dies with
        #: ``_forwards`` (same chain + market-settings inputs); values may be
        #: None (the solve declined: thin/zero-carry/unsupported dividends).
        self._joint_carry: dict[str, dict[date, object]] = {}
        self._fit_settings = FitSettings()
        self._settings_version = 0  # bumped on change; part of fit-cache keys
        #: Global meta / UX settings + engine defaults (the Options workspace).
        self._options = OptionsSettings()
        self._options_version = 0  # bumped only when a fit-affecting field changes
        #: Observation-filter overlay version (Note 15): bumped whenever ANY
        #: filter knob changes so the overlay payload refreshes, WITHOUT busting
        #: fit caches (only active-mode changes touch _options_version).
        self._filter_version = 0
        #: Per-node observation-filter states (Note 15 Phase 3), keyed
        #: (ticker, iso, fit_mode) -> api.observation_filter.NodeFilter. Wiped
        #: with the chain caches (source/as-of switch = the strict reset) but
        #: SURVIVES recalibrate (a refetch is a new observation, not a reset)
        #: and transient as-of round-trips (_CHAIN_CACHE_ATTRS).
        self._filter_states: dict[tuple, object] = {}
        #: Restore the user's saved Fit/Options defaults (the Options "Save as
        #: default" button) when a store is configured; code defaults otherwise.
        saved_fit, saved_options = load_defaults(self.store_path)
        if saved_fit is not None:
            self._fit_settings = saved_fit
        if saved_options is not None:
            self._options = saved_options
        elif self._gated:
            # The trigger-gated live server defaults autoCalibrate OFF so a Fetch
            # only loads quotes and fitting waits for the explicit Calibrate button
            # (no saved preference yet — a user "Save as default" still wins above).
            self._options = self._options.model_copy(update={"autoCalibrate": False})
        #: Persisted per-edge graph overrides (plan Phase 7): weight + per-handle
        #: beta per directed edge. Empty ⇒ the production solve uses the auto-lattice.
        #: Restored from the store; the Graph edge editor PUTs replacements.
        self._graph_edges: list[GraphEdgeInput] = _coerce_graph_edges(
            load_graph_edges(self.store_path)
        )
        #: Persisted ticker-block rule (the sparse block-matrix editor). Stored
        #: VERBATIM so it round-trips exactly as written; its EXPANSION is what
        #: lives in _graph_edges. None ⇒ no rule (the edge list, if any, is raw).
        self._graph_block_rule: GraphBlockRule | None = _coerce_block_rule(
            load_graph_block_rule(self.store_path)
        )
        #: Persisted precision-message edge rules (message arc P3, schema v2 —
        #: source=informer/target=receiver). Its OWN blob: the legacy edge list
        #: above is never reinterpreted (spec §18.5). Empty ⇒ auto relations.
        #: Since U6 this workspace field holds the ACTIVE config's rows (the
        #: solve's read path; workspace docs replay it byte-identically).
        self._graph_message_edges: list[GraphMessageEdge] = _coerce_message_edges(
            load_graph_message_edges(self.store_path)
        )
        #: U6 draft/active config lifecycle (app-level, NOT workspace-scoped):
        #: {"draft": envelope|None, "active": envelope|None}. At boot the blob
        #: is authoritative for the active rows; a legacy-only store migrates
        #: into an initial v1 active + clean draft.
        self._graph_message_config: dict[str, GraphMessageConfigEnvelope | None] = (
            _coerce_message_config(load_graph_message_config(self.store_path))
        )
        if self._graph_message_config["active"] is not None:
            self._graph_message_edges = list(
                self._graph_message_config["active"].rows
            )
        elif self._graph_message_edges:
            migrated = GraphMessageConfigEnvelope(
                name="default",
                version=1,
                createdAt=_config_now(),
                author="desk",
                parentVersion=None,
                notes="migrated from graph_message_edges",
                rows=list(self._graph_message_edges),
            )
            self._graph_message_config = {
                "draft": migrated.model_copy(deep=True),
                "active": migrated,
            }
            save_graph_message_config(
                self.store_path, _config_blob(self._graph_message_config)
            )
        #: Trailing per-ticker ATM-innovation record feeding the idio band floor
        #: (volfit.graph.idio): every production solve records its lit-node
        #: innovations here, and a node that later goes dark gets its credible
        #: band floored from the days it was lit. Persisted best-effort.
        self._graph_idio: IdioHistory = IdioHistory.from_blob(
            load_graph_idio(self.store_path)
        )
        #: In-memory tail of the append-only audit log (governance kernel, R1
        #: item 8); the durable log lives in the store's `events` table.
        self._event_tail: deque = deque(maxlen=200)
        self._market_settings: dict[str, MarketSettings] = {}
        #: Per-ticker event calendar (shared across workspaces). Events now drive
        #: the event-weighted variance clock used by every fit (volfit.calib.
        #: weighted_time), so a calendar change must refit: the events version is
        #: folded into the fit-cache key.
        self._events: dict[str, list[EventSpec]] = {}
        #: PER-TICKER version counters (ROADMAP perf #3): the event calendar, market
        #: settings and forward policy are per-ticker concepts, so one ticker's edit
        #: must not invalidate every other ticker's warm fits. Keyed by ticker.
        self._events_version: dict[str, int] = {}  # bumped on a ticker's calendar change
        self._forward_policies: dict[tuple[str, str], ForwardPolicy] = {}
        self._forwards_version: dict[str, int] = {}  # bumped on a ticker's fwd change
        #: Per-ticker hypothetical/live spot SHIFT (proportional return vs the
        #: spot the fits were calibrated at, ``_anchor_spot``). Drives the fast
        #: no-recal spot-move transport (volfit.dynamics.transport): the
        #: calibrated anchor smile/surface/LV-grid is transported analytically,
        #: never refitted. NOT in the fit-cache key (the anchor fit stays warm and
        #: is transported on top). Two counters (ROADMAP perf #3C): the GLOBAL
        #: ``_spot_version`` is the client refresh signal surfaced in the status
        #: payload (a spot moved somewhere → re-pull the mounted views); the
        #: PER-TICKER ``_spot_version_by_ticker`` keys the DERIVED grid caches
        #: (localvol extraction) so a SPOT move on one name does not bust every
        #: other name's transported grid.
        self._spot_shift: dict[str, float] = {}
        self._spot_version = 0
        self._spot_version_by_ticker: dict[str, int] = {}
        #: Per-ticker market-DATA version: bumped when a fresh options chain is
        #: fetched ("Fetch Options Quotes" / the scheduler). Folded into the fit
        #: key so a refetch marks every node stale (and auto-calibration refits).
        self._data_version: dict[str, int] = {}
        #: Per-(ticker, ISO, mode) CALIBRATED pointer: the fit-key + spot a node
        #: was last *calibrated* at. With autoCalibrate OFF the displayed fit is
        #: frozen at this pointer (stale when the current key drifts) until an
        #: explicit Calibrate; with it ON the node re-fits on any input change.
        self._calibrated: dict[tuple[str, str, str], tuple[tuple, float]] = {}
        #: Monotonic CALIBRATION EPOCH: bumped whenever an already-calibrated
        #: node's displayed fit actually changes (a genuine re-calibration moves
        #: its calibrated key). The frontend polls this and refetches every mounted
        #: view the moment it advances — a level-triggered sync that is robust to
        #: missed running->idle edges, fast single-node jobs, and background /
        #: scheduler calibrations, regardless of which view is currently open.
        self._calib_epoch = 0
        #: The fit target ("mid" | "bidask" | "haircut") the user is currently
        #: VIEWING — recorded on every smile fetch. The calibrated pointer is keyed
        #: per (ticker, ISO, mode), so a Calibrate must re-point the SAME mode the
        #: smile is shown in; this lets every calibration path (the button, the
        #: scheduler, a bare POST) default to the mode actually on screen instead
        #: of always "mid" (which left a bid-ask / haircut smile frozen forever).
        self._last_fit_mode = "mid"
        #: Per-ticker spot the node fits were calibrated at — the spot-move
        #: transport anchors here (NOT the live snapshot spot, which a refetch
        #: moves while the calibration stays frozen).
        self._anchor_spot: dict[str, float] = {}
        #: Per-ticker CALIBRATED affine (Local-Vol) surface pointer: the affine
        #: cache key the surface was last calibrated at. Same freeze/stale model
        #: as the parametric nodes — autoCalibrate OFF keeps the LV surface frozen
        #: until an explicit Calibrate.
        self._affine_calibrated: dict[str, tuple] = {}
        self._fits: dict[tuple, FitRecord] = {}
        #: Version-keyed cache of prepared (de-Americanized, inverted) quotes per
        #: node — the de-Am binomial inversion is the cost here. Shares the exact
        #: lifecycle of ``_fits`` (cleared on source/as-of switch, per-ticker
        #: evicted on recalibrate), so it never outlives the fits it feeds. Value
        #: type is volfit.api.quotes.PreparedQuotes (annotated loosely to avoid an
        #: import cycle).
        self._prepared: dict[tuple, object] = {}
        self._priors: dict[tuple[str, str], PriorRecord] = {}
        #: Latest full prior SURFACE snapshot per ticker (the prior framework).
        #: DB-backed (VolStore.prior_snapshots, history kept); this is the warm
        #: in-memory cache of the most recently saved one per ticker.
        self._prior_snapshots: dict[str, "PriorSurfaceSnapshot"] = {}
        #: The ACTIVE fetched prior per ticker (the freshness-ladder result of
        #: "Fetch priors"): the snapshot the dotted spot-updated overlay draws and
        #: the calibration anchor pulls toward. Deliberately NOT cleared by
        #: ``_clear_chain_caches`` — fetching itself toggles the as-of, and the
        #: active prior must survive that.
        self._active_prior: dict[str, "PriorSurfaceSnapshot"] = {}
        #: The freshness-ladder source each active prior came from
        #: ("saved" | "15min" | "close"), for the Fetch status display.
        self._active_prior_source: dict[str, str] = {}
        #: Per-ticker active-prior version, bumped whenever the active prior changes
        #: (Fetch). Folded into the fit / affine cache keys so a fetched prior
        #: re-anchors the calibration instead of serving a stale cached fit.
        self._active_prior_version: dict[str, int] = {}
        self._sessions: dict[tuple[str, str], EditSession] = {}
        #: Per-node variance-swap quote sessions (one var-swap per node, shared
        #: by the Parametric and Local-Vol fits; separate undo/redo history).
        self._varswap_sessions: dict[tuple[str, str], VarSwapSession] = {}
        #: Explicitly darkened (ticker, ISO) nodes; every node is LIT by default.
        #: Lit = an observed source for the graph solver, dark = extrapolated.
        self._dark_nodes: set[tuple[str, str]] = set()
        self._universe = None  # volfit.graph.smile_universe.SmileUniverse
        #: Calibration signature the cached universe was built against
        #: (see calib_signature); None forces the next ensure_universe build.
        self._universe_sig = None
        #: Background calibration job manager (the global "Calibrate" action and
        #: the scheduler's auto-calibrate both run through this).
        from volfit.api.jobs import CalibrationJobs

        self.calibration_jobs = CalibrationJobs()
        #: Fine-grained engine-activity reporter (volfit.api.activity): what the
        #: compute engine is doing right now (fetch / de-am / calibrate / term /
        #: density / LV surface), narrated to the bottom status bar. Thread-safe;
        #: pushed at coarse boundaries only so it never slows a fit.
        from volfit.api.activity import ActivityReporter

        self.activity = ActivityReporter()
        #: Timed-fetch scheduler (volfit.api.scheduler); attached by create_app,
        #: None when AppState is built directly (tests / offline scripts).
        self.scheduler = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ data sources
    @property
    def provider(self) -> OptionChainProvider:
        """The currently active market-data provider."""
        return self._providers[self._active_source]

    @property
    def active_source(self) -> str:
        """Id of the active data source (e.g. "yahoo", "bloomberg")."""
        return self._active_source

    def source_ids(self) -> list[str]:
        """All configured data-source ids, in registration order."""
        return list(self._providers)

    def source_statuses(self, refresh: bool = False) -> dict[str, tuple[str, str]]:
        """Per-source (level, detail) feed status, cached with a short TTL."""
        from volfit.api.datasource import probe_statuses

        if refresh:
            self._status_cache.clear()
        return probe_statuses(self._providers, self._status_cache)

    def set_active_source(self, source_id: str) -> str:
        """Switch the active source: keep the watchlist + custom expiry picks,
        clear all data caches, and refetch on the new feed (auto selections
        re-resolve lazily; custom picks intersect the new available list)."""
        if source_id not in self._providers:
            raise UnknownNodeError(f"unknown data source {source_id!r}")
        with self._lock:
            if source_id == self._active_source:
                return self._active_source
            # Preserve custom expiry picks but re-resolve them LAZILY on the new feed:
            # stash them in _pending_selections so each ticker re-probes its available
            # ladder on first access (_ensure_selection), intersecting the picks with
            # the new source's listing. The switch returns instantly instead of blocking
            # on a synchronous per-ticker available_expiries fetch (seconds each on a
            # paginated feed like Massive); auto tickers re-resolve to their default.
            for t, mode in self._selection_mode.items():
                if mode == "custom" and t in self._selected:
                    self._pending_selections[t] = list(self._selected[t])
            self._active_source = source_id
            self._asof = AsOfSelection()  # a new feed starts live
            self._available.clear()
            self._selected.clear()
            self._selection_mode.clear()
            self._clear_chain_caches()
        return self._active_source

    def _clear_chain_caches(self) -> None:
        """Drop per-ticker chain-derived caches (call under the lock). Keeps the
        watchlist + expiry selection; used on source switch and as-of change."""
        self._snapshots.clear()
        self._forwards.clear()
        self._fits.clear()
        self._prepared.clear()
        self._calibrated.clear()
        self._anchor_spot.clear()
        self._affine_calibrated.clear()
        self._sessions.clear()
        self._varswap_sessions.clear()
        self._filter_states.clear()  # source/as-of switch = the filter's strict reset
        self._universe = None

    #: Cache dicts that ``_clear_chain_caches`` wipes — the live surface state a
    #: transient as-of switch must NOT destroy (see capture/restore below).
    _CHAIN_CACHE_ATTRS = (
        "_snapshots", "_forwards", "_fits", "_calibrated", "_anchor_spot",
        "_affine_calibrated", "_sessions", "_varswap_sessions", "_filter_states",
    )

    # ------------------------------------------- observation filter (Note 15)
    def filter_node(self, key: tuple):
        """The stored per-node filter holder, or None (Note 15 Phase 3)."""
        with self._lock:
            return self._filter_states.get(key)

    def set_filter_node(self, key: tuple, holder) -> None:
        with self._lock:
            self._filter_states[key] = holder

    def capture_chain_state(self) -> dict:
        """Snapshot the live as-of + chain-derived caches so a TRANSIENT as-of
        switch (e.g. the on-the-fly prior fetch, which recalibrates at a past
        close then restores live) can be made transparent. Without this the
        restore's cache-clear would wipe the live surface in the gated workflow,
        where reads no longer lazily re-bootstrap. Restore via
        ``restore_chain_state``."""
        with self._lock:
            saved = {attr: dict(getattr(self, attr)) for attr in self._CHAIN_CACHE_ATTRS}
            saved["_asof"] = self._asof
            return saved

    def restore_chain_state(self, saved: dict) -> None:
        """Restore the live as-of + caches captured by ``capture_chain_state``,
        leaving the live surface exactly as it was before the as-of round-trip."""
        with self._lock:
            for attr in self._CHAIN_CACHE_ATTRS:
                setattr(self, attr, dict(saved[attr]))
            self._asof = saved["_asof"]
            self._universe = None

    # -------------------------------------------------------------- workspace
    def workspace_doc(self) -> dict:
        """Serialize the user-authored workspace (R1 item 9) to a JSON-safe
        dict — settings, sessions, priors, policies, filter states, graph
        overrides, spot shifts, as-of and the universe's tickers + picks."""
        return build_doc(self)

    def restore_workspace(self, doc: dict) -> None:
        """Install a serialized workspace: replaces the whole scoped state,
        drops every chain-derived / per-ticker derived cache and advances all
        version counters, so nothing warm can serve a pre-restore fit. The
        universe restores lazily (no network); fits recalibrate on demand."""
        restore_doc(self, doc)

    # ------------------------------------------------------------ as-of
    @property
    def as_of(self) -> AsOfSelection:
        """The active global as-of selection."""
        return self._asof

    def set_as_of(self, selection: AsOfSelection) -> AsOfSelection:
        """Set the as-of point; validate against the active provider, then drop
        chain caches so the whole stack re-prices on the new observation."""
        if selection.mode not in ("live", "prev_close", "eod", "captured", "intraday"):
            raise UnknownNodeError(f"unknown as-of mode {selection.mode!r}")
        if selection.mode in ("prev_close", "eod"):
            if selection.mode not in self.provider.historical_modes():
                raise UnknownNodeError(
                    f"{self._active_source!r} has no {selection.mode!r} history"
                )
            if selection.mode == "eod" and selection.on is None:
                raise UnknownNodeError("eod as-of requires a date")
        if selection.mode == "captured" and selection.ts is None:
            raise UnknownNodeError("captured as-of requires a timestamp")
        if selection.mode == "intraday":
            if not self.provider.intraday_capable():
                raise UnknownNodeError(
                    f"{self._active_source!r} cannot serve an intraday instant"
                )
            if selection.ts is None:
                raise UnknownNodeError("intraday as-of requires a timestamp")
        with self._lock:
            if selection != self._asof:
                self._asof = selection
                self._clear_chain_caches()
            return self._asof

    def _fetch_asof(self, ticker: str, chosen: list[date]) -> ChainSnapshot:
        """Fetch a chain for the current as-of: live (+capture) / provider EOD /
        captured replay from the store."""
        sel = self._asof
        # Tell a flat-file-backed provider the ACTIVE universe (not just its static
        # watchlist) so the day's flat-file cache co-caches every active ticker —
        # else a name added in the Universe tab is filtered out and shows 0 expiries.
        hint = getattr(self.provider, "set_flat_universe", None)
        if hint is not None:
            try:
                hint(self.active_tickers())
            except Exception:  # noqa: BLE001 — never block a fetch on the hint
                pass
        if sel.mode == "captured":
            snap = self._load_captured(ticker, sel.ts)
            if snap is None:
                raise UnknownNodeError(
                    f"no captured snapshot for {ticker!r} at {sel.ts}"
                )
            return snap
        if sel.mode in ("prev_close", "eod"):
            return self.provider.fetch_chain(
                ticker, chosen, as_of=AsOf(mode=sel.mode, on=sel.on)
            )
        if sel.mode == "intraday":
            return self.provider.fetch_chain(
                ticker, chosen, as_of=AsOf(mode="intraday", ts=sel.ts)
            )
        snap = self.provider.fetch_chain(ticker, chosen)  # live
        self._persist_capture(snap)
        return snap

    def _load_captured(self, ticker: str, ts: datetime | None) -> ChainSnapshot | None:
        if self.store_path is None or ts is None:
            return None
        with VolStore(self.store_path) as store:
            return store.snapshot_at(ticker, ts)

    def _persist_capture(self, snap: ChainSnapshot) -> None:
        """Best-effort: save a live chain to the store for later replay, deduped
        to one capture per ~60 s per ticker. Never fails a fetch. Skipped for
        sources with their own history channel (Massive flat files / Bloomberg
        Terminal) — see ``NO_AUTO_CAPTURE_SOURCES``."""
        if self.store_path is None or self._active_source in NO_AUTO_CAPTURE_SOURCES:
            return
        try:
            with VolStore(self.store_path) as store:
                last = store.last_snapshot_ts(snap.ticker)
                if last is not None and abs((snap.timestamp - last).total_seconds()) < 60:
                    return
                store.save_snapshot(snap)
        except Exception:
            pass

    # ------------------------------------------------------------ market data
    def _empty_snapshot(self, ticker: str) -> ChainSnapshot:
        """An empty, never-cached snapshot for a transient feed miss (unresolved
        ladder or a failed/throttled provider fetch) — callers retry next time."""
        return ChainSnapshot(
            ticker=ticker,
            spot=0.0,
            timestamp=datetime.combine(self.reference_date, datetime.min.time()),
            quotes=[],
        )

    def snapshot(self, ticker: str) -> ChainSnapshot:
        """Chain snapshot of the ticker's SELECTED expiries (cached once);
        UnknownNodeError for tickers not in the active universe.

        In the trigger-gated workflow (``_gated``) a READ never pulls quotes: if
        nothing has been fetched yet this returns an empty, uncached snapshot, so
        opening the app / selecting the universe never touches the feed. The
        explicit Fetch (``refresh_chain``) and Calibrate (``ensure_chain``) paths
        do the actual provider fetch. Ungated keeps the historical lazy fetch."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            if ticker in self._snapshots:
                return self._snapshots[ticker]
        if self._gated:
            return self._empty_snapshot(ticker)  # reads never fetch (trigger-gated)
        return self._fetch_and_cache(ticker)

    def ensure_chain(self, ticker: str) -> ChainSnapshot:
        """Return the cached chain, fetching it once if absent — the Calibrate
        auto-fetch path ("press Calibrate before Fetch" still works). Always
        permitted to hit the feed, even in the gated workflow."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            if ticker in self._snapshots:
                return self._snapshots[ticker]
        return self._fetch_and_cache(ticker)

    def _fetch_and_cache(self, ticker: str) -> ChainSnapshot:
        """Pull the chain from the active provider for the SELECTED expiries and
        cache it (the explicit-fetch path). Degrades a feed failure / empty chain
        to an empty UNCACHED snapshot (retried on the next access), never a 500."""
        with self._lock:
            chosen = list(self._selected.get(ticker, []))
        if not chosen:
            # Ladder hasn't resolved yet (transient feed miss): return an empty,
            # uncached snapshot so the next access re-probes the provider rather
            # than freezing a zero-expiry node for the whole process.
            return self._empty_snapshot(ticker)
        try:
            snap = self._fetch_asof(ticker, chosen)  # outside lock (network)
        except UnknownNodeError:
            raise  # genuine 404 (e.g. captured replay with no stored snapshot)
        except Exception:
            # The active provider could not return a chain — down, throttled, or
            # at its daily cap (Bloomberg "daily capacity reached") even though it
            # listed the ladder. Treat it as a transient miss exactly like an
            # unresolved ladder: return an empty, UNCACHED snapshot so /universe
            # and every downstream view degrade to "no data" instead of a 500,
            # and the next access re-probes once the feed recovers.
            return self._empty_snapshot(ticker)
        with self._lock:
            # Never freeze an empty result: an unresolved ladder (transient feed
            # miss) or a chain that came back with no quotes must be retried on
            # the next access, not cached for the life of the process.
            if not snap.quotes:
                return snap
            self._snapshots.setdefault(ticker, snap)
            return self._snapshots[ticker]

    def has_quotes(self, ticker: str) -> bool:
        """Whether a non-empty chain has been fetched + cached for the ticker
        (so views can show 'press Fetch' vs the quotes without fetching)."""
        with self._lock:
            snap = self._snapshots.get(ticker)
        return snap is not None and bool(snap.quotes)

    def loaded_snapshot(self, ticker: str) -> ChainSnapshot | None:
        """The cached chain if one has been fetched, else None — NEVER fetches.
        Status/staleness reads (volfit.api.data_age) use this so polling the
        data-age of the universe stays feed-free."""
        with self._lock:
            return self._snapshots.get(ticker)

    def forwards(self, ticker: str) -> dict[date, ImpliedForward]:
        """Parity-implied forwards per expiry, cached per ticker."""
        snapshot = self.snapshot(ticker)
        with self._lock:
            cached = self._forwards.get(ticker)
            if cached:
                return cached
            # Pass the reference date so American chains are de-biased and the parity
            # discount is clamped to a physical rate band (robust to noisy/stale wings;
            # see data.forwards).
            fwds = implied_forwards(snapshot, self.reference_date)
            # Don't cache an empty result (unresolved ladder / empty chain): a
            # transient feed miss must be retried on the next access, not frozen.
            if fwds:
                self._forwards[ticker] = fwds
            return fwds

    def resolve_expiry(self, ticker: str, expiry_iso: str) -> date:
        """Parse and validate an ISO expiry against the ticker's SELECTED ladder.

        Validated against the selection (cheap metadata, what the universe lists),
        not the parity-implied forwards: in the gated workflow no chain is fetched
        on a read, so forwards is empty until the explicit Fetch, yet a selected
        node must still resolve (to show quotes / 'no fit yet'). The selection is a
        superset of the forward-bearing expiries, so valid nodes are unaffected and
        a genuinely unknown date is still rejected."""
        try:
            expiry = date.fromisoformat(expiry_iso)
        except ValueError:
            raise UnknownNodeError(f"malformed expiry {expiry_iso!r}") from None
        if expiry not in self.selected_expiries(ticker):
            raise UnknownNodeError(f"unknown expiry {expiry_iso!r} for {ticker!r}")
        return expiry

    def year_fraction(self, expiry: date) -> float:
        """t = days to expiry / 365 (matches the provider's expiry ladder)."""
        return (expiry - self.reference_date).days / DAYS_PER_YEAR

    # ---------------------------------------------------------- fit settings
    @property
    def settings_version(self) -> int:
        """Monotone counter folded into fit keys; bumps on settings change."""
        with self._lock:
            return self._settings_version

    def fit_settings(self) -> FitSettings:
        with self._lock:
            return self._fit_settings

    def set_fit_settings(self, settings: FitSettings) -> FitSettings:
        """Apply new hyperparameters; identical settings don't bump the
        version, so a redundant PUT never invalidates warm fit caches."""
        with self._lock:
            old = self._fit_settings
            if settings != self._fit_settings:
                self._fit_settings = settings
                self._settings_version += 1
        if settings != old:
            self.log_event("fit_settings", payload=_dump_diff(old, settings))
        return self.fit_settings()

    # ------------------------------------------------ real-time streaming (WS)
    def sync_streaming(self) -> None:
        """Start/stop/resubscribe each provider's real-time stream to match the
        active source, spot mode AND the current universe. Idempotent and cheap (a
        no-op once in the right state, thanks to the provider's contract-listing
        cache), so the scheduler can call it every tick. A provider streams iff it
        is the active source, exposes ``start_streaming`` (Massive), and spotMode is
        ``realtime``; any other streaming provider (e.g. after a source switch) is
        stopped so it does not leak a background socket. When the desired contract
        set changes (a ticker added/removed or its expiry selection edited) the
        stream is restarted on the new subscription (``start_streaming`` tears the
        old one down first)."""
        with self._lock:
            active, mode = self._active_source, self._options.spotMode
            auto = self._options.autoStream
            providers = dict(self._providers)
        for sid, prov in providers.items():
            if not hasattr(prov, "start_streaming"):
                continue
            streaming = prov.is_streaming()
            # Stream the active source's WS book when spotMode is realtime (live
            # re-pricing) OR autoStream is on (just feed fast Fetch/Calibrate from the
            # book; re-pricing/refit stay gated on realtime in the scheduler).
            want = sid == active and (mode == "realtime" or auto)
            if not want:
                if streaming:
                    prov.stop_streaming()  # source/mode no longer wants it
                continue
            desired = self._desired_stream_contracts(prov)
            if not desired:
                continue  # nothing fittable yet; leave any warm stream as-is
            if not streaming:
                prov.start_streaming(desired)
            else:
                # Resubscribe only if the provider can report its current
                # subscription (else we can't diff and must not thrash-restart).
                probe = getattr(prov, "streaming_contracts", None)
                if probe is not None and set(desired) != set(probe()):
                    prov.start_streaming(desired)  # universe changed -> resubscribe

    def _desired_stream_contracts(self, prov) -> list[str]:
        """The option tickers the active universe wants streamed (cheap once the
        provider's contract listing is cached). A bad ticker never blocks the rest."""
        contracts: list[str] = []
        for ticker in self.active_tickers():
            try:
                contracts += prov.option_tickers(ticker, self.selected_expiries(ticker))
            except Exception:  # noqa: BLE001 — a bad ticker never blocks streaming
                continue
        return contracts

    def is_streaming(self) -> bool:
        """Whether the active provider currently has a live real-time book (used by
        the scheduler's throttled refit branch)."""
        prov = self.provider
        probe = getattr(prov, "is_streaming", None)
        return bool(probe is not None and probe())

    # ----------------------------------------------------- options (meta) settings
    @property
    def options_version(self) -> int:
        """Monotone counter folded into fit keys; bumps only when a
        fit-affecting Options field (calendarWeight) changes, so toggling a
        pure-UI option (spot mode, auto-calibrate) never busts warm fits."""
        with self._lock:
            return self._options_version

    def options(self) -> OptionsSettings:
        with self._lock:
            return self._options

    @property
    def filter_version(self) -> int:
        """Observation-filter overlay version (Note 15): keys the filter overlay
        payload so a knob tweak refreshes the view without invalidating fits."""
        with self._lock:
            return self._filter_version

    def set_options(self, options: OptionsSettings) -> OptionsSettings:
        """Apply new meta settings. Calibration-affecting fields bump the options
        version (``calendarWeight``, the var-swap penalty knobs ``varSwapEnabled``
        / ``varSwapWeightPct``, the event clock, the calendar-coupling switch
        ``enforceCalendar`` and the prior-anchor knobs ``autoLoadPrior`` /
        ``priorAnchorWeightPct``); the rest are global defaults / display toggles
        read live and need no cache invalidation."""
        with self._lock:
            _audit_old = self._options
            if options != self._options:
                # Observation filter (Note 15): overlay-mode knobs must NOT bust
                # the fit cache (the filter only reads fits in overlay), so filter
                # fields join affects_fit only when the active-MAP fit changes —
                # an off/overlay <-> active transition, or any knob while active.
                _filter_knobs = (
                    "filterCovarianceMode",
                    "filterProcessVolBpSqrtDay",
                    "filterProcessSkewSqrtDay",
                    "filterProcessCurvSqrtDay",
                    "filterTransportNoiseScale",
                    "filterResidualInflation",
                    "filterAdaptiveSigma",
                    "filterMaxGain",
                    "filterResetHours",
                    "filterDataOnlyPrepass",
                )
                filter_changed = options.observationFilterMode != (
                    self._options.observationFilterMode
                ) or any(
                    getattr(options, f) != getattr(self._options, f)
                    for f in _filter_knobs
                )
                was_active = self._options.observationFilterMode == "active"
                is_active = options.observationFilterMode == "active"
                filter_affects_fit = (was_active != is_active) or (
                    is_active and filter_changed
                )
                if filter_changed:
                    self._filter_version += 1
                affects_fit = (
                    filter_affects_fit
                    or options.calendarWeight != self._options.calendarWeight
                    or options.varSwapEnabled != self._options.varSwapEnabled
                    or options.varSwapWeightPct != self._options.varSwapWeightPct
                    or options.eventsEnabled != self._options.eventsEnabled
                    or options.normalizeEvents != self._options.normalizeEvents
                    # 0DTE research clock (R2 item 10): the toggle and both
                    # profile knobs change every node's (t, tau), so they bust
                    # the fit cache like the event-clock switches above.
                    or options.intradayClock != self._options.intradayClock
                    or options.sessionVarShare != self._options.sessionVarShare
                    or options.nonTradingWeight != self._options.nonTradingWeight
                    or options.enforceCalendar != self._options.enforceCalendar
                    # Symmetric-surface solver switch: changes how the coupled
                    # surface fit treats the calendar constraint end to end.
                    or options.surfaceSolver != self._options.surfaceSolver
                    or options.autoLoadPrior != self._options.autoLoadPrior
                    or options.priorAnchorWeightPct != self._options.priorAnchorWeightPct
                    or options.priorAnchorDeltas != self._options.priorAnchorDeltas
                    # prior-persistence mode + operator/factor/tail knobs (the
                    # 7-mode menu; Docs/prior_persistence_roadmap.md) — all change
                    # calibration output once wired, so they bust the fit cache.
                    or options.priorPersistenceMode != self._options.priorPersistenceMode
                    or options.priorOperatorSet != self._options.priorOperatorSet
                    or options.priorOperatorStrengthPct
                    != self._options.priorOperatorStrengthPct
                    or options.priorOperatorRequiredPrecision
                    != self._options.priorOperatorRequiredPrecision
                    or options.priorOperatorGapExponent
                    != self._options.priorOperatorGapExponent
                    or options.priorOperatorBandwidth != self._options.priorOperatorBandwidth
                    or options.priorOperatorCovarianceMode
                    != self._options.priorOperatorCovarianceMode
                    or options.priorDataOnlyPrepass != self._options.priorDataOnlyPrepass
                    or options.collarSign != self._options.collarSign
                    or options.priorFactorSet != self._options.priorFactorSet
                    or options.priorFactorStrengthPct
                    != self._options.priorFactorStrengthPct
                    or options.priorTailAnchorStrengthPct
                    != self._options.priorTailAnchorStrengthPct
                    # SIV put-wing no-butterfly regularizer (R6) — changes the SIV
                    # overlay calibration, so it busts the fit cache.
                    or options.sivWingPenaltyPct != self._options.sivWingPenaltyPct
                    # Extrapolated-region tapered enforcement (Notes 09/10
                    # Phase 2) — changes the overlay calibration when on.
                    or options.extrapEnforce != self._options.extrapEnforce
                    # Joint borrow/de-Am carry (R2 item 11 increment 2) —
                    # changes the resolved forwards every fit consumes.
                    or options.jointCarry != self._options.jointCarry
                    or options.jointCarryEngageBp != self._options.jointCarryEngageBp
                )
                if affects_fit:
                    self._options_version += 1
                self._options = options
            current = self._options
        if current != _audit_old:
            self.log_event("options_settings", payload=_dump_diff(_audit_old, current))
        return current

    # -------------------------------------------- persisted settings defaults
    def store_enabled(self) -> bool:
        """Whether a persistence store is configured (VOLFIT_DB / -NoDb off)."""
        return self.store_path is not None

    def settings_defaults_saved(self) -> bool:
        """Whether the user has saved Fit/Options defaults to the store."""
        return has_defaults(self.store_path)

    def save_settings_defaults(self) -> bool:
        """Persist the CURRENT Fit + Options settings as the startup defaults
        (the Options "Save as default" button). No-op without a store."""
        with self._lock:
            fit, options = self._fit_settings, self._options
        return save_defaults(self.store_path, fit, options)

    def reset_settings_defaults(self) -> tuple[FitSettings, OptionsSettings]:
        """Drop any persisted defaults and revert the live Fit + Options settings
        to the built-in code defaults (the "Reset to defaults" button). Routed
        through set_*_settings so the fit/options versions bump and warm caches
        invalidate exactly as a manual edit would."""
        clear_defaults(self.store_path)
        fit = self.set_fit_settings(FitSettings())
        options = self.set_options(OptionsSettings())
        return fit, options

    def dynamics_regime(self) -> str | float:
        """The active vol-spot dynamics regime for spot-move transport.

        Reads OptionsSettings.dynamicsRegime; "custom" resolves to the numeric
        ``ssr`` so volfit.dynamics handles it as a custom skew-stickiness ratio.
        """
        with self._lock:
            options = self._options
        if options.dynamicsRegime == "custom":
            return float(options.ssr)
        return options.dynamicsRegime

    # ------------------------------------------------------------- spot shift
    @property
    def spot_version(self) -> int:
        """GLOBAL monotone counter bumped on any ticker's spot-shift change — the
        client refresh signal (surfaced in the status payload): a spot moved
        somewhere, re-pull the mounted views. Deliberately NOT in the slice
        fit-cache key — the anchor fit is transported on read, never re-fitted.
        Use ``spot_version_for(ticker)`` for the per-ticker derived-grid cache key."""
        with self._lock:
            return self._spot_version

    def spot_version_for(self, ticker: str) -> int:
        """PER-TICKER spot version folded into the derived-grid caches (localvol
        extraction) so one name's spot move re-transports only that name's grid,
        not every other ticker's (ROADMAP perf #3C)."""
        with self._lock:
            return self._spot_version_by_ticker.get(ticker, 0)

    def spot_shift(self, ticker: str) -> float:
        """The ticker's active spot shift (proportional return; 0 = anchored)."""
        with self._lock:
            return self._spot_shift.get(ticker, 0.0)

    def set_spot_shift(self, ticker: str, shift: float) -> float:
        """Set the ticker's hypothetical/live spot shift; bump the spot version
        only on a real change so a redundant set never busts derived caches."""
        with self._lock:
            if float(shift) != self._spot_shift.get(ticker, 0.0):
                self._spot_shift[ticker] = float(shift)
                self._spot_version += 1  # global client signal
                self._spot_version_by_ticker[ticker] = (
                    self._spot_version_by_ticker.get(ticker, 0) + 1  # per-ticker cache key
                )
            return self._spot_shift.get(ticker, 0.0)

    # --------------------------------------------------- data / calibration state
    def data_version(self, ticker: str) -> int:
        """The ticker's market-data version (bumps on a fresh options fetch)."""
        with self._lock:
            return self._data_version.get(ticker, 0)

    def bump_data_version(self, ticker: str) -> int:
        """Mark a ticker's option data as freshly fetched (every node goes stale)."""
        with self._lock:
            self._data_version[ticker] = self._data_version.get(ticker, 0) + 1
            return self._data_version[ticker]

    def refresh_chain(self, ticker: str) -> float:
        """Fetch a fresh options chain for a ticker ("Fetch Options Quotes").

        Drops the cached snapshot + forwards and bumps the data version (so every
        node goes stale / auto-refits), then re-fetches the chain (network) so the
        new quotes are warm for the next calibration. The calibrated pointers and
        spot shift are left untouched — the displayed fit stays frozen until an
        explicit Calibrate re-anchors it at the new chain's spot. Returns the new
        spot."""
        self._require_active(ticker)
        with self._lock:
            self._snapshots.pop(ticker, None)
            self._forwards.pop(ticker, None)
            self._joint_carry.pop(ticker, None)
            self._data_version[ticker] = self._data_version.get(ticker, 0) + 1
        # Force a provider fetch (in the gated workflow a plain read would not).
        return float(self._fetch_and_cache(ticker).spot)  # warm the new chain

    def get_calibrated_ptr(self, ticker: str, iso: str, mode: str) -> tuple | None:
        """The (fit-key, cal-spot) a node was last calibrated at, or None."""
        with self._lock:
            return self._calibrated.get((ticker, iso, mode))

    def set_calibrated_ptr(self, ticker: str, iso: str, mode: str, key: tuple, spot: float) -> None:
        """Record that a node is now calibrated at ``key`` (spot ``spot``).

        Bumps the global calibration epoch when this is a genuine RE-calibration
        that moves an already-calibrated node onto a new key — i.e. when the
        displayed (frozen) fit changes and other mounted views must refetch. A
        first-ever bootstrap (no prior pointer) or an identical re-point (same key,
        e.g. a cache-hit Calibrate that changes nothing, or an autoCalibrate-ON GET
        that re-fits to the same key) does NOT advance the epoch, so it never
        churns the frontend or risks a refetch loop."""
        with self._lock:
            prev = self._calibrated.get((ticker, iso, mode))
            self._calibrated[(ticker, iso, mode)] = (key, float(spot))
            self._anchor_spot[ticker] = float(spot)
            if prev is not None and prev[0] != key:
                self._calib_epoch += 1

    @property
    def calib_epoch(self) -> int:
        """Monotonic counter of node re-calibrations that changed a displayed fit."""
        with self._lock:
            return self._calib_epoch

    @property
    def calib_signature(self) -> tuple:
        """Cheap change-detector over the calibration state the graph sandbox
        universe is built from: (viewed fit mode, number of calibrated pointers,
        re-calibration epoch). A first-ever Calibrate grows the count (the epoch
        deliberately ignores bootstraps), a re-calibration bumps the epoch, and a
        fit-mode switch changes the mode — any of which must invalidate a cached
        universe, else the Graph tab serves fits that are no longer on screen
        (or an EMPTY universe cached before the first Calibrate, forever)."""
        with self._lock:
            return (self._last_fit_mode, len(self._calibrated), self._calib_epoch)

    @property
    def last_fit_mode(self) -> str:
        """The fit target the user is currently viewing (recorded on smile fetch)."""
        with self._lock:
            return self._last_fit_mode

    def note_fit_mode(self, fit_mode: str) -> None:
        """Record the fit target a smile was just fetched in, so calibration paths
        that aren't handed an explicit mode (the scheduler, a bare POST /calibrate)
        target the mode actually on screen rather than always defaulting to mid."""
        with self._lock:
            self._last_fit_mode = fit_mode

    def anchor_spot(self, ticker: str) -> float:
        """Spot the ticker's fits were calibrated at; the live snapshot spot when
        nothing has been calibrated yet (the spot-move transport anchors here)."""
        with self._lock:
            anchor = self._anchor_spot.get(ticker)
        return anchor if anchor is not None else float(self.snapshot(ticker).spot)

    def get_affine_ptr(self, ticker: str) -> tuple | None:
        """The affine cache key the ticker's LV surface was last calibrated at."""
        with self._lock:
            return self._affine_calibrated.get(ticker)

    def set_affine_ptr(self, ticker: str, key: tuple) -> None:
        """Record that the ticker's LV surface is now calibrated at ``key``."""
        with self._lock:
            self._affine_calibrated[ticker] = key

    def recalibrate(self, ticker: str) -> None:
        """Re-anchor a ticker: clear its hypothetical spot shift and drop its
        chain-derived caches so the next fit refetches the live snapshot and
        recalibrates at the current spot (the explicit "Calibrate" action)."""
        with self._lock:
            if self._spot_shift.pop(ticker, 0.0) != 0.0:
                self._spot_version += 1  # global client signal
                self._spot_version_by_ticker[ticker] = (
                    self._spot_version_by_ticker.get(ticker, 0) + 1  # per-ticker cache key
                )
            self._snapshots.pop(ticker, None)
            self._forwards.pop(ticker, None)
            self._joint_carry.pop(ticker, None)
            self._fits = {k: v for k, v in self._fits.items() if k[0] != ticker}
            self._prepared = {k: v for k, v in self._prepared.items() if k[0] != ticker}
            self._calibrated = {k: v for k, v in self._calibrated.items() if k[0] != ticker}
            self._anchor_spot.pop(ticker, None)
            self._affine_calibrated.pop(ticker, None)
            # Sessions (user quote/var-swap edits) are intentionally kept.
            cache = getattr(self, "_localvol_cache", None)
            if cache is not None:
                for key in [k for k in cache if k[0] == ticker]:
                    cache.pop(key, None)
            cache = getattr(self, "_affine_cache", None)
            if cache is not None:
                for key in [k for k in cache if k[0] == ticker]:
                    cache.pop(key, None)
            self._universe = None  # graph universe re-derives from fresh fits

    def live_spot(self, ticker: str) -> float:
        """Re-probe the active provider's current spot WITHOUT touching the
        cached snapshot (real-time spot polling). Falls back to the cached
        snapshot spot when the provider has no cheap spot probe."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            chosen = list(self._selected.get(ticker, []))
        try:
            return float(self.provider.spot(ticker, chosen))
        except Exception:
            return float(self.snapshot(ticker).spot)

    # ------------------------------------ market settings and forward policy
    def forwards_version(self, ticker: str) -> int:
        """Per-ticker monotone counter folded into the fit key; bumps when THIS
        ticker's market settings or forward policy change. Per-ticker so editing
        one name's rate/dividends/forward never refits the rest (ROADMAP perf #3)."""
        with self._lock:
            return self._forwards_version.get(ticker, 0)

    def market_settings(self, ticker: str) -> MarketSettings:
        """The ticker's rate/dividend settings (defaults when never set)."""
        with self._lock:
            return self._market_settings.get(ticker) or MarketSettings()

    def set_market_settings(self, ticker: str, settings: MarketSettings) -> MarketSettings:
        """Apply new market settings; identical settings don't bump the
        forwards version, so a redundant PUT never invalidates warm fits."""
        with self._lock:
            old = self._market_settings.get(ticker, MarketSettings())
            if settings != old:
                self._market_settings[ticker] = settings
                self._forwards_version[ticker] = self._forwards_version.get(ticker, 0) + 1
                # rate/dividends are joint-carry solve inputs (R2 item 11)
                self._joint_carry.pop(ticker, None)
        if settings != old:
            self.log_event("market_settings", scope=ticker,
                           payload=_dump_diff(old, settings))
        return self.market_settings(ticker)

    def forward_policy(self, ticker: str, expiry_iso: str) -> ForwardPolicy:
        """The node's forward policy ("parity" default when never set)."""
        with self._lock:
            return self._forward_policies.get((ticker, expiry_iso)) or ForwardPolicy()

    def set_forward_policy(
        self, ticker: str, expiry_iso: str, policy: ForwardPolicy
    ) -> ForwardPolicy:
        """Store one node's forward policy; UnknownNodeError on bad nodes
        (validated *before* storing), version bumped only on a real change."""
        iso = self.resolve_expiry(ticker, expiry_iso).isoformat()  # may raise
        with self._lock:
            old = self._forward_policies.get((ticker, iso), ForwardPolicy())
            if policy != old:
                self._forward_policies[(ticker, iso)] = policy
                self._forwards_version[ticker] = self._forwards_version.get(ticker, 0) + 1
        if policy != old:
            self.log_event("forward_policy", scope=f"{ticker}/{iso}",
                           payload=_dump_diff(old, policy))
        return self.forward_policy(ticker, iso)

    # ------------------------------------------------------ event calendar
    def events_version(self, ticker: str) -> int:
        """Per-ticker monotone counter folded into the fit key; bumps on THIS
        ticker's event-calendar change (events drive its variance clock). Per-ticker
        so one name's calendar edit never refits the rest (ROADMAP perf #3)."""
        with self._lock:
            return self._events_version.get(ticker, 0)

    def events(self, ticker: str) -> list[EventSpec]:
        """The ticker's persisted event calendar (empty when never set)."""
        with self._lock:
            return list(self._events.get(ticker, []))

    def set_events(self, ticker: str, events: list[EventSpec]) -> list[EventSpec]:
        """Replace the ticker's event calendar; bump the version only on a real
        change so a redundant PUT never invalidates warm fit caches."""
        with self._lock:
            if events != self._events.get(ticker, []):
                self._events[ticker] = list(events)
                self._events_version[ticker] = self._events_version.get(ticker, 0) + 1
            return list(self._events.get(ticker, []))

    def dividend_model(self, ticker: str) -> DividendModel:
        """The ticker's MarketSettings translated to a data-layer model."""
        settings = self.market_settings(ticker)
        return DividendModel(
            mode=settings.dividendMode,
            yield_=settings.dividendYield,
            dividends=tuple(
                Dividend(date.fromisoformat(d.exDate), d.amount)
                for d in settings.dividends
            ),
            switch_years=settings.switchYears,
        )

    def theoretical_forward_for(self, ticker: str, expiry: date) -> tuple[float, float]:
        """(forward, discount) from the dividend model and flat rate."""
        spot = self.snapshot(ticker).spot
        rate = self.market_settings(ticker).rate
        t = self.year_fraction(expiry)
        forward = theoretical_forward(
            spot, rate, t, self.dividend_model(ticker), self.reference_date
        )
        return forward, math.exp(-rate * t)

    def cash_dividend_schedule(self, ticker: str, expiry: date, forward: float):
        """Forward-consistent discrete CASH schedule for de-Americanizing the
        chain, or None to keep the continuous-yield de-Am (volfit.data.dividends).

        Returns ``(ex_times, scaled_amounts, rate)``: the discrete-dividend tree
        uses the ticker's physical ``rate`` and the schedule's ex-date timing,
        the amounts scaled so the escrowed forward reproduces ``forward`` — so
        the smile joins smoothly across a cash ex-date with no level shift.
        """
        rate = self.market_settings(ticker).rate
        schedule = forward_consistent_cash_schedule(
            self.snapshot(ticker).spot,
            forward,
            rate,
            self.year_fraction(expiry),
            self.dividend_model(ticker),
            self.reference_date,
        )
        if schedule is None:
            return None
        times, amounts = schedule
        return times, amounts, rate

    def joint_carry_read(self, ticker: str, expiry: date):
        """The cached joint borrow/de-Am fixed-point read for one expiry
        (R2 item 11) — a JointBorrowResult, or None when the solve declines
        (thin chain, zero-carry synth, unsupported dividend mix, no spot).

        Cached per (ticker, expiry) and invalidated with the forwards cache
        and on market-settings changes: the solve runs one de-Am pass per
        iteration, far too heavy to repeat on every prepared-quotes call."""
        with self._lock:
            per = self._joint_carry.setdefault(ticker, {})
            if expiry in per:
                return per[expiry]
        from volfit.data.carry_solve import dividend_legs, joint_borrow

        result = None
        try:
            settings = self.market_settings(ticker)
            legs = dividend_legs(settings, self.reference_date)
            if legs is not None:
                dividend_yield, div_times, div_amounts = legs
                result = joint_borrow(
                    self.snapshot(ticker), expiry, self.reference_date,
                    settings.rate, dividend_yield=dividend_yield,
                    div_times=div_times, div_amounts=div_amounts,
                )
        except Exception:  # noqa: BLE001 — a solve hiccup must not break fits
            result = None
        with self._lock:
            self._joint_carry.setdefault(ticker, {})[expiry] = result
        return result

    def resolved_forward(self, ticker: str, expiry: date) -> ResolvedForward:
        """The forward calibration uses for one expiry, per its policy.

        "parity" reads the regression (always present: the expiry universe
        is gated on parity fits, see resolve_expiry); "theoretical" prices
        the dividend model; "manual" takes the user's forward with the
        parity discount (falling back to exp(-rate t) defensively); with
        ``jointCarry`` ON, a MATERIAL joint borrow/de-Am read (R2 item 11:
        converged, |borrow| >= jointCarryEngageBp) overrides the parity
        route with source "joint" — below the threshold the parity forward
        is returned EXACTLY, so ordinary names stay byte-identical even
        with the toggle on."""
        policy = self.forward_policy(ticker, expiry.isoformat())
        parity = self.forwards(ticker).get(expiry)
        if policy.mode == "theoretical":
            forward, discount = self.theoretical_forward_for(ticker, expiry)
            return ResolvedForward(expiry, forward, discount, "theoretical")
        if policy.mode == "manual":
            if parity is not None:
                discount = parity.discount
            else:
                rate = self.market_settings(ticker).rate
                discount = math.exp(-rate * self.year_fraction(expiry))
            return ResolvedForward(expiry, float(policy.manualForward), discount, "manual")
        if parity is None:
            # Reachable when a node is selected past the parity gate (e.g. a
            # near-settle 0DTE chain whose two-sided pairs collapsed, or a
            # captured-replay ladder selected explicitly): a readable 404 for
            # the API, a calm named condition for harness callers — never an
            # AttributeError.
            raise UnknownNodeError(
                f"no parity forward for {ticker!r} {expiry.isoformat()} "
                "(too few two-sided pairs — thin or one-sided chain)"
            )
        opts = self.options()
        if opts.jointCarry:
            joint = self.joint_carry_read(ticker, expiry)
            if (
                joint is not None
                and joint.converged
                and abs(joint.borrow_bp) >= opts.jointCarryEngageBp
            ):
                return ResolvedForward(
                    expiry, joint.forward, joint.discount, "joint"
                )
        return ResolvedForward(expiry, parity.forward, parity.discount, "parity")

    # ------------------------------------------------------------- fit cache
    def get_fit(self, key: tuple) -> FitRecord | None:
        """Cached fit, keyed (ticker, ISO, mode, session-v, settings-v)."""
        with self._lock:
            return self._fits.get(key)

    def store_fit(self, key: tuple, record: FitRecord) -> None:
        with self._lock:
            self._fits[key] = record

    def get_prepared(self, key: tuple):
        """Cached PreparedQuotes for a node (version-keyed), or None."""
        with self._lock:
            return self._prepared.get(key)

    def store_prepared(self, key: tuple, prepared) -> None:
        with self._lock:
            self._prepared[key] = prepared

    # --------------------------------------------------------- edit sessions
    def session(self, key: tuple[str, str]) -> EditSession:
        """The node's edit session, created on first use (lock-guarded)."""
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = EditSession()
            return self._sessions[key]

    def session_if_exists(self, key: tuple[str, str]) -> EditSession | None:
        """The node's edit session if one was ever created, else None."""
        with self._lock:
            return self._sessions.get(key)

    # ------------------------------------------------- var-swap quote sessions
    def varswap_session(self, key: tuple[str, str]) -> VarSwapSession:
        """The node's var-swap session, created on first use (lock-guarded)."""
        with self._lock:
            if key not in self._varswap_sessions:
                self._varswap_sessions[key] = VarSwapSession()
            return self._varswap_sessions[key]

    def varswap_session_if_exists(self, key: tuple[str, str]) -> VarSwapSession | None:
        """The node's var-swap session if one was ever created, else None."""
        with self._lock:
            return self._varswap_sessions.get(key)

    # ----------------------------------------------------------------- priors
    def get_prior(self, key: tuple[str, str]) -> PriorRecord | None:
        with self._lock:
            return self._priors.get(key)

    def save_prior(self, key: tuple[str, str], record: PriorRecord) -> None:
        with self._lock:
            self._priors[key] = record

    # ----------------------------------------------- prior surface snapshots
    def save_prior_snapshot(self, snapshot: "PriorSurfaceSnapshot") -> bool:
        """Cache a ticker's latest prior snapshot and persist it (history kept).

        Returns whether it was persisted to a store (False = in-memory only, so it
        would not survive a restart). Persistence is best-effort and never raises."""
        from datetime import datetime

        with self._lock:
            self._prior_snapshots[snapshot.ticker] = snapshot
        if self.store_path is None:
            return False
        try:
            from volfit.data.store import VolStore

            with VolStore(self.store_path) as store:
                store.save_prior_snapshot(
                    snapshot.ticker,
                    datetime.fromisoformat(snapshot.dataTs),
                    datetime.fromisoformat(snapshot.savedTs),
                    snapshot.model_dump(),
                )
            return True
        except Exception as exc:  # noqa: BLE001 — persistence must never break a save
            warnings.warn(f"prior-snapshot persist failed: {exc}")
            return False

    def latest_prior_snapshot(self, ticker: str) -> "PriorSurfaceSnapshot | None":
        """The most recently saved prior snapshot for a ticker (cache, then store)."""
        with self._lock:
            cached = self._prior_snapshots.get(ticker)
        if cached is not None:
            return cached
        if self.store_path is None:
            return None
        try:
            from volfit.api.schemas_prior import PriorSurfaceSnapshot
            from volfit.data.store import VolStore

            with VolStore(self.store_path) as store:
                doc = store.latest_prior_snapshot(ticker)
        except Exception as exc:  # noqa: BLE001 — history is best-effort
            warnings.warn(f"prior-snapshot load failed: {exc}")
            return None
        if doc is None:
            return None
        snap = PriorSurfaceSnapshot.model_validate(doc)
        with self._lock:
            self._prior_snapshots.setdefault(ticker, snap)
        return snap

    def set_active_prior(
        self, ticker: str, snapshot: "PriorSurfaceSnapshot | None", source: str
    ) -> None:
        """Set (or clear) the active fetched prior for a ticker + its ladder source
        ("saved" | "15min" | "close" | "none")."""
        with self._lock:
            if snapshot is None:
                self._active_prior.pop(ticker, None)
            else:
                self._active_prior[ticker] = snapshot
            self._active_prior_source[ticker] = source
            self._active_prior_version[ticker] = self._active_prior_version.get(ticker, 0) + 1
        self.log_event(
            "prior_selection", scope=ticker,
            payload={"source": source, "cleared": snapshot is None},
        )

    def active_prior_version(self, ticker: str) -> int:
        """Per-ticker active-prior version (folded into fit / affine cache keys)."""
        with self._lock:
            return self._active_prior_version.get(ticker, 0)

    def active_prior(self, ticker: str) -> "PriorSurfaceSnapshot | None":
        """The active fetched prior for a ticker (the dotted overlay / anchor)."""
        with self._lock:
            return self._active_prior.get(ticker)

    def active_prior_source(self, ticker: str) -> str | None:
        """Which freshness-ladder branch the active prior came from, or None."""
        with self._lock:
            return self._active_prior_source.get(ticker)

    # ------------------------------------------------------------- lit / dark
    def node_lit(self, ticker: str, iso: str) -> bool:
        """Whether a node is lit (observed); lit by default, dark when darkened."""
        with self._lock:
            return (ticker, iso) not in self._dark_nodes

    def set_node_lit(self, ticker: str, iso: str, lit: bool) -> None:
        """Mark a node lit (observed source) or dark (extrapolation target)."""
        with self._lock:
            if lit:
                self._dark_nodes.discard((ticker, iso))
            else:
                self._dark_nodes.add((ticker, iso))

    # ------------------------------------------------------- graph edge overrides
    def graph_edges(self) -> list[GraphEdgeInput]:
        """The persisted per-edge graph overrides (empty ⇒ auto-lattice)."""
        with self._lock:
            return list(self._graph_edges)

    def set_graph_edges(self, edges: list[GraphEdgeInput]) -> None:
        """Replace the per-edge overrides and persist them (best-effort).

        Also DROPS any stored block rule: the raw editor hand-edits the list, so
        a rule kept alongside would misdescribe the topology it claims to expand
        to. The block editor goes through ``set_graph_block_rule`` instead."""
        with self._lock:
            self._graph_edges = list(edges)
            self._graph_block_rule = None
        save_graph_edges(self.store_path, [e.model_dump() for e in edges])
        save_graph_block_rule(self.store_path, None)
        self.log_event("graph_edges", payload={"nEdges": len(edges), "rule": None})

    def graph_block_rule(self) -> GraphBlockRule | None:
        """The persisted ticker-block rule (None ⇒ no rule stored)."""
        with self._lock:
            return self._graph_block_rule

    def set_graph_block_rule(
        self, rule: GraphBlockRule | None, edges: list[GraphEdgeInput]
    ) -> None:
        """Persist the block rule AND its expansion in ONE step, so /graph/edges
        immediately serves the expanded list. ``rule=None`` with ``edges=[]``
        clears both — back to the auto-lattice."""
        with self._lock:
            self._graph_block_rule = rule
            self._graph_edges = list(edges)
        save_graph_edges(self.store_path, [e.model_dump() for e in edges])
        save_graph_block_rule(
            self.store_path, rule.model_dump() if rule is not None else None
        )
        self.log_event(
            "graph_edges", payload={"nEdges": len(edges), "rule": rule is not None}
        )

    def graph_message_edges(self) -> list[GraphMessageEdge]:
        """The ACTIVE message-relation rows — what the solve uses (empty ⇒
        auto relations). Lives in the workspace so docs replay it."""
        with self._lock:
            return list(self._graph_message_edges)

    def set_graph_message_edges(self, edges: list[GraphMessageEdge]) -> None:
        """Replace the ACTIVE rows directly (workspace restore / legacy
        callers) and keep the U6 envelope's active slot in sync WITHOUT a
        version bump — a restore replays state, it does not activate."""
        with self._lock:
            self._graph_message_edges = list(edges)
            active = self._graph_message_config["active"]
            if active is not None:
                self._graph_message_config["active"] = active.model_copy(
                    update={"rows": list(edges)}
                )
        save_graph_message_edges(self.store_path, [e.model_dump() for e in edges])
        self._persist_message_config()
        self.log_event("graph_message_edges", payload={"nEdges": len(edges)})

    # ------------------------------------------- U6 message-config lifecycle
    def graph_message_config(
        self,
    ) -> tuple[GraphMessageConfigEnvelope | None, GraphMessageConfigEnvelope | None]:
        """The (draft, active) envelope pair (deep copies)."""
        with self._lock:
            d = self._graph_message_config["draft"]
            a = self._graph_message_config["active"]
            return (
                d.model_copy(deep=True) if d is not None else None,
                a.model_copy(deep=True) if a is not None else None,
            )

    def graph_message_draft_edges(self) -> list[GraphMessageEdge]:
        """The DRAFT rows (falling back to active — editing starts from what
        runs; empty ⇒ auto relations)."""
        with self._lock:
            d = self._graph_message_config["draft"]
            if d is not None:
                return list(d.rows)
            return list(self._graph_message_edges)

    def set_graph_message_draft(self, edges: list[GraphMessageEdge]) -> None:
        """Stage rows on the DRAFT slot (the editor's Save). The active config
        — and every solve that uses it — is untouched until Activate."""
        with self._lock:
            active = self._graph_message_config["active"]
            self._graph_message_config["draft"] = GraphMessageConfigEnvelope(
                name=active.name if active is not None else "default",
                version=(active.version + 1) if active is not None else 1,
                createdAt=_config_now(),
                author="desk",
                parentVersion=active.version if active is not None else None,
                notes="",
                rows=list(edges),
            )
        self._persist_message_config()
        self.log_event("graph_message_draft", payload={"nRows": len(edges)})

    def activate_message_config(self, notes: str = "") -> None:
        """Promote the draft to ACTIVE (the audited lifecycle step): the solve
        row set flips, the draft stays as a clean copy of the new active.
        Raises ValueError when nothing is staged."""
        with self._lock:
            draft = self._graph_message_config["draft"]
            if draft is None:
                raise ValueError("no draft config to activate")
            active = draft.model_copy(
                update={"createdAt": _config_now(), "notes": notes or draft.notes}
            )
            self._graph_message_config = {
                "draft": active.model_copy(
                    update={
                        "version": active.version + 1,
                        "parentVersion": active.version,
                        "notes": "",
                    },
                    deep=True,
                ),
                "active": active,
            }
            self._graph_message_edges = list(active.rows)
        # Legacy blob keeps mirroring the ACTIVE rows (downgrade safety).
        save_graph_message_edges(
            self.store_path, [e.model_dump() for e in active.rows]
        )
        self._persist_message_config()
        self.log_event(
            "graph_message_config_activate",
            payload={
                "name": active.name,
                "version": active.version,
                "nRows": len(active.rows),
            },
        )

    def revert_message_config(self) -> None:
        """Discard the draft: it becomes a clean copy of the active config
        (or empty when nothing was ever activated)."""
        with self._lock:
            active = self._graph_message_config["active"]
            self._graph_message_config["draft"] = (
                active.model_copy(
                    update={
                        "version": active.version + 1,
                        "parentVersion": active.version,
                        "notes": "",
                    },
                    deep=True,
                )
                if active is not None
                else None
            )
        self._persist_message_config()
        self.log_event("graph_message_config_revert")

    def _persist_message_config(self) -> None:
        """Best-effort blob write (never breaks the operation being staged)."""
        try:
            save_graph_message_config(
                self.store_path, _config_blob(self._graph_message_config)
            )
        except Exception:  # noqa: BLE001 — persistence must not break staging
            pass

    # ------------------------------------------------------------- audit log
    def log_event(self, action: str, scope: str = "", payload: dict | None = None) -> None:
        """Append-only audit event (governance kernel, R1 item 8).

        Best-effort by design: the in-memory tail always records (tests, the
        UI's recent-activity view), the store persists when configured, and a
        persistence hiccup NEVER breaks the operation being audited. Actor is
        the constant "desk" until the hosted product names sessions."""
        entry = {"action": action, "scope": scope, "payload": payload or {}}
        with self._lock:
            self._event_tail.append(entry)
        if self.store_path is None:
            return
        try:
            with VolStore(self.store_path) as store:
                governance.append_event(store, action, scope, payload or {})
        except Exception:  # noqa: BLE001 — audit must never break the operation
            pass

    def event_tail(self, limit: int = 50) -> list[dict]:
        """The most recent in-memory audit events, newest first."""
        with self._lock:
            return list(self._event_tail)[-limit:][::-1]

    # ------------------------------------------------------ graph idio history
    def graph_idio_sigma(self) -> dict[str, float]:
        """Per-ticker trailing idio sigma from innovations recorded STRICTLY
        before today (the reference date) — the idio band floor's causal input."""
        with self._lock:
            return self._graph_idio.sigma_map(self.reference_date.isoformat())

    def record_graph_innovations(self, items: dict[tuple[str, str], float]) -> None:
        """Record today's lit-node ATM innovations ``{(ticker, expiry): innov}``.

        Idempotent per (ticker, day, expiry) — repeated solves overwrite — and
        persisted best-effort so the floor survives a restart."""
        if not items:
            return
        day = self.reference_date.isoformat()
        with self._lock:
            changed = False
            for (ticker, expiry), value in items.items():
                changed |= self._graph_idio.record(ticker, day, expiry, value)
            blob = self._graph_idio.to_blob() if changed else None
        if blob is not None:
            save_graph_idio(self.store_path, blob)

    # --------------------------------------------------------------- universe
    @property
    def universe(self):
        return self._universe

    @universe.setter
    def universe(self, value) -> None:
        self._universe = value
        if value is None:  # explicit invalidation also drops the build signature
            self._universe_sig = None

    @property
    def universe_sig(self) -> tuple | None:
        """calib_signature the cached universe was built against (None = rebuild)."""
        return self._universe_sig

    @universe_sig.setter
    def universe_sig(self, value: tuple | None) -> None:
        self._universe_sig = value


def _coerce_block_rule(raw: dict | None) -> GraphBlockRule | None:
    """Validate a persisted block-rule blob; None on absence or bad data (a stale
    blob degrades to 'no rule' — the expanded edges persist separately, so the
    served topology survives even when the rule blob does not)."""
    if not raw:
        return None
    try:
        return GraphBlockRule(**raw)
    except Exception:  # noqa: BLE001 — never let a stale blob break startup
        return None


def _dump_diff(old, new) -> dict:
    """Changed-fields diff of two pydantic models: {field: [old, new]} — the
    audit log records WHAT moved, not full settings dumps."""
    od, nd = old.model_dump(), new.model_dump()
    return {k: [od.get(k), nd[k]] for k in nd if od.get(k) != nd[k]}


def _coerce_graph_edges(raw: list[dict]) -> list[GraphEdgeInput]:
    """Validate persisted edge dicts into GraphEdgeInput, dropping unreadable ones
    (a stale/partial blob degrades to fewer edges, never a startup crash)."""
    out: list[GraphEdgeInput] = []
    for item in raw:
        try:
            out.append(GraphEdgeInput(**item))
        except Exception:  # noqa: BLE001 — skip a malformed persisted edge
            continue
    return out


def _coerce_message_edges(raw: list[dict]) -> list[GraphMessageEdge]:
    """Validate persisted message-edge dicts, dropping unreadable ones (same
    degrade-gracefully contract as the legacy edge blob)."""
    out: list[GraphMessageEdge] = []
    for item in raw:
        try:
            out.append(GraphMessageEdge(**item))
        except Exception:  # noqa: BLE001 — skip a malformed persisted edge
            continue
    return out


def _config_now() -> str:
    """ISO-second UTC stamp for config-envelope writes."""
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_message_config(
    raw: dict | None,
) -> dict[str, GraphMessageConfigEnvelope | None]:
    """Validate the persisted U6 envelope pair; an unreadable slot degrades to
    None (same contract as every settings blob)."""
    out: dict[str, GraphMessageConfigEnvelope | None] = {"draft": None, "active": None}
    for slot in ("draft", "active"):
        item = (raw or {}).get(slot)
        if item is None:
            continue
        try:
            out[slot] = GraphMessageConfigEnvelope.model_validate(item)
        except Exception:  # noqa: BLE001 — skip a malformed persisted slot
            continue
    return out


def _config_blob(config: dict[str, GraphMessageConfigEnvelope | None]) -> dict:
    """JSON-safe blob of the envelope pair."""
    return {
        slot: (env.model_dump() if env is not None else None)
        for slot, env in config.items()
    }


def _source_id_of(provider: OptionChainProvider) -> str:
    """Stable data-source id for a provider instance (used when AppState is
    built around a single provider, e.g. in tests)."""
    name = type(provider).__name__.lower()
    for sid in ("yahoo", "bloomberg", "massive", "synthetic"):
        if sid in name:
            return sid
    return "synthetic"  # unknown/custom providers behave like the offline source
