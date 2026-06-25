"""Pydantic schemas for the volfit HTTP API (ROADMAP Phase 5).

The smile payload field names are FROZEN against the frontend contract in
frontend/src/lib/mockData.ts: `SmilePoint`, `QuoteBand`, `SmileDiagnostics`
and `SmileData` must serialize to exactly the camelCase shapes the React
Smile Viewer already consumes, so swapping its mock module for live API
calls is a one-line change. Request/response models for the surface fit,
graph solver, SSR scenario, term-structure and density endpoints follow the
same convention.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Market-settings / forward-mode and fit-history schemas live in their own
# modules (file-size policy) and are re-exported here so the API keeps one
# schema import surface.
from volfit.api.schemas_history import (  # noqa: F401  (re-export)
    HistoryPoint,
    HistoryResponse,
)
from volfit.api.schemas_market import (  # noqa: F401  (re-export)
    DividendSpec,
    ForwardEntry,
    ForwardPolicy,
    ForwardsResponse,
    MarketSettings,
)
from volfit.dynamics.ssr import Regime

#: Quote-weighting modes for slice calibration (product spec: fit to mid,
#: fit to bid-ask, or fit to a haircut bid-ask).
FitMode = Literal["mid", "bidask", "haircut"]


# ------------------------------------------------------------- fit settings
class FitSettings(BaseModel):
    """Global slice-fit hyperparameters (the Smile Viewer's panel).

    PUT /settings/fit applies them to every subsequent fit: the settings
    version is folded into the fit-cache key, so all views (smile, term,
    density, local-vol) refit consistently — no per-endpoint threading.
    ``model`` chooses the smile family the Smile Viewer charts: "lqd" (the
    arbitrage-free quantile-density default, also the analytic backbone), or
    the "svi" / "sigmoid" overlays (volfit.api.fit_models) calibrated to the
    same quotes. ``nOrder``/``regLambda``/``regPower`` only affect LQD; the
    overlay families ignore them. ``nCores`` is the number R of zero-wing hat
    kernels of the Multi-Core SIV ("sigmoid") slice (the slider analogue of the
    LQD Legendre order, eq param-count of the MC-SIV note); it only affects the
    sigmoid family. LQD is always fitted under the hood, so the density,
    term-structure, local-vol and graph views stay LQD-based. ``haircut`` is the
    band tightening of the "haircut" fit mode in absolute vol (0.005 = 0.5 vol
    points); it only affects fit_mode="haircut" (volfit.calib.band).
    ``weightScheme`` chooses the per-quote calibration weights (volfit.calib.
    weights): "equal" (unit weights, the historical scheme) or "tv_density"
    (time-value density weights — economic time-value shape with the strike
    oversampling divided out); it applies in every fit mode and to every model.
    """

    model: Literal["lqd", "svi", "sigmoid"] = "lqd"
    nOrder: int = Field(6, ge=4, le=16)  # Legendre order N of the LQD slice
    regLambda: float = Field(1e-6, ge=0.0, le=1.0)  # lam * n^{2r} a_n^2 damping
    regPower: float = Field(1.0, ge=0.0, le=4.0)  # the r in n^{2r}
    nCores: int = Field(2, ge=0, le=6)  # Multi-Core SIV hat count R (sigmoid only)
    haircut: float = Field(0.005, ge=0.0, le=0.05)  # haircut-mode band shrink (vol)
    weightScheme: Literal["equal", "tv_density"] = "equal"  # per-quote weights
    # --- per-model optimization / penalty coefficients (Options exposes them
    # all explicitly; every default equals the historical hardcoded constant, so
    # a default fit is byte-identical to before they were tunable) ---
    barrierCenter: float = Field(0.90, gt=0.0, lt=1.0)  # LQD A_R soft-barrier centre
    barrierScale: float = Field(50.0, gt=0.0)  # LQD A_R soft-barrier steepness
    sviPenaltyWeight: float = Field(1e3, ge=0.0)  # SVI no-arb soft-penalty weight
    leeSlopeMax: float = Field(2.0, gt=0.0)  # SVI Lee wing-slope bound
    sigmoidRidge: float = Field(1e-2, ge=0.0)  # Multi-Core SIV hat-amplitude ridge
    midAnchorWeight: float = Field(0.05, ge=0.0)  # band-mode mid anchor (all models)


# ----------------------------------------------------- options (meta) settings
class OptionsSettings(BaseModel):
    """Global meta / UX settings and engine defaults — the Options workspace
    (ROADMAP Phase 10). Distinct from FitSettings (the live per-fit knobs): these
    are app-wide toggles, penalty strengths and seed-defaults the other
    workspaces read.

    Wired to real engine behaviour this phase:
      * ``calendarWeight`` — the quadratic calendar-slack penalty weight folded
        into surface slice fits (volfit.models.lqd.calibrate, eq. slack_calendar);
        the only field that changes calibration output, so it (alone) bumps the
        options version in the fit-cache key.
      * ``enforceCalendar`` — calendar-arbitrage fix: when on, the background
        Calibrate job (volfit.api.workflow.calibrate_all) couples each ticker's lit
        expiries in ascending-T order, threading the previous slice as a convex-
        order floor; the surface-fit endpoint also seeds its default from it.
      * ``eventsEnabled`` — global default for event-time dilation (term view).
      * ``varSwapEnabled`` — whether the var-swap level is surfaced.
      * ``dynamicsRegime`` / ``ssr`` — seed defaults for the spot-vol scenario.
      * ``gridXNodes`` / ``gridTNodes`` / ``gridRegLambda`` — default vertex grid
        and roughness of the local-vol-affine fit (AffineFitRequest seeds them).
      * ``autoLoadPrior`` — when on (and a prior has been fetched), the active
        spot-updated prior anchors the calibration at delta-locations with a
        data-gap precision (volfit.calib.prior): dense-quote zones ignore the
        prior, sparse wings lean on it. Strength ``priorAnchorWeightPct``.

    Stubbed this phase (persisted UI state only; behaviour is a documented TODO):
      * ``autoCalibrate`` — auto-refit on every quote edit (True, today's
        behaviour) vs a manual "Calibrate" trigger gating refits.
      * ``spotMode`` — stream live spot and re-price ("realtime") vs freeze spot
        at load ("static"); pairs with the existing As-of selector.
    """

    #: Default fit target (Mid / Bid-Ask band / Haircut band). The live fit target
    #: is a per-request param; this is the persisted DEFAULT the frontend seeds the
    #: session from on load, so "Save as default" remembers it. Backend stores it
    #: only (each fit still receives its mode per request), so it never bumps the
    #: options version.
    fitMode: FitMode = "mid"
    # arbitrage / events / var-swap (wired as global defaults)
    enforceCalendar: bool = True
    #: Master switch for the event-weighted variance clock (volfit.calib.
    #: weighted_time): when on, the ticker's event calendar augments day-weights
    #: so an event before an expiry lowers the working IV at fixed price. Now
    #: affects calibration, so it bumps the options version.
    eventsEnabled: bool = True
    #: Normalize the variance clock so the 1Y weight budget stays 365 (rescale
    #: ALL days, events included): events redistribute variance within the year
    #: and 1Y vols are unchanged. Off by default (cumulative weight > calendar
    #: days). Affects calibration -> bumps the options version.
    normalizeEvents: bool = False
    varSwapEnabled: bool = True
    #: Var-swap penalty weight as a PERCENTAGE of the summed option-quote weights
    #: of the same (asset, expiry) node (volfit.api.varswap.varswap_target): at
    #: 100% an active var-swap quote weighs as much as all option quotes combined.
    #: Changes calibration output, so it bumps the options version (set_options),
    #: and only matters while ``varSwapEnabled`` is on.
    varSwapWeightPct: float = Field(10.0, ge=0.0, le=1000.0)
    #: How the Local-Vol fit prices the model variance swap. "static" is the
    #: log-contract strike replication of the option surface (the k^-2-weighted
    #: integral); "source_pde" is the backward source PDE g(0,1)
    #: (volfit.models.localvol.varswap_pde) — a LOCAL quantity, far less sensitive
    #: to coarsening/truncating the strike grid in the wings (needed once the
    #: calibration grid is coarsened; Stage 3). Calibration-affecting (bumps the
    #: options version); parametric models always use the static replication.
    varSwapMethod: Literal["static", "source_pde"] = "static"
    # prior default
    autoLoadPrior: bool = False
    #: Prior-anchor budget as a PERCENTAGE of the summed option-quote weights of the
    #: node (like the var-swap penalty): the total weight given to the data-gap
    #: prior anchor (volfit.calib.prior), distributed across the delta-locations in
    #: proportion to the observed-vs-desired quote-density deficit. Only bites while
    #: ``autoLoadPrior`` is on and a prior is active; changes calibration output, so
    #: it bumps the options version (set_options).
    priorAnchorWeightPct: float = Field(50.0, ge=0.0, le=1000.0)
    #: Per-side delta-locations the prior anchor is placed at (the wing shape it
    #: pins); ATM is always added, and the var-swap prior carries the aggregate tail
    #: below the smallest delta. Each value is a forward Black delta in (0, 0.5).
    priorAnchorDeltas: list[float] = Field(default=[0.02, 0.05, 0.10, 0.25, 0.40])

    @field_validator("priorAnchorDeltas")
    @classmethod
    def _clean_deltas(cls, v: list[float]) -> list[float]:
        """Keep deltas strictly in (0, 0.5), dedup + sort; fall back to the default
        set if nothing valid is given (so the anchor always has placements)."""
        cleaned = sorted({round(float(d), 4) for d in v if 0.0 < float(d) < 0.5})
        return cleaned or [0.02, 0.05, 0.10, 0.25, 0.40]

    # ---- prior-persistence mode (Docs/prior_persistence_design_options.md §10) --
    #: Which prior-persistence model the calibration uses. ``strike_gap`` is the
    #: legacy data-gap anchor (what ``autoLoadPrior`` used to switch on);
    #: ``quote_operator`` / ``smile_factor`` / ``hybrid`` persist trader-readable
    #: shape factors (ATM/RR/BF/var-swap, or level/skew/curvature) ONLY where the
    #: live quotes do not already identify them (the §9.3 activation gate);
    #: ``graph_only`` leaves lit calibration market-pure and relies on the graph
    #: baseline for dark nodes; ``off`` / ``overlay`` add no calibration penalty
    #: (``overlay`` still draws the dotted transported prior). A persisted
    #: pre-mode blob is migrated from ``autoLoadPrior`` on store load
    #: (settings_persist); new installs default to the recommended ``hybrid``.
    #: Calibration-affecting -> bumps the options version (set_options).
    priorPersistenceMode: Literal[
        "off", "overlay", "strike_gap", "quote_operator",
        "smile_factor", "hybrid", "graph_only",
    ] = "hybrid"
    #: Quote operators the prior may persist in ``quote_operator`` / ``hybrid``
    #: modes (§5): ATM level, 25/10-delta risk-reversal (RR) and butterfly (BF),
    #: and the var-swap level. Unknown names are dropped; empty -> the default set.
    priorOperatorSet: list[str] = Field(default=["ATM", "RR25", "BF25", "VarSwap"])
    #: Base operator-prior budget as a percent of the summed option-quote weights.
    priorOperatorStrengthPct: float = Field(50.0, ge=0.0, le=1000.0)
    #: Observation-precision threshold above which an operator's prior turns OFF
    #: (the gate's required precision; per-operator multipliers live in code, §9.3).
    priorOperatorRequiredPrecision: float = Field(1.0, ge=0.0)
    #: Sharpness gamma of the gate transition gap = max(1 - obs/req, 0)^gamma (§9.3).
    priorOperatorGapExponent: float = Field(1.0, ge=0.0, le=10.0)
    #: Quote-support kernel bandwidth (log-moneyness) around each operator leg (§5.3).
    priorOperatorBandwidth: float = Field(0.06, gt=0.0, le=2.0)
    #: Operator covariance model: ``diagonal`` (per-operator, the v1) or ``full``
    #: (Jacobian-propagated covariance, a later upgrade — §5.3).
    priorOperatorCovarianceMode: Literal["diagonal", "full"] = "diagonal"
    #: Two-pass activation (§5.4): fit data-only first, measure operator precision,
    #: then refit with only the under-observed operator priors, so a well-observed
    #: move is never damped. Off (default) = the cheaper single-pass quote-support
    #: gate (no extra fit). Calibration-affecting -> bumps the options version.
    priorDataOnlyPrepass: bool = False
    #: Risk-reversal / collar sign convention: ``call_put`` = call-delta minus
    #: put-delta vol, ``put_call`` = the opposite (§5.1, desk choice).
    collarSign: Literal["call_put", "put_call"] = "call_put"
    #: Smile factors the prior may persist in ``smile_factor`` mode (§6): ATM vol,
    #: ATM skew, ATM curvature, optional wing slopes, var-swap vol.
    priorFactorSet: list[str] = Field(default=["ATM", "skew", "curvature", "VarSwap"])
    #: Base factor-prior budget as a percent of the summed quote weights (§6).
    priorFactorStrengthPct: float = Field(50.0, ge=0.0, le=1000.0)
    #: Residual deep-tail strike-anchor budget in ``hybrid`` mode, as a percent of
    #: the summed quote weights — applied only where no operator/quote covers the
    #: tail (uses ``priorAnchorDeltas`` for the deep placements, §7).
    priorTailAnchorStrengthPct: float = Field(20.0, ge=0.0, le=1000.0)

    @field_validator("priorOperatorSet")
    @classmethod
    def _clean_operators(cls, v: list[str]) -> list[str]:
        """Keep known operator names in declaration order (dedup); empty -> default.

        Known: ATM, RR25/BF25 (25-delta), RR10/BF10 (10-delta), VarSwap. Mirrors
        the registry in volfit.calib.operators so the UI cannot persist an op the
        builder does not know."""
        known = ["ATM", "RR25", "BF25", "RR10", "BF10", "VarSwap"]
        kept = [op for op in known if op in set(v)]
        return kept or ["ATM", "RR25", "BF25", "VarSwap"]

    @field_validator("priorFactorSet")
    @classmethod
    def _clean_factors(cls, v: list[str]) -> list[str]:
        """Keep known factor names in canonical order (dedup); empty -> default."""
        known = ["ATM", "skew", "curvature", "leftWing", "rightWing", "VarSwap"]
        kept = [f for f in known if f in set(v)]
        return kept or ["ATM", "skew", "curvature", "VarSwap"]
    # local-vol-affine vertex grid + roughness (the single source of truth: the
    # affine fit reads these directly; the Local-Vol workspace has no own knobs).
    #: Strike-vertex placement: "delta" = the symmetric delta axis (dense near
    #: ATM, controlled wing reach; the default — fixes the under-resolved put
    #: wing), "linear" = the legacy uniform-in-x axis. (volfit.api.affine_fit)
    gridStrikeMode: Literal["delta", "linear"] = "delta"
    #: Strike vertices. In "delta" mode this is a FLOOR (the delta set ~13 nodes
    #: drives placement; midpoints are inserted only to reach this many); in
    #: "linear" mode it is the exact count.
    gridXNodes: int = Field(12, ge=3, le=200)
    #: Time vertices (Stage 3 sqrt(T) axis): the base set is always 0 + a node
    #: before the first expiry + every lit expiry. This is a FLOOR on the number
    #: of POSITIVE time vertices — the widest sqrt(T) gaps are split until reached
    #: (never drops an expiry); 0 = the base set only. (volfit.api.affine_fit)
    gridTNodes: int = Field(10, ge=0, le=120)
    gridRegLambda: float = Field(1e-2, ge=0.0, le=1e4)
    gridRegRho: float = Field(1.0, ge=0.0, le=10.0)  # affine time-vs-strike roughness
    #: Force the local VOL sigma(x, t) convex in x below the 5Δ-put strike (a soft
    #: hinge sqrt(W)·relu(-D²sigma) per time row at the deep-put vertices), to stop
    #: the sparse left wing from fitting too concave. Off ⇒ byte-identical.
    convexWing: bool = False
    convexWingWeight: float = Field(1e3, ge=0.0)  # W above; tunable strength
    #: Front tie (Stage 4): pull the unconstrained t = 0 vertex row toward the
    #: first (data-identified) row via a soft one-sided difference
    #: sqrt(W)·(θ[0,:] − θ[1,:]) per strike column, so the free front stops leaking
    #: into the shortest, most-curved smile. On by default (a mild stabilizer);
    #: weight 0 / off ⇒ byte-identical. (volfit.models.localvol.affine_calib)
    frontTie: bool = True
    frontTieWeight: float = Field(1e-2, ge=0.0)
    #: Adaptive local-vol CAP: the nodal local vol is bounded at
    #: max(60%, lvVolCapMult x the highest observed implied vol) — capped at 400%.
    #: The old fixed 60% cap clamped the deep-put LOCAL vol of high-vol names
    #: (NVDA), starving the put wing; local variance in the wing runs well above
    #: implied, so the bound must scale with the name. (volfit.api.affine_fit)
    lvVolCapMult: float = Field(3.0, ge=1.0, le=20.0)
    #: LV PDE time discretisation (Stage 7): "rannacher" = Crank-Nicolson (2nd order)
    #: after implicit-Euler kink-damping start-up — reaches the same accuracy at ~3x
    #: larger dt, so the Dupire march runs ~3x fewer time steps per evaluation (the
    #: per-eval speed-up); "implicit" = fully implicit Euler (1st order, the legacy
    #: scheme). Quality-neutral by construction (better per-step accuracy, not a
    #: coarser data grid). Var-swap fits (free left-slope) keep implicit either way.
    #: LV-only: folded into affine_key, does not bump the parametric options version.
    #: Default "implicit": benchmarked at only ~1.1x net (CN's heavier sensitivity
    #: step ~cancels the fewer-time-steps win) AND CN is not monotone (an arb
    #: violation appeared on a coarse-x grid), so it is OFF by default; available as
    #: an opt-in. The real cold-fit lever is fewer evals, not fewer time steps.
    timeScheme: Literal["implicit", "rannacher"] = "implicit"
    #: Early-stop the COLD LV fit when the quote-fit improvement stalls (Stage 8). The
    #: fit otherwise runs to the 200-eval cap though its tail evals barely move the
    #: surface; stopping at the stall point scales the WHOLE fit (march + assembly +
    #: optimizer). Measured ~1.45x (slow-converging SPY, +0.10 bp) to ~3.3x
    #: (fast-converging NVDA, +0.25 bp) on the cold fit; warm-started recalibrations
    #: converge before the stall window so they are unaffected. ON by default; OFF runs
    #: the full 200-eval fit. LV-only (folded into affine_key).
    lvEarlyStop: bool = True
    #: Use the compiled Numba vectorized-Thomas Dupire march (Stage 6′) for the LV
    #: calibration hot path — ~6x the scipy/LAPACK banded march (no-pivot Thomas,
    #: SIMD across the sensitivity columns, fused source), the bulk of the per-eval
    #: cost. Output matches the banded march to ~1e-15; falls back to banded
    #: automatically when numba is unavailable or for the var-swap / Rannacher paths.
    #: ON by default. LV-only (folded into affine_key).
    lvFastKernel: bool = True
    #: LV calibration solver (Stage 5, revisited). "gn" (the DEFAULT) = the matrix-free
    #: Gauss-Newton (volfit.models.localvol.affine_gn) — it AVOIDS trf's dense SVD
    #: (~52% of an eval), which pays now that the Numba march makes each eval cheap:
    #: ~1.3-1.65x faster than trf. "trf" = scipy trust-region (the legacy solver).
    #: Trade-off accepted at the default: GN converges to a slightly DIFFERENT local
    #: optimum on stiff real data, so its surface can differ by up to ~0.25 vol-bp
    #: (often better). GN engages only for the smooth MID fit target with the Numba
    #: kernel active (``lvFastKernel``); it falls back to trf otherwise — for the
    #: non-smooth bid-ask/haircut band objective, var-swap fits, or the banded march.
    #: LV-only (in affine_key).
    lvSolver: Literal["trf", "gn"] = "gn"
    #: Left-wing (x < x_min) LINEAR extrapolation slope as a multiple of the first
    #: cell's slope (between the two lowest vertices) — the deep-put local variance
    #: continues rising toward x = 0 instead of clamping flat. Used as the fixed
    #: multiple when Convex wing is ON (else flat); when a var-swap quote is set the
    #: slope becomes a FREE calibration variable (this is its init). The cap does
    #: not apply in the extrapolation region. (volfit.models.localvol.affine)
    leftWingSlopeMult: float = Field(1.5, ge=0.0, le=20.0)
    # editable penalty strength (changes calibration output)
    calendarWeight: float = Field(1e6, ge=0.0)
    # graph-solver prior defaults (the Graph SolverPanel seeds from these):
    # kappa = prior strength (local precision toward baseline), eta = reach,
    # lambda = OT flux weight (0 = off), nu = OT source allowance.
    graphKappaScale: float = Field(1.0, gt=0.0)
    graphEtaScale: float = Field(1.0, ge=0.0)
    graphLambdaScale: float = Field(0.0, ge=0.0)
    graphNu: float = Field(0.1, gt=0.0)
    # spot-vol dynamics defaults — the Parametric spot-scenario reads these
    # (the regime selector moved entirely to Options). "custom" uses ``ssr``.
    dynamicsRegime: Literal[
        "sticky_moneyness",
        "sticky_strike",
        "sticky_local_vol",
        "sticky_local_vol_grid",
        "custom",
    ] = "sticky_strike"
    ssr: float = Field(2.0, ge=0.0)
    # ---- calibration / data-fetch workflow (the trigger model) ----
    #: After options are fetched: ON = calibrate all lit nodes in the background;
    #: OFF = leave nodes stale until the user presses Calibrate. Also gates whether
    #: a quote edit / parameter change refits (ON) or just marks stale (OFF). The
    #: gated live server (serve.py) defaults this OFF (set in AppState when no saved
    #: preference) so fitting happens only on the explicit Calibrate button; the
    #: code default stays ON for the ungated test/dev app.
    autoCalibrate: bool = True
    #: Local-Vol (affine) calibration master switch. OFF = the background Calibrate
    #: job skips every ticker's LV surface (only the parametric nodes fit, so test
    #: cycles are fast) AND the Local Vol workspace tab is disabled. Pure
    #: workflow/UI gate — does not affect parametric fits, so it never busts caches.
    localVolEnabled: bool = True
    #: Spot updates: "realtime" = the backend scheduler polls the provider spot
    #: every ``spotPollSeconds`` and transports the surface; "static" = on-demand
    #: only (the "Fetch spots" button).
    spotMode: Literal["realtime", "static"] = "static"
    spotPollSeconds: float = Field(5.0, gt=0.0, le=3600.0)
    #: Options chains: "auto" = the scheduler refetches every
    #: ``optionsFetchMinutes``; "on_demand" = only the "Fetch Options Quotes" button.
    optionsFetchMode: Literal["auto", "on_demand"] = "on_demand"
    optionsFetchMinutes: float = Field(5.0, gt=0.0, le=1440.0)
    #: While a real-time WS book is streaming (Massive realtime), the scheduler
    #: refetches the chain from the book and recalibrates all lit nodes every
    #: ``streamRefitSeconds`` — a faster, book-driven loop distinct from the
    #: minutes-cadence ``optionsFetchMode == "auto"`` REST refetch.
    streamRefitSeconds: float = Field(5.0, gt=0.0, le=600.0)


# --------------------------------------------------- persisted settings defaults
class SettingsDefaultsStatus(BaseModel):
    """Whether the Fit/Options "Save as default" persistence is available and used.

    ``storeEnabled`` is False when no app store is configured (VOLFIT_DB unset /
    restart.ps1 -NoDb) — the Options tab then disables its Save button.
    ``hasSaved`` reports whether the user has saved defaults to the store.
    """

    storeEnabled: bool
    hasSaved: bool


class SettingsDefaultsReset(SettingsDefaultsStatus):
    """Reset response: the status plus the reverted (code-default) settings, so
    the Options drafts can re-sync without a second round-trip."""

    fit: FitSettings
    options: OptionsSettings


# ------------------------------------------------- prior-persistence diagnostics
class PriorOperatorDiag(BaseModel):
    """One operator / factor's prior-persistence diagnostics (design note §9.4).

    ``gap`` in [0, 1] is the activation factor (1 = fully persisted, 0 = the data
    identifies it so the prior is off); ``activeLambda`` is the final LSQ weight."""

    operator: str
    priorValue: float
    obsPrecision: float
    requiredPrecision: float
    gap: float
    activeLambda: float


class PriorDiagnostics(BaseModel):
    """Auditable prior-persistence state for one node (the §9.4 table): which shape
    factors the prior is persisting and why, so the prior is never a hidden
    stabilizer. ``operators`` is populated in quote-operator / smile-factor / hybrid
    modes; ``strikeAnchorCount`` in strike-gap / hybrid (the deep-tail anchor)."""

    mode: str
    active: bool
    operators: list[PriorOperatorDiag] = []
    varSwapPriorVol: float | None = None
    varSwapWeight: float | None = None
    strikeAnchorCount: int | None = None


# ------------------------------------------------------------- smile payload
class SmilePoint(BaseModel):
    """One point of a continuous model curve in (log-moneyness, vol) space."""

    k: float
    vol: float


class QuoteBand(BaseModel):
    """One market quote as a bid/ask band of implied vols at log-moneyness k.

    ``index`` is the quote's position in the prepared array — stable for the
    session and the key used by quote edits. ``excluded`` quotes are dropped
    from calibration but still listed (the UI dims them); ``amended`` flags a
    user-overridden mid (bid/ask stay the original market band).
    """

    k: float
    bid: float
    ask: float
    mid: float
    index: int
    excluded: bool
    amended: bool


class SmileDiagnostics(BaseModel):
    """Headline diagnostics displayed next to the smile chart."""

    atmVol: float
    skew: float
    curvature: float
    aLeft: float  # endpoint scales A_L, A_R (eqs. AL, AR of the LQD note)
    aRight: float
    leeLeft: float  # Lee wing slopes beta_L, beta_R (eqs. betaL, betaR)
    leeRight: float
    varSwapVol: float
    rmsError: float  # weighted RMS vol error of the fit (decimal vol; UI shows %)


class ModelParam(BaseModel):
    """One displayed model hyperparameter as a label/value pair (e.g. the LQD
    Legendre degree, the Multi-Core SIV core count) — a presentational row in the
    diagnostics panel, so its shape is uniform across families."""

    label: str
    value: str


class ModelInfo(BaseModel):
    """The model family + its hyperparameters that produced the DISPLAYED fit.

    Derived from the actual displayed slice (not the live FitSettings), so a
    frozen/stale node correctly reports the family + degree/cores it was last
    calibrated with even after the settings have moved on. Surfaced in the
    Parametric diagnostics aside to make model/hyperparameter testing legible."""

    id: Literal["lqd", "svi", "sigmoid"]
    label: str  # human family name ("LQD", "SVI-JW", "Multi-Core SIV")
    params: list[ModelParam] = Field(default_factory=list)


class VarSwapInfo(BaseModel):
    """Variance-swap quote state of a node (volfit.api.varswap_session).

    ``level`` is the quoted var-swap *volatility* (None when no quote exists);
    ``modelVol`` is the model's own fair var-swap vol (the diagnostics value, so
    the UI can seed a new quote at the model level and show the gap). ``enabled``
    mirrors OptionsSettings.varSwapEnabled so the frontend can gate the affordance
    without a second fetch. ``canUndo``/``canRedo`` cover the SEPARATE var-swap
    edit history (independent of the option-quote session)."""

    level: float | None
    excluded: bool
    modelVol: float
    enabled: bool
    canUndo: bool
    canRedo: bool


class SmileData(BaseModel):
    """Everything the Smile Viewer needs for one (underlying, expiry) node."""

    ticker: str
    expiry: str  # ISO date
    T: float  # year fraction to expiry
    forward: float
    model: list[SmilePoint]
    prior: list[SmilePoint]
    #: True when ``prior`` is the ACTIVE fetched prior, transported to the current
    #: forward under the dynamics regime (drawn dotted as a spot-updated prior);
    #: False when it is a saved per-node prior or the current fit fallback.
    priorTransported: bool = False
    quotes: list[QuoteBand]
    kMin: float
    kMax: float
    diagnostics: SmileDiagnostics
    modelInfo: ModelInfo  # displayed model family + hyperparameters (degree / cores)
    varSwap: VarSwapInfo  # variance-swap quote + model level for this node
    canUndo: bool  # quote-edit session undo/redo availability
    canRedo: bool  # (both False when the node has no edit session yet)
    #: False when the node has never been calibrated (gated workflow, before the
    #: Calibrate button): ``model`` is empty and the view shows quotes (if fetched)
    #: + the dotted prior (if any), with a "No fit yet — Calibrate" cue.
    hasFit: bool = True
    stale: bool = False  # inputs drifted since the last calibration (needs Calibrate)
    #: Whole-surface weighted RMS vol error of the ticker (all expiries pooled, the
    #: same calibration-consistent basis as diagnostics.rmsError). Decimal vol.
    surfaceRmsError: float = 0.0
    #: The pre-transport calibration curve, set only while a spot move is active,
    #: so the viewer can overlay the original fit (dimmed) under the transported
    #: smile. Each curve is in its own log-moneyness (sticky-strike => a lateral
    #: shift; sticky-moneyness => the two coincide). None when no spot move.
    anchorModel: list[SmilePoint] | None = None


# ------------------------------------------------------------------ universe
class ExpiryInfo(BaseModel):
    """One listed expiry of a ticker with its year fraction and type tag
    (daily/weekly/monthly/quarterly/leaps — volfit.data.expiries), the
    handle for bulk expiry selection in the universe screen."""

    expiry: str
    t: float
    expiryType: str


class UniverseResponse(BaseModel):
    """Available tickers and their expiry ladders."""

    asOf: str
    tickers: list[str]
    expiries: dict[str, list[ExpiryInfo]]


class PriorSavedResponse(BaseModel):
    """Acknowledgement of a prior-curve save."""

    saved: bool = True


# --------------------------------------------------------------- quote edits
class QuoteEditRequest(BaseModel):
    """One quote-set edit on a smile node (fit-session model).

    ``exclude``/``include`` require ``index``; ``amend`` requires ``index``
    and ``mid`` (the replacement mid *implied vol*, e.g. 0.21); ``reset``
    clears every edit. Semantic validation (range, missing fields, the
    minimum-quote guard) lives in volfit.api.session.EditSession.apply.
    """

    action: Literal["exclude", "include", "amend", "reset"]
    index: int | None = None
    mid: float | None = None


class VarSwapEditRequest(BaseModel):
    """One variance-swap quote edit on a smile node (volfit.api.varswap_session).

    ``set`` adds or adjusts the quote and requires a positive ``level`` (var-swap
    *volatility*, e.g. 0.185); ``exclude``/``include`` toggle an existing quote in
    or out of the fit; ``remove``/``reset`` delete it. Semantic validation lives
    in VarSwapSession.apply (router maps ValueError to HTTP 422)."""

    action: Literal["set", "exclude", "include", "remove", "reset"]
    level: float | None = None


# --------------------------------------------------------------- surface fit
class SurfaceFitRequest(BaseModel):
    """Fit all expiries of one ticker, sequential and calendar-constrained."""

    ticker: str
    fitMode: FitMode = "mid"
    enforceCalendar: bool = True


class SurfaceFitResponse(BaseModel):
    """Per-expiry fits plus calendar diagnostics, nearest to farthest."""

    ticker: str
    expiries: list[str]
    calendarResiduals: list[float]  # max_alpha (G_near - G_far), 0 for first
    maxIvErrorBp: list[float]
    smiles: list[SmileData]


# ---------------------------------------------------------------- 3D surface
class SurfaceResponse(BaseModel):
    """sigma(k, T) mesh for the 3D vol-surface chart (volfit.api.surface).

    Every expiry's fitted slice is sampled on ONE shared log-moneyness grid
    (the union of the per-expiry quoted ranges), so ``vol`` is a full
    rectangular mesh: ``vol[i][j]`` is the implied vol of expiry i at k[j].
    """

    ticker: str
    expiries: list[str]  # ISO dates, nearest first
    t: list[float]  # CALENDAR year fractions, same order
    tau: list[float]  # event-variance years the mesh is quoted in (= t with no events)
    k: list[float]  # shared log-moneyness grid (length N_SURFACE_POINTS)
    vol: list[list[float]]  # one row per expiry, one column per k (sqrt(w / tau))
    atmVol: list[float]  # exact ATM handle per expiry (lqd.atm)
    forward: list[float]  # active forward per expiry


# --------------------------------------------------------------- quote table
class TableRow(BaseModel):
    """One prepared quote of a slice as a table/export row (volfit.api.table).

    IVs are the displayed band (an amended quote shows its overridden mid);
    prices are *discounted* OTM option prices reconstructed by Black at the
    band IVs (puts by parity), in the same conventions as volfit.api.quotes.
    """

    index: int
    strike: float
    type: str  # "C"/"P" — the OTM side convention (call iff k >= 0)
    k: float
    bidIv: float
    midIv: float
    askIv: float
    modelIv: float  # fitted vol at this k
    bidPrice: float
    midPrice: float
    askPrice: float
    excluded: bool
    amended: bool


class TableResponse(BaseModel):
    """The full quote/price/IV table of one fitted (ticker, expiry) node."""

    ticker: str
    expiry: str
    t: float
    forward: float
    discount: float
    rows: list[TableRow]


# --------------------------------------------------------------- graph solve
class GraphObservation(BaseModel):
    """One observed handle shift on a smile node, in absolute handle units."""

    ticker: str
    expiry: str
    dAtmVol: float
    dSkew: float = 0.0
    dCurv: float = 0.0


class GraphSolverParams(BaseModel):
    """Tunable hyperparameters of the increment prior Q_Delta and the graph.

    The three scales multiply the per-handle base regime (service.py
    GRAPH_PRIOR_HYPER): ``etaScale`` the directed-smoothness weight eta,
    ``kappaScale`` the local precision kappa (stiffness toward the baseline —
    higher means less propagation), ``lambdaScale`` the optimal-transport flux
    weight lambda (0 disables the OT term, preserving the legacy regime).
    ``nu`` is the OT source/sink allowance, used only when lambdaScale > 0.
    ``calendarWeight`` / ``crossWeight`` override the same-ticker and
    cross-ticker edge weights; null keeps the service defaults.
    """

    etaScale: float = Field(default=1.0, ge=0.0)
    kappaScale: float = Field(default=1.0, gt=0.0)
    lambdaScale: float = Field(default=0.0, ge=0.0)
    nu: float = Field(default=0.1, gt=0.0)
    calendarWeight: float | None = Field(default=None, gt=0.0)
    crossWeight: float | None = Field(default=None, gt=0.0)


class GraphSolveRequest(GraphSolverParams):
    """Propagate sparse handle observations through the smile universe."""

    observations: list[GraphObservation] = Field(min_length=1)


class GraphNodeResult(BaseModel):
    """Posterior ATM-vol summary for one node of the universe."""

    ticker: str
    expiry: str
    t: float
    baseAtmVol: float
    postAtmVol: float
    shiftBp: float
    sd: float
    bandLo: float  # 95% credible band on the posterior ATM vol
    bandHi: float
    observed: bool


class GraphSolveResponse(BaseModel):
    """Posterior field over every node of the smile universe."""

    nodes: list[GraphNodeResult]


class GraphAutotuneRequest(GraphSolverParams):
    """Pick the propagation reach etaScale by leave-one-out cross-validation.

    Needs at least two observations (LOO holds one out at a time). The other
    solver knobs are held fixed at the supplied values while eta is tuned;
    ``etaScale`` on this request is ignored (it is the quantity being chosen).
    """

    observations: list[GraphObservation] = Field(min_length=2)


class AutotuneCandidate(BaseModel):
    """One grid point of the auto-tune sweep and its LOO error."""

    etaScale: float
    rmseBp: float  # RMS leave-one-out ATM-vol prediction error, basis points


class GraphAutotuneResponse(BaseModel):
    """Chosen etaScale (LOO-RMSE minimizer) plus the full scored grid."""

    etaScale: float
    rmseBp: float
    candidates: list[AutotuneCandidate]


class GraphNodeInfo(BaseModel):
    """Baseline (pre-solve) fitted handles of one universe node."""

    ticker: str
    expiry: str
    t: float
    atmVol: float
    skew: float
    curvature: float
    lit: bool = True  # lit/dark designation (volfit.api.state); lit by default


class GraphNodesResponse(BaseModel):
    """The full smile universe with baseline handles (Graph Viewer lattice)."""

    nodes: list[GraphNodeInfo]


# ----------------------------------------------- production graph extrapolation
class GraphEdgeBeta(BaseModel):
    """Per-edge increment beta (plan Phase 6, Amendment D): the AMPLITUDE of a
    directed move, kept strictly separate from the edge weight (the TRUST).

    Directional: ``(from -> to)`` scales how much a unit move at the source node
    propagates to the target, per handle. ``beta_ij`` need not equal ``beta_ji``.
    """

    fromTicker: str
    fromExpiry: str
    toTicker: str
    toExpiry: str
    betaAtmVol: float = 1.0
    betaSkew: float = 1.0
    betaCurv: float = 1.0


class GraphEdgeInput(BaseModel):
    """One user-supplied directed edge: weight (TRUST) + per-handle beta (AMPLITUDE)
    kept as separate fields (plan Phase 7 / Amendment D). A supplied edge list
    defines the whole graph topology, overriding the auto-lattice; the node SET is
    still the selected lit+dark universe. ``beta_ij`` need not equal ``beta_ji``."""

    fromTicker: str
    fromExpiry: str
    toTicker: str
    toExpiry: str
    weight: float = Field(default=1.0, ge=0.0)  # directed conductance / trust
    betaAtmVol: float = 1.0  # directed amplitude per handle
    betaSkew: float = 1.0
    betaCurv: float = 1.0


class GraphEdgesResponse(BaseModel):
    """The persisted per-edge graph overrides (GET/PUT /graph/edges)."""

    edges: list[GraphEdgeInput]


class GraphEdgesRequest(BaseModel):
    """Replace the persisted per-edge overrides (empty list ⇒ back to the lattice)."""

    edges: list[GraphEdgeInput]


class GraphExtrapolateRequest(GraphSolverParams):
    """Production prior-anchored extrapolation over the SELECTED lit+dark universe.

    Unlike the sandbox ``GraphSolveRequest``, observations are NOT manually typed:
    they are derived server-side as ``calibrated_handles - transported_prior_handles``
    on the lit nodes (plan Amendment A). The solver knobs (eta/kappa/lambda/nu,
    calendar/cross weights) carry over from ``GraphSolverParams``.
    """

    #: Diagnostic/stress override: use flat ATM-only baselines at every node,
    #: ignoring any saved prior (plan Phase 2 flat_atm).
    flatAtm: bool = False

    #: v1 single-knob beta broadcast to every cross-ticker edge / handle / direction
    #: (calendar edges default to beta 1). Null keeps all betas at 1.
    crossBeta: float | None = None

    #: Explicit per-edge per-handle beta overrides (take precedence over crossBeta).
    edgeBetas: list[GraphEdgeBeta] = []

    #: Explicit edge list (weight + beta). When non-empty it defines the whole
    #: topology (overrides the lattice + crossBeta/edgeBetas); empty falls back to
    #: the persisted edges, then the auto-lattice (plan Phase 7).
    edges: list[GraphEdgeInput] = []


class GraphExtrapolateNode(BaseModel):
    """One node's prior -> posterior ATM-handle summary with full provenance.

    Bulk payload is ATM summaries only; full reconstructed curves are fetched per
    node on demand via the node-smile route (plan Amendment E / Phase 5)."""

    ticker: str
    expiry: str
    t: float  # calendar year fraction (display)
    lit: bool
    calibrated: bool  # lit AND has a calibration today (so it is an observation)
    priorSource: str  # active_transported | nearest_expiry_transported | ...
    priorAsOf: str | None = None
    transportDistance: float  # h = log(F_now / F_prior)
    validForValidation: bool
    # Baseline (transported prior) handles.
    priorAtmVol: float
    priorSkew: float
    priorCurv: float
    # Posterior (extrapolated) handles + ATM credible band.
    postAtmVol: float
    postSkew: float
    postCurv: float
    shiftBp: float  # (post - prior) ATM vol, basis points
    sd: float  # posterior ATM-vol standard deviation
    bandLo: float
    bandHi: float
    innovationBp: float | None = None  # lit nodes: (calibrated - prior) ATM vol, bp
    # Data-derived precision (plan Phase 4), per handle (atm_vol, skew, curvature).
    baselinePrecision: list[float] = []  # transported-prior baseline precision
    obsPrecision: list[float] | None = None  # lit-node observation precision
    precisionFactors: dict[str, float] = {}  # the scalar factor breakdown


class GraphExtrapolateResponse(BaseModel):
    """Posterior field over every selected node (production extrapolation)."""

    nodes: list[GraphExtrapolateNode]


class GraphQuotePoint(BaseModel):
    """One market quote band on a reconstructed node (for the live overlay)."""

    k: float
    bid: float
    mid: float
    ask: float


class GraphNodeMetrics(BaseModel):
    """Quote-comparison metrics of a reconstructed smile vs the market (plan Phase 5)."""

    nQuotes: int
    rmsVol: float  # weighted RMS vol error vs mid (calib/rms), decimal vol
    insideSpreadHitRate: float  # fraction of strikes with model inside [bid, ask]
    atmResidualBp: float  # (post - market) ATM vol, basis points
    skewResidual: float
    curvResidual: float
    standardizedResidual: float | None = None  # quoted DARK nodes only (eq. zeta)


class GraphNodeSmile(BaseModel):
    """A reconstructed node's full smile + prior/lit overlays + quote metrics.

    Fetched on demand per node (plan Amendment E) — the bulk solve returns ATM
    summaries only. Curves are sampled on the shared display k-grid."""

    ticker: str
    expiry: str
    t: float
    model: str = "lqd"  # the displayed model family the smile is reconstructed in
    lit: bool
    calibrated: bool
    priorSource: str
    validForValidation: bool
    priorAtmVol: float
    priorSkew: float
    priorCurv: float
    postAtmVol: float
    postSkew: float
    postCurv: float
    sd: float
    post: list[SmilePoint]  # reconstructed posterior smile
    postBandLo: list[SmilePoint]  # 95% credible band (ATM-level uncertainty)
    postBandHi: list[SmilePoint]
    prior: list[SmilePoint]  # transported prior smile
    litCalibration: list[SmilePoint]  # the node's own calibration (lit nodes)
    quotes: list[GraphQuotePoint]
    metrics: GraphNodeMetrics | None = None


class GraphBacktestNode(BaseModel):
    """One held-out node's leave-one-node-out prediction vs its calibration."""

    ticker: str
    expiry: str
    priorSource: str
    calibratedAtmVol: float
    postAtmVol: float  # predicted from the other nodes (this one withheld)
    residualBp: float  # (post - calibrated) ATM vol, basis points
    standardizedResidual: float  # zeta under the posterior + obs uncertainty


class GraphBacktestResponse(BaseModel):
    """Leave-one-node-out backtest over the calibrated, validation-clean nodes
    (plan Phase 8): per-node residuals + an aggregate calibration summary."""

    nodes: list[GraphBacktestNode]
    nScored: int
    nExcludedBootstrap: int  # calibrated nodes skipped (circular bootstrap prior)
    rmseBp: float  # RMS held-out ATM-vol prediction error, basis points
    zetaMean: float  # mean standardized residual (well-calibrated ⇒ ~0)
    zetaStd: float  # std standardized residual (well-calibrated ⇒ ~1)


# ------------------------------------------------------------------ scenario
class ScenarioRequest(BaseModel):
    """SSR scenario: shift one smile for a spot move under a dynamics regime.

    ``regime`` is a named regime ("sticky_moneyness" | "sticky_strike" |
    "sticky_local_vol") or a custom numeric SSR value.
    """

    ticker: str
    expiry: str
    spotReturn: float
    regime: Regime | float = Regime.STICKY_STRIKE
    fitMode: FitMode = "mid"


class ScenarioResponse(BaseModel):
    """Base and shifted smiles on a shared k grid, plus the resolved SSR."""

    k: list[float]
    baseVol: list[float]
    shiftedVol: list[float]
    ssr: float
    regime: str


# ------------------------------------------------------- fast spot-move state
class SpotShiftRequest(BaseModel):
    """Set a ticker's hypothetical/live spot move (no recalibration).

    ``spotReturn`` is the proportional move vs the anchor spot the fits were
    calibrated at (e.g. 0.02 for +2%); 0 returns to the anchor. The whole
    surface (smile, term, LV grid) is transported analytically on the next read
    via volfit.dynamics.transport — calibration only happens on an explicit
    "Calibrate" (POST /spot/{ticker}/calibrate).
    """

    spotReturn: float = 0.0


class SpotState(BaseModel):
    """The active spot-move state of a ticker (the no-recal transport view)."""

    ticker: str
    anchorSpot: float  # spot the cached fits were calibrated at
    spotReturn: float  # active proportional shift (0 = anchored)
    shiftedSpot: float  # anchorSpot * (1 + spotReturn)
    regime: str  # active vol-spot dynamics regime label
    regimeSsr: float  # its skew-stickiness ratio (transport strength R)


class LiveSpot(BaseModel):
    """A real-time spot probe versus the anchor (for spotMode='realtime')."""

    ticker: str
    anchorSpot: float
    liveSpot: float
    spotReturn: float  # implied liveSpot / anchorSpot - 1


# ------------------------------------------------------ calibration workflow
class ActivityInfo(BaseModel):
    """The fine-grained engine activity in flight (volfit.api.activity), narrated
    to the bottom status bar. ``active`` false => the engine is idle."""

    active: bool = False
    stage: str = ""  # fetch | calibrate | localvol | term | density | surface
    message: str = ""  # primary line, e.g. "Calibrating SPY 2026-07-17 (LQD)"
    detail: str = ""  # secondary line, e.g. "de-americanizing"
    done: int = 0  # progress numerator (0 with total 0 => indeterminate)
    total: int = 0  # progress denominator
    seq: int = 0  # monotonic; advances on every change


class CalibrationStatus(BaseModel):
    """State of the background calibration job + stale-node accounting."""

    running: bool
    total: int  # nodes in the current/last job
    done: int  # nodes calibrated so far
    current: str  # "TICKER EXPIRY" in flight, "" when idle
    phase: str = ""  # coarse phase of the in-flight item: "Parametric" | "LV"
    error: str  # last per-node error (the job never aborts on one bad node)
    cancelled: bool
    litNodes: int  # total lit (calibratable) nodes in the universe
    staleNodes: int  # lit nodes whose displayed fit has drifted from its last fit
    spotVersion: int  # global spot-move counter (bumps on any transported move)
    #: Monotonic calibration epoch (AppState.calib_epoch): advances whenever a
    #: re-calibration changes an already-calibrated node's displayed fit. The
    #: frontend refetches every mounted view the moment it advances — a
    #: level-triggered sync robust to missed job edges / background calibrations.
    epoch: int
    #: The fine-grained engine activity in flight (what the engine is doing right
    #: now), narrated to the bottom status bar. Idle when nothing is running.
    activity: ActivityInfo = ActivityInfo()


class FetchRequest(BaseModel):
    """Optional ticker subset for a fetch / calibrate action (None = all active)."""

    tickers: list[str] | None = None


class FetchResult(BaseModel):
    """Outcome of a spots / options fetch action."""

    tickers: list[str]  # tickers actually fetched
    spots: dict[str, float]  # ticker -> spot (live for spots, chain for options)
    calibrationStarted: bool  # whether auto-calibrate kicked off a background job


class SchedulerStatus(BaseModel):
    """Backend scheduler state for the TopBar fetch controls."""

    running: bool  # the scheduler thread is alive
    spotMode: str  # "realtime" | "static"
    optionsFetchMode: str  # "auto" | "on_demand"
    autoCalibrate: bool
    localVolEnabled: bool  # whether LV is calibrated + the Local Vol tab is usable
    #: Seconds to the next auto options fetch / spot poll, or -1 when that mode
    #: is on-demand/static (so the UI shows a button instead of a countdown).
    secondsToNextOptions: float
    secondsToNextSpot: float


# ------------------------------------------------------------------ local vol
class LocalVolGridResponse(BaseModel):
    """Extracted Dupire local-vol grid of a ticker plus no-arb diagnostics.

    ``sigma[i][j]`` is the local vol of forward-variance bucket i (between
    listed expiries, sampled at the bucket midpoint) at log-moneyness k[j];
    ``minDensity``/``calendarViolation`` are the discrete PDE residuals of
    volfit.models.localvol.model (scheme noise, gated by ``arbitrageFree``),
    ``nNan``/``nClipped`` count extraction repairs (Dupire denominator <= 0,
    variance floored).
    """

    ticker: str
    expiries: list[str]
    t: list[float]  # expiry year fractions (bucket right edges)
    k: list[float]  # log-moneyness nodes
    sigma: list[list[float]]  # local vols, one row per bucket
    nNan: int
    nClipped: int
    minDensity: list[float]
    calendarViolation: list[float]
    arbitrageFree: bool


# ------------------------------------------------------------ term structure
class EventSpec(BaseModel):
    """One scheduled event of the dilated clock: ``weight`` years of extra
    diffusion time lumped at year-fraction ``time`` (volfit.calib.event_time).
    Pydantic enforces time > 0 and weight >= 0, so bad specs are 422s."""

    time: float = Field(gt=0)
    weight: float = Field(ge=0)
    label: str = ""


class EventCalendar(BaseModel):
    """A ticker's persisted event calendar (GET/PUT /events/{ticker}).

    The event list is shared per-ticker state so it survives Parametric tab
    switches and ticker changes (volfit.api.state.AppState), instead of living
    only in the Term sub-tab's view-local state."""

    events: list[EventSpec] = Field(default_factory=list)


class EventAutocalibrateRequest(BaseModel):
    """Auto-calibrate the event calendar from the ATM term structure.

    ``maxExpiry`` is the horizon: one candidate event is placed before each
    expiry at or before it, and their day-weights are solved (all at once) so the
    weighted forward variance up to the interval just past the horizon is as flat
    and monotone-increasing as possible, with events as small and sparse as
    possible (volfit.calib.event_autocalibrate). Replaces the existing calendar."""

    maxExpiry: str  # ISO date: no events are added beyond this expiry
    fitMode: FitMode = "mid"


class TermStructureRequest(BaseModel):
    """ATM term structure of one ticker under an optional event calendar."""

    fitMode: FitMode = "mid"
    events: list[EventSpec] = Field(default_factory=list)
    eventsEnabled: bool = True


class TermPoint(BaseModel):
    """One fitted expiry on the term structure (calendar and dilated time)."""

    expiry: str  # ISO date
    t: float  # calendar year fraction
    tau: float  # event-dilated time tau(t)
    atmVol: float  # exact ATM handle sigma_0 (same fit as GET /smiles)
    w0: float  # ATM total implied variance
    varSwapVol: float  # model fair var-swap vol = sqrt(var-swap strike / t)
    varSwapQuote: float | None = None  # user-quoted var-swap vol (None if unset)
    varSwapExcluded: bool = False  # quote present but excluded from the fit
    maxIvErrorBp: float
    #: Active fetched prior's ATM vol at this expiry, transported to the current
    #: forward (dotted spot-updated prior term line); None when no active prior.
    priorVol: float | None = None


class TermCurve(BaseModel):
    """Dense ATM total-variance curve, linear in event-dilated time."""

    t: list[float]
    tau: list[float]
    w: list[float]
    vol: list[float]  # sqrt(w / t)


class DividendMarker(BaseModel):
    """One discrete dividend ex-date positioned on the term-structure axis.

    Emitted only when the ticker's dividend mode uses the discrete schedule
    (volfit.data.dividends): the forward already drops across each ex-date, so
    these are drawn as informational markers on both the real-time (``t``) and
    event-dilated (``tau``) maturity axes.
    """

    exDate: str  # ISO date
    t: float  # ex-date year fraction
    tau: float  # event-dilated position of the ex-date
    amount: float  # cash amount or proportional fraction (per the active mode)


class TermStructureResponse(BaseModel):
    """Per-expiry points plus the dense interpolated curve, nearest first."""

    ticker: str
    points: list[TermPoint]
    curve: TermCurve
    calendarViolations: int  # adjacent expiry pairs with w0 strictly falling
    dividends: list[DividendMarker] = []  # discrete ex-dates within the range


# ------------------------------------------------------------------- density
class DistributionArrays(BaseModel):
    """Risk-neutral log-return density and quantile function of one slice.

    (x, density) chart f_X on x = Q(z); (u, quantile) chart Q(u). All four
    arrays live on the same trimmed/strided quadrature grid, so they share
    one length and align point-for-point. ``u``/``quantile`` are optional — a
    density-only curve (the left-extended stacked overlay) omits them.
    """

    x: list[float]
    density: list[float]
    u: list[float] = []
    quantile: list[float] = []


class DensityResponse(BaseModel):
    """Current fit's distribution plus the saved prior's (null if unsaved)."""

    current: DistributionArrays
    prior: DistributionArrays | None = None


class StackedDensityItem(BaseModel):
    """One expiry's risk-neutral density for the stacked-densities view: the
    pdf f_X on the log-return grid x (the displayed model's own density)."""

    expiry: str
    t: float
    x: list[float]
    density: list[float]
    #: Per-expiry axis context, so the overlay's x-axis can switch to strike /
    #: %ATM / Δ / normalized exactly like the Smile view (every expiry has its own
    #: forward, ATM vol and smile, so the transform is per-curve).
    forward: float = 0.0
    atmVol: float = 0.0
    vol: list[float] = []  # displayed-model IV at each x (for the Δ axis)


class StackedDensityResponse(BaseModel):
    """Risk-neutral densities of every fitted expiry of a ticker, nearest first
    (the Parametric 'Stacked densities' view — all curves overlaid show they
    stay non-negative, i.e. no butterfly arbitrage)."""

    ticker: str
    expiries: list[StackedDensityItem]
