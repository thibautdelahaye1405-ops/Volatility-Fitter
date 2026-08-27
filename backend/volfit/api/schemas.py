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
    CarryCurveResponse,
    CarryPoint,
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
    weights): "equal" (unit weights, the historical scheme), "tv_density"
    (time-value density weights — economic time-value shape with the strike
    oversampling divided out), "vega_density" (Black-vega shape, same density
    correction — the flattest into the wings) or "delta_density" (OTM |forward
    delta| shape, same density correction — between vega and time value in
    wing decay); it applies in every fit mode and to every model.
    """

    model: Literal["lqd", "svi", "sigmoid"] = "lqd"
    # Legendre order N of the LQD slice. Default 16: N=6-12 leaves an
    # equioscillating truncation residual at the smile shoulder on low-vol
    # wide-z names (SPY LEAPs: +-20bp vs 3bp spreads); the cap 24 is where the
    # shoulder error reaches spread level on the reference SPY surface.
    nOrder: int = Field(16, ge=4, le=24)
    #: LQD optimization chart (volfit.models.lqd.charts): "lr" (historical
    #: raw (L, R, a) vector), "endpoint" ((log A_L, log A_R, a) — body modes
    #: endpoint-neutral so acute central convexity can't mechanically drag
    #: the asymptotic wings) or "logistic" (endpoint chart with
    #: A_R = expit(rho): the admissibility wall A_R < 1 is unreachable, the
    #: chart covers exactly the admissible set — committee revision R1, the
    #: production default). Same family/objective in all three, so the
    #: fitted optimum is chart-independent to solver tolerance.
    lqdCoords: Literal["lr", "endpoint", "logistic"] = "logistic"
    regLambda: float = Field(1e-6, ge=0.0, le=1.0)  # lam * n^{2r} a_n^2 damping
    regPower: float = Field(1.0, ge=0.0, le=4.0)  # the r in n^{2r}
    #: Generalized LQD tails (book ch. 2; tails+calendar arc Phase 2): fixed
    #: per-side tail exponents in [0, 1/2] — 0 = exponential (the historical
    #: model, byte-identical default), 1/2 = Gaussian rate, asymmetric values
    #: allowed. POLICY inputs (the scenario instrument), never optimized: the
    #: alpha -> 0 limit is nonuniform, so per-slice estimation is
    #: ill-conditioned by construction. LQD-only (overlays ignore them).
    tailAlphaLeft: float = Field(0.0, ge=0.0, le=0.5)
    tailAlphaRight: float = Field(0.0, ge=0.0, le=0.5)
    #: Per-underlier overrides of the pair above (arc Phase 3 — the ratified
    #: alpha scope is per-underlier, common across that underlier's
    #: expiries): ticker -> [alpha_left, alpha_right]. An absent ticker uses
    #: the global pair; entries are validated to the same [0, 1/2] range.
    tailAlphaByTicker: dict[str, tuple[float, float]] = {}

    @field_validator("tailAlphaByTicker")
    @classmethod
    def _alpha_overrides_in_range(
        cls, v: dict[str, tuple[float, float]]
    ) -> dict[str, tuple[float, float]]:
        for ticker, pair in v.items():
            if not all(0.0 <= a <= 0.5 for a in pair):
                raise ValueError(
                    f"tailAlphaByTicker[{ticker!r}] = {pair} outside [0, 1/2]"
                )
        return v

    def tail_alphas(self, ticker: str) -> tuple[float, float]:
        """The (alpha_left, alpha_right) pair governing ``ticker``'s fits."""
        pair = self.tailAlphaByTicker.get(ticker)
        if pair is not None:
            return float(pair[0]), float(pair[1])
        return self.tailAlphaLeft, self.tailAlphaRight
    nCores: int = Field(2, ge=0, le=2)  # Multi-Core SIV hat count R (sigmoid only; capped at 2)
    haircut: float = Field(0.005, ge=0.0, le=0.05)  # haircut-mode band shrink (vol)
    weightScheme: Literal["equal", "tv_density", "vega_density", "delta_density"] = (
        "equal"
    )  # per-quote weights
    # --- per-model optimization / penalty coefficients (Options exposes them
    # all explicitly; every default equals the historical hardcoded constant, so
    # a default fit is byte-identical to before they were tunable) ---
    barrierCenter: float = Field(0.90, gt=0.0, lt=1.0)  # LQD A_R soft-barrier centre
    barrierScale: float = Field(50.0, gt=0.0)  # LQD A_R soft-barrier steepness
    sviPenaltyWeight: float = Field(1e3, ge=0.0)  # SVI no-arb soft-penalty weight
    # SVI Lee wing-slope cap. STRICTLY buffered under Lee's bound of 2 since
    # committee revision R1 (2026-07-24): beta = 2 itself admits negative
    # tail density (the hinge was zero exactly on the broken boundary).
    leeSlopeMax: float = Field(1.95, gt=0.0)
    #: Committee R3: SVI optimization chart. "structural" =
    #: (beta_L, beta_R, k*, w*, kappa*) with lifts — every finite iterate
    #: strictly positive-floor and strictly Lee-clean, the penalties inert.
    #: DEFAULT since the benchmark adjudication (ratified 2026-07-26,
    #: FINDINGS_svi_chart.md): better/equal precision in all 12 regime
    #: medians, zero breaks, 594 vs 9,472 eval-cap exhaustions, ~3x faster;
    #: the raw chart's lower headline arb rate was a survivorship artifact
    #: of its non-converged third. "raw" = the historical vector, kept for
    #: comparability and rollback.
    sviChart: Literal["raw", "structural"] = "structural"
    #: Committee R2 rider: when a display fit fails the belly butterfly
    #: certificate, refit ONCE with the belly hinge and keep the repair if it
    #: certifies. Clean first fits never see a second solve.
    bellyRepair: bool = True
    sigmoidRidge: float = Field(1e-2, ge=0.0)  # Multi-Core SIV hat-amplitude ridge
    #: V3.1 (roadmap item 2 leg 3): Multi-Core Sigmoid optimization chart.
    #: "structural" = the (β_L, β_R, z*, v*, κ_p, κ_c) chart of
    #: models/sigmoid/structural.py — the base's k-space Lee wing slopes
    #: (eq mcsbetak) lifted logistically against the buffered leeSlopeMax cap,
    #: so every finite iterate has strictly Lee-clean base wings. DEFAULT "raw"
    #: (byte-identical historical vector) until the adjudication sweep ratifies
    #: a flip — the sviChart precedent (pre-registered benchmark, then flip).
    mcsChart: Literal["raw", "structural"] = "raw"
    midAnchorWeight: float = Field(0.05, ge=0.0)  # band-mode mid anchor (all models)
    # --- short-dated objective knobs (2026-08-25 ruggedness diagnosis; every
    # default is byte-identical — flips ride benchmark adjudication) ---
    #: Tau-aware mid-anchor attenuation: when set (years), the band-mode mid
    #: anchor is scaled by min(1, sqrt(tau / midAnchorTauRef)). The data rows
    #: blow up ~1/sqrt(tau) at short maturities while the shape ridge is
    #: tau-free, so at 1 week the tick-quantized mid staircase outguns the
    #: regularization ~7x — this restores a maturity-uniform anchor-vs-shape
    #: contest. None = off (the historical constant anchor).
    midAnchorTauRef: float | None = Field(None, gt=0.0, le=5.0)
    #: IV-space band half-width floor in TICKS: in bid-ask / haircut mode each
    #: quote's target band is widened about its mid to at least the IV width
    #: of this many price ticks at the quote's vega, so a short-dated wing
    #: quote whose spread prints below the tick grid cannot claim sub-tick IV
    #: certainty. 0 = off (byte-identical); needs the chain's tick size
    #: (real feeds — synthetic/tickless chains are unaffected).
    bandTickFloorTicks: float = Field(0.0, ge=0.0, le=20.0)
    #: Robust loss on the DATA rows only, via IRLS reweighting — scipy's
    #: global loss would also soften the no-arb penalty/calendar rows, which
    #: must stay quadratic. After the base fit, quote-row residuals beyond
    #: ``robustFScale`` are down-weighted (huber: 1/|r| taper; cauchy:
    #: 1/(1+r^2) — harder) and the slice refits warm-started (two passes).
    #: "off" = single fit, byte-identical.
    robustLoss: Literal["off", "huber", "cauchy"] = "off"
    #: Robust scale in the residual's own units (vol for vol-space residuals;
    #: vega-normalized price ~ vol for LQD). Residuals under it keep full
    #: weight. Read only while ``robustLoss`` is on.
    robustFScale: float = Field(0.005, gt=0.0, le=1.0)
    #: R1 deferral closed, opt-in: SVI / MCS residuals switch from raw-vol
    #: space to the LQD convention — vega-normalized PRICE residuals (vega
    #: frozen at the mid, floored) — so a far-wing short-dated quote's
    #: multi-vol-point IV quantum stops entering the objective at full
    #: weight. OFF = the historical vol-space residuals, byte-identical.
    overlayPriceResiduals: bool = False

    @field_validator("nCores", mode="before")
    @classmethod
    def _clamp_cores(cls, v: int) -> int:
        """SIV cores capped at 2 (FINDINGS R6: cores ≥3 overfit + manufacture wing
        arb). Clamp rather than reject so a persisted desk with nCores>2 still loads."""
        return min(int(v), 2)


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
    #: Data-age staleness thresholds (minutes) for LIVE real-feed chains
    #: (volfit.api.data_age): past ``dataAgeAmberMin`` the market pill turns
    #: amber (advisory — e.g. the delayed tier's 15 min lag); past
    #: ``dataAgeRedMin`` it turns red and the quality report fails the node's
    #: publish-readiness (a premarket fetch of yesterday's book must not read
    #: 13/13 ready). Display/report policy only — never bumps the options
    #: version, never touches a fit.
    dataAgeAmberMin: float = Field(20.0, ge=1.0, le=1440.0)
    dataAgeRedMin: float = Field(120.0, ge=5.0, le=10080.0)
    # arbitrage / events / var-swap (wired as global defaults)
    enforceCalendar: bool = True
    #: Calendar-coupled surface solver (with ``enforceCalendar`` on).
    #: "symmetric" (production): fit every expiry independently, screen each
    #: adjacent interface for an IDENTIFIED violation (normalized-call order
    #: on the common quote support), then jointly Gauss-Newton-repair only the
    #: violation-connected components — no traversal-order bias, corrections
    #: allocated by data information (volfit.calib.symmetric). "sequential":
    #: the historical nearest-to-farthest pass threading the previous slice as
    #: a one-sided floor. Changes calibration output -> bumps the options
    #: version.
    surfaceSolver: Literal["symmetric", "sequential"] = "symmetric"
    #: Tapered no-arb enforcement in the extrapolated strike region (Notes
    #: 09/10 Phase 2, volfit.calib.extrap): the SVI/MCS overlay fits gain a
    #: butterfly hinge on the time-value envelope, a tapered calendar hinge
    #: vs the previous displayed slice, and the wing-slope-order hinge. With
    #: the symmetric surface solver this ALSO arms the LQD tail contract —
    #: per-interface seam price ordering + linear wing-slope (log endpoint
    #: scale) ordering rows in the joint repair (volfit.calib.symmetric). OFF
    #: by default (byte-identical); affects calibration -> bumps the options
    #: version. Phase 1 (the Quality tab's advisory measurement) is always on.
    extrapEnforce: bool = False
    #: Promote the full-line certificate's TAIL-ORDER clause (the limiting
    #: tail order of adjacent slices, ``ledgerTailOrderOk``) from advisory to
    #: a gate (V3.0 rider): the active-set exchange treats a tail-order
    #: failure like a ledger-gap failure (the λ± seam rows at common α are its
    #: repair path — unequal α is irreducible by construction), the Quality
    #: readiness issue list names it and the publish export blocks on it.
    #: OFF by default (byte-identical, Phase-0 advisory policy); affects the
    #: surface repair -> bumps the options version.
    ledgerTailOrderGate: bool = False
    #: Quote-band relaxation infeasibility diagnostic (V3.0 rider, book ch. 2
    #: §calendar): after the surface pass, for every adjacent pair the
    #: exchange could NOT certify, bisect the smallest symmetric quote-band
    #: widening (vol units) under which the pair certifies, and report it on
    #: the Quality node (``bandRelaxationVol``) + export notes. Advisory —
    #: the accepted surface is untouched (never bumps the options version);
    #: only runs in band fit modes on uncertified pairs. OFF by default.
    bandRelaxationDiagnostic: bool = False
    #: Overlay calendar-floor scope (the short-dated upside-crossing fix):
    #: None = the historical per-family grids (SVI floor/ceiling confined to
    #: the COMMON quote support; MCS winged at 2 sigma). A value = BOTH
    #: overlay families build their calendar floor/ceiling grids winged this
    #: many sigma_ref*sqrt(T) beyond the common support
    #: (volfit.calib.calendar.variance_floor_grid_winged), so the displayed
    #: overlays keep calendar order out into the wing where the optical
    #: stacked-IV crossings live. Calibration-affecting -> bumps the options
    #: version.
    calendarFloorPadZ: float | None = Field(None, gt=0.0, le=8.0)
    #: Calendar context on SINGLE-NODE refits. The workflow caveat
    #: (workflow_stages): an independent recompute of one node (autoCalibrate
    #: tick, quote edit, undo) has no cross-expiry context, so it silently
    #: voids the surface pass's coupling until the next full Calibrate. When
    #: on (and ``enforceCalendar``), a single-node fit threads the ADJACENT
    #: committed displayed slices as its confined floor (previous expiry) and
    #: ceiling (next expiry) — the sequential-pass construction. OFF by
    #: default (byte-identical). Calibration-affecting -> bumps the options
    #: version.
    calendarOnRefit: bool = False
    #: R2 item 11 (increment 2): route the JOINT borrow/de-Am fixed point's
    #: converged (forward, discount) into the resolved forwards the fits
    #: consume — American chains only, engaged PER EXPIRY and only when the
    #: converged |borrow| is at least ``jointCarryEngageBp`` (below it the
    #: parity forward is kept EXACTLY, so ordinary names stay byte-identical
    #: even with the toggle ON — the item's day-one bar). OFF by default;
    #: both knobs bump the options version (resolved forwards feed every fit).
    jointCarry: bool = False
    jointCarryEngageBp: float = Field(25.0, ge=0.0, le=10000.0)
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
    # ---- 0DTE research clock (roadmap R2 item 10) ----
    #: Sub-day maturities: value each node from the chain snapshot's timestamp
    #: to the expiry's exact SETTLEMENT instant (the schema-v7 settlement map;
    #: NYSE session rules as fallback) instead of integer calendar days, and
    #: accrue variance time through the session-weighted intraday profile
    #: (volfit.calib.intraday_time). OFF by default — byte-identical fits.
    #: Affects calibration -> bumps the options version.
    intradayClock: bool = False
    #: Fraction of a trading day's variance that accrues DURING the exchange
    #: session (09:30 ET to the close; half-day sessions scale it). The default
    #: 6.5/24 is the flat-density share that nests the legacy day convention;
    #: research values (~0.7-0.9) make a live 0DTE's clock "remaining trading
    #: minutes" and the overnight cheap. Only read while ``intradayClock`` is
    #: on; affects calibration -> bumps the options version.
    sessionVarShare: float = Field(6.5 / 24.0, ge=0.0, le=1.0)
    #: Day-weight of a NON-trading calendar day (weekends, exchange holidays)
    #: on the intraday clock — the weekend-effect research lever. 1.0 (the
    #: default) keeps the legacy convention where a 3-day weekend costs three
    #: full days of variance. Only read while ``intradayClock`` is on; affects
    #: calibration -> bumps the options version.
    nonTradingWeight: float = Field(1.0, ge=0.0, le=1.0)
    varSwapEnabled: bool = True
    #: Var-swap penalty weight as a PERCENTAGE of the summed option-quote weights
    #: of the same (asset, expiry) node (volfit.api.varswap.varswap_target): at
    #: 100% an active var-swap quote weighs as much as all option quotes combined.
    #: Changes calibration output, so it bumps the options version (set_options),
    #: and only matters while ``varSwapEnabled`` is on.
    varSwapWeightPct: float = Field(10.0, ge=0.0, le=1000.0)
    #: Hard var-swap pinning (forward-roadmap-v3 V3.6 rider): when on, the
    #: MARKET var-swap quote row's weight is escalated by the stiff-row
    #: multiplier (volfit.calib.varswap.VARSWAP_PIN_MULT) so the fitted
    #: var-swap level matches the quote to solver tolerance — the codebase's
    #: equality-constraint idiom (the 1e6 calendar rows). PRIOR var-swap rows
    #: stay soft: pinning to a stale prior would be dangerous. OFF by default
    #: (byte-identical); calibration-affecting -> bumps the options version.
    varSwapHardPin: bool = False
    #: How the Local-Vol fit prices the model variance swap. "static" is the
    #: log-contract strike replication of the option surface (the k^-2-weighted
    #: integral); "source_pde" is the backward source PDE g(0,1)
    #: (volfit.models.localvol.varswap_pde) — a LOCAL quantity, far less sensitive
    #: to coarsening/truncating the strike grid in the wings (needed once the
    #: calibration grid is coarsened; Stage 3). Calibration-affecting (bumps the
    #: options version); parametric models always use the static replication.
    varSwapMethod: Literal["static", "source_pde"] = "static"
    # prior default. LEGACY (Phase 8): ``priorPersistenceMode`` is now the single
    # source of truth for prior gating; this field is retained only so a pre-mode
    # persisted blob can be migrated to a mode on store load (settings_persist) and
    # for round-trip back-compat. It no longer gates calibration.
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
    #: Tail-persistence carrier of the PRIOR var-swap companion row:
    #: "absolute" = match the prior's var-swap vol level (historical);
    #: "atm_spread" = match the prior's var-swap MINUS ATM vol SPREAD — the
    #: tail-mass-over-body carrier, so a level move (e.g. filter-driven ATM
    #: update) carries the tail along instead of fighting a stale absolute
    #: level. Market var-swap quotes are always absolute (they are the
    #: truth). Calibration-affecting -> bumps the options version.
    priorVarSwapMode: Literal["absolute", "atm_spread"] = "absolute"
    #: Wing-slope operator scale: the WingL / WingR members of
    #: ``priorOperatorSet`` persist each side's deep-wing vol SLOPE between
    #: the two outermost prior-anchor deltas (volfit.calib.operators) — the
    #: Lee-asymptote-adjacent tail-shape carrier the design note's §5 lists
    #: as the optional extension. Gap-gated like every operator; this factor
    #: scales the two wing rows' budget share relative to the body operators.
    priorWingSlopeScale: float = Field(1.0, ge=0.0, le=10.0)

    @field_validator("priorOperatorSet")
    @classmethod
    def _clean_operators(cls, v: list[str]) -> list[str]:
        """Keep known operator names in declaration order (dedup); empty -> default.

        Known: ATM, RR25/BF25 (25-delta), RR10/BF10 (10-delta), WingL/WingR
        (per-side deep-wing slope), VarSwap. Mirrors the registry in
        volfit.calib.operators so the UI cannot persist an op the builder
        does not know."""
        known = ["ATM", "RR25", "BF25", "RR10", "BF10", "WingL", "WingR", "VarSwap"]
        kept = [op for op in known if op in set(v)]
        return kept or ["ATM", "RR25", "BF25", "VarSwap"]

    @field_validator("priorFactorSet")
    @classmethod
    def _clean_factors(cls, v: list[str]) -> list[str]:
        """Keep known factor names in canonical order (dedup); empty -> default."""
        known = ["ATM", "skew", "curvature", "leftWing", "rightWing", "VarSwap"]
        kept = [f for f in known if f in set(v)]
        return kept or ["ATM", "skew", "curvature", "VarSwap"]

    # ---- observation Kalman filter (Docs/kalman_filtering.tex, Note 15) --------
    #: Temporal observation filter over the smile handles (ATM vol / skew /
    #: curvature). ``off`` = feature absent (byte-identical); ``overlay`` =
    #: predict/update per snapshot and DRAW the filtered state, calibration
    #: untouched (the pilot mode); ``active`` = the Kalman prediction prior enters
    #: the fit as a one-stage MAP residual block (note eq. active-map) — never a
    #: second pass over the same quotes. Only the off<->active transition affects
    #: fits (see set_options); overlay changes bump the lightweight filter version.
    observationFilterMode: Literal["off", "overlay", "active"] = "off"
    #: Measurement-covariance route (note §4): ``jacobian`` = R propagated from the
    #: fit's solution Jacobian, R = rho * G (J^T W J)^+ G^T (eq. cov-delta) — the
    #: default; ``factors`` = the cheap precision-factor builder (eq. cheapR),
    #: kept as the fallback + A/B diagnostic.
    filterCovarianceMode: Literal["jacobian", "factors"] = "jacobian"
    #: ATM-level process noise in vol BP per sqrt(calendar day) (eq. Q clock term).
    #: Default 30 (was the note's 10): the 3-regime Phase-7 backtest is one-sided —
    #: at 30 the posterior is calibrated (zeta std 0.8-1.9 vs 1.3-6.2 at 10) and
    #: shock lag drops 3-8x, in every regime and on both covariance routes
    #: (backtest/FINDINGS_observation_filter.md).
    filterProcessVolBpSqrtDay: float = Field(30.0, ge=0.0, le=1000.0)
    #: Skew / curvature process-noise scales per sqrt(calendar day).
    filterProcessSkewSqrtDay: float = Field(0.02, ge=0.0, le=10.0)
    filterProcessCurvSqrtDay: float = Field(0.05, ge=0.0, le=10.0)
    #: Extra process std per unit |log-forward| transport distance (eq. Q spot term;
    #: the same intuition as the prior-persistence transport factor).
    filterTransportNoiseScale: float = Field(0.10, ge=0.0, le=10.0)
    #: Inflate R by the realized fit inconsistency rho = clip(chi^2/(m-d), 1, cap)
    #: (eq. resid-inflation) so a dense-but-contradictory cluster reads as noise.
    filterResidualInflation: bool = True
    #: Innovation-gated adaptive process noise (FINDINGS F4, the shock-lag fix):
    #: when a handle's standardized innovation exceeds this many sigmas, P- is
    #: inflated so the surprise reads as ~this level and the gain rises toward
    #: the data. 0 = off. Clean days never trip it; a contradictory chain's
    #: rho-inflated R keeps it quiet. Overlay: gated on today's innovation.
    #: Active (F10): the level row is gated by a fit-free ATM probe of the
    #: prepared mids, the shape rows by the previous step's innovation.
    filterAdaptiveSigma: float = Field(3.0, ge=0.0, le=20.0)
    #: Pilot safety cap on the diagonalized per-handle gains; 1.0 = no cap binding
    #: in normal operation (the update itself keeps K in [0, 1] per handle).
    filterMaxGain: float = Field(1.0, ge=0.0, le=1.0)
    #: Maximum data gap (hours) the filter will PREDICT across; a longer gap resets
    #: the state instead (reset_reason="stale"). Default spans a weekend + holiday.
    filterResetHours: float = Field(96.0, gt=0.0, le=720.0)
    #: Clock the process noise accrues on. "calendar" = wall-clock days (the
    #: legacy convention — byte-identical default). "session" = the intraday
    #: variance clock (calib/intraday_time): a session carries
    #: ``filterSessionShare`` of a day's variance, a non-trading day
    #: ``filterNonTradingWeight``. Measured on the 2026-07 0DTE campaign
    #: (backtest/observation_filter_intraday, 936 measurements): 30-min steps
    #: move ATM 19.5 bp, one overnight 55 bp, a whole WEEKEND also 55 bp — no
    #: calendar q calibrates all three (best: zeta 1.04/0.53/0.23), while
    #: share 0.60 / weight 0.0 at q=90 bp gives zeta 0.95/0.89/0.84. The reset
    #: rule stays on calendar hours (staleness is about data age, not variance).
    filterClock: Literal["calendar", "session"] = "calendar"
    filterSessionShare: float = Field(0.60, ge=0.0, le=1.0)
    filterNonTradingWeight: float = Field(0.0, ge=0.0, le=1.0)
    #: Measurement pass: fit data-only first (persistence priors off) so z_t is a
    #: clean market observation, then run the committed fit as usual. Off = reuse
    #: the committed fit's handles and flag contamination (note §5.1; the same
    #: cost trade-off as ``priorDataOnlyPrepass``).
    filterDataOnlyPrepass: bool = False

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
    #: Minimum strike vertices guaranteed INSIDE each expiry's OWN traded range
    #: (fix #1 for short-dated LV). The delta axis is sized to the LONGEST expiry
    #: and clipped to the GLOBAL strike range, so a narrow SHORT smile can land only
    #: a few vertices on its sharpest curvature (measured: a 6-DTE SPY weekly got
    #: 3 -> 108 bp LV RMS, vs ~28 bp once it reaches ~8). The shared axis's widest
    #: in-range gaps are split until each expiry has at least this many vertices, so
    #: ONLY under-resolved (short-front) expiries gain nodes — well-covered normal
    #: expiries are untouched (often byte-identical). 0 = off (legacy axis).
    gridXMinPerExpiry: int = Field(8, ge=0, le=60)
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
    #: LV PDE lattice right edge FLOOR in moneyness x = K/F (V3.3 rider): the
    #: lattice runs to x_max = max(1.4 × the highest quoted x, lvXMaxMin), and
    #: the right wing of every LV view is capped at k = ln(x_max) because
    #: prices beyond the lattice would be clamped garbage. 2.5 (the default,
    #: k ≈ +0.92) is byte-identical to the historical constant; raising it
    #: (e.g. 2.72 → k = +1.0, 4.0 → k ≈ +1.39) extends the untruncated right
    #: wing of the stacked-variance / display grids at O(n_x) march cost.
    #: LV-only: folded into affine_key, does not bump the options version.
    lvXMaxMin: float = Field(2.5, ge=2.5, le=10.0)
    # editable penalty strength (changes calibration output)
    calendarWeight: float = Field(1e6, ge=0.0)
    #: Multi-Core SIV put-wing no-butterfly regularizer strength, as a percentage of
    #: the base weight (FINDINGS_calibration_arb R6). 100 = the default Durrleman
    #: penalty that pushes g(k) >= 0 in the unquoted wings; 0 = off (byte-identical).
    #: Zero on an arb-free slice, so liquid names are untouched regardless.
    sivWingPenaltyPct: float = Field(100.0, ge=0.0, le=1000.0)
    # graph-solver prior defaults (the Graph SolverPanel seeds from these):
    # kappa = prior strength (local precision toward baseline), eta = reach,
    # lambda = OT flux weight (0 = off), nu = OT source allowance.
    graphKappaScale: float = Field(1.0, gt=0.0)
    graphEtaScale: float = Field(1.0, ge=0.0)
    graphLambdaScale: float = Field(0.0, ge=0.0)
    graphNu: float = Field(0.1, gt=0.0)
    #: Default propagation operator for the production graph solve (message
    #: arc P3, Docs/graph_precision_message_framework.md §18.1). The frontend
    #: seeds its mode selector from this. DEFAULT = "precision_messages"
    #: (USER-RATIFIED FLIP 2026-07-27, FINDINGS_message_phase4.md: the daily
    #: §22.4 gate did not clear, but intraday the legacy operator is nearly
    #: inert — 168.6bp vs 172.7 transport — while messages carry the signal
    #: at 65.8bp). "smooth_field" stays explicit configuration/rollback, and
    #: remains the WIRE default on GraphExtrapolateRequest (replay,
    #: byte-identity locks and the backtest harness are untouched). Old
    #: persisted blobs lack the field and coerce to the default; a store
    #: that ever saved Options pins its explicit value until re-save.
    graphPropagationMode: Literal[
        "smooth_field", "precision_messages", "hybrid"
    ] = "precision_messages"
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
    #: Unified snapshot fetch (POST /fetch/snapshot, V3.7 item 15): ON = after the
    #: chains are refreshed and the spot transported, roll each ticker's ACTIVE
    #: prior to its latest SAVED snapshot — the O(1) saved branch of the freshness
    #: ladder ONLY (never the prev-close recalibration, never an as-of flip) — so
    #: the calibration that follows anchors on the freshest saved prior. OFF
    #: (default) = the snapshot verb is byte-identical to the legacy
    #: fetch_options + fetch_spots sequence. Pure workflow gate — never bumps the
    #: options version (a roll bumps the per-ticker active-prior version instead).
    autoRollPriorOnFetch: bool = False
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
    #: Scheduler consolidation onto the unified snapshot verb (V3.7 rider):
    #: ON = the ``optionsFetchMode == "auto"`` timer runs the SAME sequence as
    #: POST /fetch/snapshot (chains → spot transport → optional prior roll →
    #: optional autoCalibrate) instead of the bare chain refetch, and the
    #: double-fire guard re-arms the spot timer on every snapshot tick (a
    #: realtime spot poll due on the same tick is absorbed, never fired twice).
    #: OFF (default) = the legacy split timers, byte-identical. Pure workflow
    #: gate — never bumps the options version.
    schedulerUnifiedFetch: bool = False
    #: While a real-time book is streaming (Massive WS / Bloomberg //blp/mktdata,
    #: realtime spot mode), the scheduler
    #: refetches the chain from the book and recalibrates all lit nodes every
    #: ``streamRefitSeconds`` — a faster, book-driven loop distinct from the
    #: minutes-cadence ``optionsFetchMode == "auto"`` REST refetch.
    streamRefitSeconds: float = Field(5.0, gt=0.0, le=600.0)
    #: Auto-open the real-time push feed on a streaming-capable active source (the
    #: Massive WebSocket book, or Bloomberg's //blp/mktdata subscription book —
    #: quota-free vs the metered bdp path) so chain Fetch / Calibrate / spot serve
    #: from the fast in-memory book instead of the slow / metered snapshot pull.
    #: Independent of ``spotMode`` — the book just feeds fetches; live re-pricing /
    #: auto-refit stay gated on ``spotMode=="realtime"``. ON by default; OFF forces
    #: the request path. No effect on sources without a stream (Yahoo / Synthetic).
    autoStream: bool = True


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


class FilterDiagnostics(BaseModel):
    """Auditable observation-filter step for one node (Note 15 invariant 5:
    every filtered output reports prediction, observation, innovation, gain and
    posterior uncertainty). ``active=False`` when the filter is off or the node
    has no state yet; per-handle lists follow ``handleNames`` order. The curve
    fields carry the drawable overlay: the LQD backbone retargeted to the
    posterior handles (+ a level credible band) and to the transported
    prediction; empty when reconstruction fails (advisory payload)."""

    active: bool
    mode: str
    handleNames: list[str] = []
    provenance: str | None = None  # "seed:<prior source>" | "update"
    resetReason: str | None = None  # why the state was (re)seeded, else None
    contaminated: bool = False  # z taken from a persistence-anchored fit (§5.1)
    transportDistance: float | None = None  # |log-forward| moved since the prior state
    prediction: list[float] = []
    predictionStd: list[float] = []
    observation: list[float] = []
    observationStd: list[float] = []
    innovation: list[float] = []
    gain: list[float] = []  # diagonal of K
    posterior: list[float] = []
    posteriorStd: list[float] = []
    measurementBreakdown: dict[str, float] = {}
    processBreakdown: dict[str, list[float]] = {}
    #: Per-handle standardized innovation zeta = nu / sqrt(diag(P^- + R)),
    #: PRE-adaptive-inflation (V3.9 item 7 — the tuning verdict statistic:
    #: std(zeta) ~ 1 iff Q is scaled right). None when no update stored.
    zeta: list[float] | None = None
    #: Sum of zeta^2 over the handles — the STEP's whitened-innovation chi².
    #: Distinct from ``measurementBreakdown["chi2"]`` (present on the Jacobian
    #: route only): that one is the FIT's whitened residual chi², auditing how
    #: R was built, not how surprising the step was.
    chi2: float | None = None
    post: list[SmilePoint] = []  # smile retargeted to the posterior m+
    postBandLo: list[SmilePoint] = []  # m+ level - 1.96 sd(ATM)
    postBandHi: list[SmilePoint] = []  # m+ level + 1.96 sd(ATM)
    predCurve: list[SmilePoint] = []  # smile retargeted to the prediction m-


class FilterStepOut(BaseModel):
    """One committed observation-filter step from the in-memory history ring
    (V3.9 item 7). Compact scalars only — the drawable overlay curves stay on
    FilterDiagnostics (one retarget per committed state, never per history
    read). Per-handle lists follow the FILTER_HANDLES order (ATM, skew,
    curvature); ``dtDays`` is the process-noise time the ACTIVE clock actually
    charged for the step (0 on a seed/reset)."""

    ts: float  # snapshot epoch (seconds) the step committed at
    dtDays: float
    prediction: list[float] = []
    predictionStd: list[float] = []
    observation: list[float] = []
    observationStd: list[float] = []
    innovation: list[float] = []
    zeta: list[float] | None = None  # pre-inflation nu / sqrt(diag(P^- + R))
    gain: list[float] = []  # diagonal of K
    posterior: list[float] = []
    posteriorStd: list[float] = []
    #: Per-component Q variance vectors (clock/spot/event/source/model, plus
    #: "adaptive" when the innovation gate tripped).
    processBreakdown: dict[str, list[float]] = {}
    transportDistance: float | None = None
    provenance: str  # "seed:<source>" | "update" | "map"
    resetReason: str | None = None
    contaminated: bool = False


class FilterHistoryResponse(BaseModel):
    """GET /smiles/{t}/{e}/filter/history: the node's last <= 64 committed
    filter steps, oldest first. Read-only and poll-safe — never fits;
    ``active=False`` (empty steps) when the filter is off or nothing has
    committed yet. The ring clears with the filter states (source/as-of
    switch) and is workspace-persisted (the doc's ``filterHistory`` key
    carries these same step dicts), so it survives a workspace round-trip."""

    active: bool
    steps: list[FilterStepOut] = []


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
    #: The quote's strike — the layer-independent identity the Smile Viewer
    #: joins on (a calibration quote, the prevailing market quote and a live
    #: tick at the same strike are the same option) and places with
    #: ``log(strike / layer forward)``. Optional for older payloads / mock.
    strike: float | None = None
    #: Fit-target band edges resolved by the fit's OWN band rule (V3.4 item 4;
    #: volfit.calib.band.resolve_band via quotes.apply_band_edits, so
    #: amended-mid recentering and the haircut collapse-to-mid clamp are
    #: inherited): fit_mode "bidask" -> (bid, ask); "haircut" -> the
    #: mid-clamped (bid+h, ask-h). None under fit_mode "mid" (the target is
    #: the mid polyline). OPTIONAL additions to the frozen contract (the
    #: SmileData.stale precedent); excluded quotes still carry values.
    targetLo: float | None = None
    targetHi: float | None = None


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
    #: Quote-derived 1σ uncertainty of the LQD-backbone handles (Note 15 §4:
    #: the solver's solution Jacobian propagated through the handle map, with
    #: the bid-ask half-spread as the stated noise) — the chart's error bars.
    #: None when no calibration / the measurement failed (advisory channel).
    atmVolStd: float | None = None
    skewStd: float | None = None
    curvStd: float | None = None


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
    #: "fit" (calibrated here) | "loaded" (a snapshot file's calibration).
    provenance: str = "fit"
    label: str  # human family name ("LQD", "SVI-JW", "Multi-Core Sigmoid")
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
    # ---- V3.6 optional readouts (item 14). All default-None so older cached
    # payloads / mocks stay valid (frozen contract: additions are OPTIONAL). ----
    #: Quote-minus-model basis in VOL BASIS POINTS: (level − modelVol) · 1e4.
    #: Sign convention: positive ⇒ the quote sits ABOVE the model's own fair
    #: var-swap. None when no quote exists.
    basisBp: float | None = None
    #: OptionsSettings.varSwapWeightPct echoed at the point of use (the panel
    #: shows the penalty strength without a settings round-trip). None while
    #: ``varSwapEnabled`` is off.
    weightPct: float | None = None
    #: The RESOLVED absolute weight of the node's single var-swap residual:
    #: (varSwapWeightPct / 100) · Σ option-quote weights — exactly the value
    #: volfit.api.service.varswap_target feeds the calibrator. None when no
    #: ACTIVE target (feature off, no quote, or quote excluded).
    weightAbs: float | None = None
    #: Mirrors SmileData.stale for this node (inputs drifted since the last
    #: calibration — needs Calibrate). None when unknown (mock payloads).
    stale: bool | None = None
    #: Fraction of the node's total weighted SQUARED vol error contributed by
    #: the var-swap term (the volfit.calib.rms.node_error_terms decomposition),
    #: in [0, 1]. None when no active target or the total error is zero.
    rmsShare: float | None = None
    #: True when OptionsSettings.varSwapHardPin escalates THIS node's active
    #: market var-swap row to the stiff-row weight (volfit.calib.varswap.
    #: VARSWAP_PIN_MULT — equality to solver tolerance). False when the pin is
    #: off or no active target; None while var-swap quoting is disabled (and on
    #: older cached payloads / mocks — the frozen contract: additions optional).
    pinned: bool | None = None
    # ---- V3.6 rider: strip-vs-tails split of the var-swap replication
    # (volfit.calib.varswap.varswap_decomposition / volfit.api.varswap_split).
    # The model's replicated variance partitioned by strike region — the
    # quoted strip [stripKLo, stripKHi] (the INCLUDED quotes' log-moneyness
    # span) vs the extrapolated wings; every trapezoid cell of the replication
    # is assigned whole to one region by its midpoint, so the three shares sum
    # to one. Parametric nodes: the ±6 / 801-point replication of the displayed
    # slice; Local-Vol expiries: the static replication on the PDE lattice
    # (truncated at the lattice, right edge = x_max). READ-ONLY display —
    # nothing enters an objective. All None when nothing can be split. ----
    #: Fraction of the replicated total variance from the quoted strip, [0, 1].
    stripVarShare: float | None = None
    #: Fraction from the left (put) wing below stripKLo, [0, 1].
    tailVarShareLeft: float | None = None
    #: Fraction from the right (call) wing above stripKHi, [0, 1].
    tailVarShareRight: float | None = None
    #: Log-moneyness span of the INCLUDED quotes used for the split.
    stripKLo: float | None = None
    stripKHi: float | None = None


class MarketLayer(BaseModel):
    """The PREVAILING market of a node — Smile Viewer layers 1 + 3.

    ``quotes`` are the latest fetched chain's prepared quotes as the market
    quotes them (NO user edits: excluded/amended always False), with the fit-
    target band of the requested fit mode (``targetLo``/``targetHi``, None in
    "mid" mode) and ``index`` = the calibration quote at the same strike (click-
    through; -1 when none). ``model`` is the displayed fit ROLLED to the
    prevailing spot under the dynamics regime (k relative to ``forward``; empty
    when the node has no fit). ``live`` flags a streaming source, whose SSE
    tick stream refines this layer at ~1 Hz (volfit.api.table_stream).
    """

    forward: float
    spot: float | None = None
    timestamp: str | None = None  # ISO UTC of the prevailing chain
    live: bool = False
    quotes: list[QuoteBand] = Field(default_factory=list)
    model: list[SmilePoint] = Field(default_factory=list)


class CalibLayer(BaseModel):
    """The CALIBRATION frame of a node — Smile Viewer layers 2 + 4: the fit on
    its own calibration spot (``model``, k relative to ``forward`` = F0) — the
    curve the calibration quotes (``SmileData.quotes``, which carry their
    strike) are directly comparable with. Empty model when no fit."""

    forward: float
    spot: float | None = None
    model: list[SmilePoint] = Field(default_factory=list)


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
    #: Degraded-market condition (R2 item 10 degraded mode v1): the node has no
    #: fit because its DATA is unfittable for a NAMED reason —
    #: "no_parity_forward" (too few two-sided pairs for a parity regression) or
    #: "no_fittable_market" (every OTM quote fell to the prep screens; e.g. a
    #: 0DTE chain minutes from settlement, all sub-3-tick bids). The viewer
    #: keeps serving the dotted transported prior and labels the condition
    #: instead of the misleading "no fit yet" cue. None = plain not-calibrated.
    degraded: str | None = None
    #: The two comparable frames of the Smile Viewer (optional additions to the
    #: frozen contract): ``market`` = prevailing quotes + target and the fit
    #: rolled to the prevailing spot; ``calib`` = the fit on its calibration
    #: spot (paired with ``quotes``, the calibration quotes + their target).
    market: MarketLayer | None = None
    calib: CalibLayer | None = None


# ------------------------------------------------------------------ universe
class ExpiryInfo(BaseModel):
    """One listed expiry of a ticker with its year fraction and type tag
    (daily/weekly/monthly/quarterly/leaps — volfit.data.expiries), the
    handle for bulk expiry selection in the universe screen."""

    expiry: str
    t: float
    expiryType: str
    # Per-node EFFECTIVE as-of (workbench follow-on, 2026-08-27; built by
    # volfit.api.node_asof from the chain CACHE only — three Nones before the
    # first Fetch): the stamp of the chain serving the node, the active source
    # id serving it ("file" for a snapshot file) and whether that stamp sits in
    # the requested as-of session (live IS the moment ⇒ True once fetched;
    # False = the source served another moment — the nodes pane shows amber).
    effectiveAsOf: str | None = None  # = the loaded ChainSnapshot.timestamp (UTC-naive ISO)
    dataSource: str | None = None  # state.active_source
    asOfExact: bool | None = None


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
    #: Fit-target band of the requested fit mode (None in "mid"): the calibration
    #: rows carry the edited band the fit used, the market rows the pure-market
    #: band (optional additions to the frozen contract).
    targetLo: float | None = None
    targetHi: float | None = None
    excluded: bool
    amended: bool


class TableResponse(BaseModel):
    """The full quote/price/IV table of one fitted (ticker, expiry) node.

    ``rows`` is the CALIBRATION frame (the quotes + target the last fit used,
    with edits, Model IV = the fit on its calibration spot); the ``market*``
    fields are the PREVAILING frame (the latest fetched chain as quoted, no
    edits, target of the fit mode, Model IV = the fit ROLLED to the prevailing
    spot at each strike's market moneyness; ``index`` = the calibration row at
    the same strike, -1 when none). The Quote Table joins the two by strike;
    the live tick stream refines the market frame while streaming.
    """

    ticker: str
    expiry: str
    t: float
    forward: float
    discount: float
    rows: list[TableRow]
    marketForward: float | None = None
    marketSpot: float | None = None
    marketTimestamp: str | None = None
    marketLive: bool = False
    marketRows: list[TableRow] = Field(default_factory=list)


# --------------------------------------------------------------- graph solve
class GraphSolverParams(BaseModel):
    """Tunable hyperparameters of the increment prior Q_Delta and the graph.

    The three scales multiply the per-handle base regime (graph_params
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
    #: Cross-venue asynchronous expiries: when > 0, a cross-ticker edge is also
    #: generated between the NEAREST expiry pair (by calendar-day gap) whenever
    #: a rung has no exact same-date partner on the other ticker, up to this
    #: many days apart. The auto-lattice attenuates the edge weight by
    #: tol/(tol + gap); the message operator decays the cross precision by the
    #: same |dT| family as calendar factors and applies the maturity-shape
    #: beta (T_informer/T_receiver)^alphaT. 0 (default) = exact-date matching
    #: only — byte-identical to the historical topology.
    crossExpiryToleranceDays: float = Field(default=0.0, ge=0.0)


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
    # Prior provenance (V3.9 item 8 wire promotion): the resolved NodePrior the
    # baseline came from — previously computed then dropped at the wire.
    # priorAsOf/priorAgeDays are None when the hierarchy fell through to a
    # bootstrap/flat baseline (no prior snapshot moment to age).
    priorSource: str | None = None  # active_transported | nearest_expiry_... | ...
    priorAsOf: str | None = None  # the prior snapshot's market moment (dataTs)
    priorAgeDays: float | None = None  # _prior_age_days convention (day resolution)
    transportDistance: float | None = None  # h = log(F_now / F_prior)
    priorPrecision: list[float] | None = None  # per handle (atm_vol, skew, curv)
    # Per-node effective as-of (mirrors ExpiryInfo; volfit.api.node_asof):
    # the serving chain's stamp, the source serving it, exact-moment flag.
    effectiveAsOf: str | None = None
    dataSource: str | None = None
    asOfExact: bool | None = None


class GraphNodesResponse(BaseModel):
    """The full smile universe with baseline handles (Graph Viewer lattice)."""

    nodes: list[GraphNodeInfo]


class GraphInnovationPoint(BaseModel):
    """One persisted ATM innovation: |calibrated − transported prior| is the
    honest 'does the prior persist?' distance; the sign is kept on the wire."""

    day: str  # the as-of ISO date the innovation was recorded on
    expiry: str  # the node's expiry (the store's node key)
    innovationBp: float  # (calibrated − transported prior) ATM vol, bp


class GraphInnovationSeries(BaseModel):
    """GET /graph/innovations/{ticker}: the per-(day, expiry) ATM innovation
    series straight from the persisted idio-floor store (state
    record_graph_innovations) — read-only, nothing fitted or solved."""

    ticker: str
    series: list[GraphInnovationPoint]


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


# --------------------------------------------------- ticker-block topology rules
class GraphBlockPair(BaseModel):
    """One cross-ticker block rule: same-expiry links between ``a`` and ``b`` on
    every expiry present in BOTH tickers' selected ladders (the exact pairing the
    auto-lattice uses for its cross edges). ``symmetric`` emits both directions,
    otherwise a→b only; ``beta`` broadcasts to all three handle betas."""

    a: str
    b: str
    weight: float = Field(gt=0.0)  # directed conductance / trust (required)
    beta: float = 1.0  # broadcast to betaAtmVol/betaSkew/betaCurv
    symmetric: bool = True


class GraphBlockCalendar(BaseModel):
    """One ticker's calendar-chain block rule: consecutive selected expiries
    linked in BOTH directions (matching the auto-lattice's calendar edges)."""

    ticker: str
    weight: float = Field(gt=0.0)
    beta: float = 1.0


class GraphBlockRule(BaseModel):
    """Sparse ticker×ticker block-matrix topology rule (GET/PUT /graph/edges/blocks).

    The rule is what the user WROTE — it persists verbatim and round-trips exactly
    as written; the backend expands it into the per-edge list that ``/graph/edges``
    continues to serve (volfit.api.graph_blocks). Explicit ``overrides`` (full
    per-edge rows) are layered LAST: an override REPLACES any expanded edge with
    the same directed (from, to) node pair."""

    pairs: list[GraphBlockPair] = []
    calendar: list[GraphBlockCalendar] = []
    overrides: list[GraphEdgeInput] = []

    def is_empty(self) -> bool:
        """True when the rule carries nothing — clears back to the auto-lattice."""
        return not (self.pairs or self.calendar or self.overrides)


class GraphBlockRuleResponse(BaseModel):
    """The persisted block rule plus the size of its current expansion."""

    rule: GraphBlockRule
    expandedCount: int


# ------------------------------------------ precision-message edges (schema v2)
class GraphMessageEdge(BaseModel):
    """One precision-message relation factor (message arc, spec §18.2).

    UNAMBIGUOUS direction: the SOURCE (informer) predicts the TARGET
    (receiver) — ``z_target ≈ beta · z_source`` with conditional relation
    precision ``messagePrecision`` quoted in the TARGET's ATM-vol units
    (spec §7.1/§9.4). NB this naming INVERTS the legacy ``GraphEdgeInput``
    reading, where the engine treats ``to`` as informing ``from``
    (build.py's ``W[from][to]`` convention) — conversion is explicit and
    test-locked via ``graph_message.message_edges_from_legacy``.

    ``precisionRule="calendar_distance"`` derives the precision from the
    §9.2 maturity-gap family at solve time (``messagePrecision`` ignored).
    """

    sourceTicker: str
    sourceExpiry: str
    targetTicker: str
    targetExpiry: str
    messagePrecision: float = Field(default=1.0, gt=0.0)
    betaAtmVol: float = 1.0
    betaSkew: float = 1.0
    betaCurv: float = 1.0
    relationClass: Literal[
        "calendar", "broad_index", "sector_etf", "sector_peer", "custom"
    ] = "custom"
    precisionRule: Literal["explicit", "calendar_distance"] = "explicit"

    #: Dynamic-harmonic semantics (framework §9.2/§9.3): None applies the
    #: class default — calendar/sector_peer/custom → reciprocal_harmonic,
    #: broad_index/sector_etf → directed_state. Ignored outside
    #: propagationMode="layered_dynamic_harmonic".
    relationSemantics: Literal["reciprocal_harmonic", "directed_state"] | None = None


class GraphMessageEdgesResponse(BaseModel):
    """The persisted precision-message edge rules (GET/PUT /graph/edges/messages)."""

    edges: list[GraphMessageEdge]


class GraphMessageEdgesRequest(BaseModel):
    """Replace the persisted message edges (empty ⇒ back to auto relations)."""

    edges: list[GraphMessageEdge]


class GraphDynamicPolicy(BaseModel):
    """Layered-mode policy dials, versioned WITH the relation config (P6 V3).

    Staged on the DRAFT envelope (PUT /graph/config/messages/policy) and
    promoted by Activate like the rows. Resolution at solve time: an
    EXPLICITLY-sent request field wins; otherwise the run slot's (active, or
    draft under ``useDraftConfig``) envelope policy; otherwise the schema
    defaults — so an untouched request stays byte-identical until a policy
    is actually activated."""

    #: §4.2 clamp-requires-freshness: observations older than this many days
    #: lose hard-boundary status and enter as soft aged anchors.
    clampMaxAgeDays: float = Field(default=1.0, gt=0.0)
    #: D2 temporal law: residual half-life in DAYS; None = fully persistent
    #: (random walk) until the next actual target calibration.
    residualHalfLifeDays: float | None = Field(default=None, gt=0.0)
    #: Per-class semantics defaults overriding the §9.2 map for rows whose
    #: relationSemantics is unset (auto); unset classes keep the §9.2 value.
    semanticsDefaults: dict[
        str, Literal["reciprocal_harmonic", "directed_state"]
    ] = {}


class GraphMessageConfigEnvelope(BaseModel):
    """One slot of the U6 draft/active message-relation config lifecycle.

    ``version`` counts ACTIVATIONS: the draft carries the version it will
    become; ``parentVersion`` is the active version it was staged from.
    ``rows`` empty means "the auto relations" (the PUT [] contract).
    ``policy`` None means "pure schema defaults" (pre-V3 blobs coerce so)."""

    name: str = "default"
    version: int = 1
    createdAt: str = ""  # ISO timestamp of this slot's last write
    author: str = "desk"
    parentVersion: int | None = None
    notes: str = ""
    rows: list[GraphMessageEdge] = []
    policy: GraphDynamicPolicy | None = None


class GraphMessageConfigResponse(BaseModel):
    """GET /graph/config/messages — both lifecycle slots (null = never
    persisted; the solve then builds its auto relations)."""

    draft: GraphMessageConfigEnvelope | None
    active: GraphMessageConfigEnvelope | None


class GraphMessageConfigActivateRequest(BaseModel):
    """POST /graph/config/messages/activate — promote the draft."""

    notes: str = ""


class GraphCycleFlag(BaseModel):
    """One inconsistent beta cycle (spec §16.4), reported at the edge whose
    addition closes it. ``betaProduct`` is the implied product around the
    cycle; ``0.0`` is the sentinel for a nonpositive beta (impossible as a
    genuine product of positive betas)."""

    receiverTicker: str
    receiverExpiry: str
    informerTicker: str
    informerExpiry: str
    betaProduct: float


class SyntheticObservation(BaseModel):
    """One what-if pulse (P5b U3 — the unified mode-aware test pulse).

    Typed handle SHIFTS vs the node's transported prior, driving the
    production solve in place of the lit-calibration innovations: selected
    universe, transported-prior baselines, ACTIVE operator, and nothing is
    fitted or recorded. Any selected node may be pulsed (dark included —
    "what if we quoted it there"); nodes outside the selection are dropped
    (the legacy edge-list contract)."""

    ticker: str
    expiry: str
    #: Handle shifts vs the transported prior (decimal vol / per-unit-k).
    dAtmVol: float = 0.0
    dSkew: float = 0.0
    dCurv: float = 0.0
    #: ATM observation precision (1/vol²), or None ⇒ the firm what-if default
    #: (the sandbox's GRAPH_PRECISION); skew/curv scale proportionally.
    precision: float | None = Field(default=None, gt=0.0)


class CalendarPolicyOverride(BaseModel):
    """Per-ticker calendar-policy override (P5b U2 policy card).

    Unset fields inherit the request-level dials; ``enabled=False``
    suppresses EVERY calendar-class factor for that ticker — the auto ladder
    and persisted calendar rows alike (a policy switch, not a row edit)."""

    enabled: bool = True
    #: §9.2 precision scale override (1/vol²), or None ⇒ inherit.
    precisionScale: float | None = Field(default=None, gt=0.0)
    #: §8.1 amplitude shape exponent override, or None ⇒ inherit.
    betaExponent: float | None = None


class GraphExtrapolateRequest(GraphSolverParams):
    """Production prior-anchored extrapolation over the SELECTED lit+dark universe.

    Unlike the retired manual-shift sandbox, observations are NOT manually typed:
    they are derived server-side as ``calibrated_handles - transported_prior_handles``
    on the lit nodes (plan Amendment A) — or supplied as ``syntheticObservations``
    pulses by the unified what-if. The solver knobs (eta/kappa/lambda/nu,
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

    #: Idio band floor (volfit.graph.idio): a non-observed node's ATM credible
    #: band is floored from the ticker's trailing innovation history — the fix
    #: for the calm-regime dark-name band overconfidence (FINDINGS_graph_loo
    #: 2026-07-09). Band-only (never moves a posterior mean); OFF restores the
    #: legacy bands exactly.
    idioFloor: bool = True

    #: Functional posterior band (R3 item 12, volfit.models.lqd.band): the
    #: node-smile credible band is the delta-method pushforward of the FULL
    #: 3-handle posterior covariance through the slice map (skew/curvature
    #: uncertainty widens the wings), and the payload carries var-swap /
    #: tail-mass sds from the same pushforward. Band-only (never moves a
    #: posterior mean); OFF restores the legacy ATM-level band exactly.
    functionalBand: bool = True

    # ---------------- precision-message mode (message arc P3, spec §18) ----
    #: Propagation operator. "smooth_field" = the legacy increment prior,
    #: byte-identical at defaults; "precision_messages" = the pairwise
    #: relation-factor operator (volfit.graph.message); "hybrid" adds the
    #: legacy directed-smoothness term on top of the message factors
    #: (explicit opt-in, spec §15.4 — config-only, no UI until validated).
    propagationMode: Literal[
        "smooth_field", "precision_messages", "hybrid", "layered_dynamic_harmonic"
    ] = "smooth_field"

    #: Explicit message relation factors. Non-empty ⇒ defines the whole
    #: message topology; empty falls back to the persisted message edges,
    #: then the auto relations (calendar ladders + same-expiry cross pairs).
    messageEdges: list[GraphMessageEdge] = []

    #: §8 calendar amplitude SHAPE exponent alphaT (locked default 1.0),
    #: broadcast to all three handles in v1 (§8.5 per-handle exponents ride
    #: the Phase-4 sweep).
    calendarBetaExponent: float = 1.0

    #: §8.4 amplitude LEVEL multipliers rho per relation class, mechanized
    #: via the §14.2 node-linked anchor. 1.0 = desk full force (zero anchor);
    #: the learned day-horizon presets are ~0.23 calendar (alphaT=1 shape)
    #: and ~0.39-0.55 cross (message_phase0 study).
    calendarAmplitude: float = Field(default=1.0, gt=0.0, le=1.0)
    crossAmplitude: float = Field(default=1.0, gt=0.0, le=1.0)

    #: §9.2 calendar precision family (Phase-0 empirical seeds).
    calendarPrecisionScale: float = Field(default=1.7e3, gt=0.0)
    calendarPrecisionEpsilon: float = Field(default=0.97, gt=0.0)
    calendarPrecisionDecay: Literal[
        "inverse_sqrt_gap", "constant", "log_distance"
    ] = "inverse_sqrt_gap"

    #: Cross-relation message precision (constant rule; Phase-0 index seed).
    crossPrecisionScale: float = Field(default=1.3e4, gt=0.0)

    #: U2 calendar policy switch: False suppresses every calendar-class
    #: factor (auto ladders AND persisted calendar rows) — cross relations
    #: keep flowing. Per-ticker refinements ride the overrides map.
    calendarEnabled: bool = True
    calendarPolicyOverrides: dict[str, CalendarPolicyOverride] = {}

    #: U3 unified what-if: when non-empty these typed pulses REPLACE the
    #: lit-calibration innovation feed (no fits triggered, nothing recorded).
    syntheticObservations: list[SyntheticObservation] = []

    #: U6 lifecycle: solve with the DRAFT config's rows instead of the active
    #: ones (the run-draft toggle) — a test drive, never an activation.
    useDraftConfig: bool = False

    #: Dynamic-harmonic mode only (framework D2): residual half-life in DAYS
    #: for persistent target-specific dislocations; None = fully persistent
    #: (random walk) until the next actual target calibration.
    residualHalfLifeDays: float | None = Field(default=None, gt=0.0)

    #: Dynamic-harmonic mode only (framework §4.2/D-record): observations
    #: older than this many days lose hard-boundary status and enter as soft
    #: aged anchors instead (clamp-requires-freshness rule). P6 V3: when the
    #: request does not send this field explicitly, the run slot's config
    #: policy (GraphDynamicPolicy) fills it — see resolve_dynamic_policy.
    clampMaxAgeDays: float = Field(default=1.0, gt=0.0)

    #: Dynamic-harmonic mode only (P6 V3, config-policy knob): per-class
    #: semantics defaults overriding the §9.2 map for rows whose
    #: relationSemantics is unset. Normally filled from the config policy at
    #: resolution — sending it explicitly is an API-caller override.
    relationSemanticsDefaults: (
        dict[str, Literal["reciprocal_harmonic", "directed_state"]] | None
    ) = None

    #: Dynamic-harmonic mode only (golden 15.13): a STABLE identity for the
    #: persistent residual store. None (default) = structural hash of the
    #: directed relations + temporal law, so any explicit beta/topology edit
    #: invalidates stored residuals. Callers whose betas are RE-ESTIMATED
    #: from data each solve (the benchmark harness; later the U6 active
    #: config version) must pin this — daily estimation drift is not a
    #: configuration change and must not wipe temporal memory.
    residualConfigVersion: str | None = None

    @field_validator("calendarPolicyOverrides", mode="before")
    @classmethod
    def _overrides_from_json(cls, v: object) -> object:
        """The drill-in GET forwards the solver knobs as QUERY params, where a
        nested map can only travel as a JSON string — accept that form too."""
        if isinstance(v, str):
            import json

            return json.loads(v) if v.strip() else {}
        return v

    #: §14.2 anchor OVERRIDE: a uniform innovation-anchor precision applied
    #: to every node when set (stress/hybrid use); None ⇒ the anchor is
    #: DERIVED from the amplitude multipliers (zero in desk mode).
    innovationAnchorPrecision: float | None = Field(default=None, ge=0.0)

    #: §16.4 cycle-consistency reporting tolerance on |beta product − 1|.
    cycleBetaTolerance: float = Field(default=0.05, gt=0.0)


class GraphPreflightIssue(BaseModel):
    """One pre-run finding (P5b U5). ``blocker`` gates Run; warnings/info
    never do — the arc's ratified contract."""

    severity: Literal["blocker", "warning", "info"]
    #: Machine tag (e.g. "empty_universe", "no_lit_path", "beta_extreme").
    code: str
    message: str
    count: int = 1


class GraphPreflightResponse(BaseModel):
    """POST /graph/preflight — the dry-run report (nothing fitted/solved/
    recorded; see volfit/api/graph_preflight.py for the contract)."""

    universeNodes: int
    litCount: int
    darkCount: int
    observationCount: int
    propagationMode: str
    #: True when no blocker-severity issue is present.
    ok: bool
    issues: list[GraphPreflightIssue]


class GraphObservationPlanRequest(GraphExtrapolateRequest):
    """POST /graph/observation-plan — "which dark node to quote next" (R3
    item 13). Solves the same posterior as /graph/extrapolate, then ranks the
    non-observed nodes by closed-form exposure-weighted posterior-variance
    reduction (rank-one Schur on the solved posterior — no refit)."""

    topN: int = Field(default=5, ge=1, le=50)
    #: Per-ticker exposure multipliers (default 1 everywhere): steer the
    #: ranking toward the books the desk actually holds.
    exposureWeights: dict[str, float] = {}


class GraphObservationBeneficiary(BaseModel):
    """One node whose ATM band shrinks when the candidate is quoted."""

    ticker: str
    expiry: str
    sdBeforeBp: float  # model posterior ATM sd, bp
    sdAfterBp: float


class GraphObservationCandidate(BaseModel):
    """One ranked next-observation candidate with its closed-form value."""

    ticker: str
    expiry: str
    lit: bool  # lit-but-uncalibrated nodes are candidates too
    selfSdBeforeBp: float  # its own model ATM sd before / after self-quoting
    selfSdAfterBp: float
    #: Share (percent) of the universe's remaining exposure-weighted ATM
    #: variance this single observation removes.
    totalVarReductionPct: float
    assumedPrecision: float  # the observation precision the score assumed
    beneficiaries: list[GraphObservationBeneficiary] = []


class GraphObservationPlanResponse(BaseModel):
    """Ranked observation plan (largest variance reduction first)."""

    candidates: list[GraphObservationCandidate]
    nCandidates: int  # how many nodes were scored (before topN truncation)


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
    #: Day-resolution prior age (_prior_age_days of priorAsOf, V3.9 item 8);
    #: None when the baseline has no snapshot moment (bootstrap / flat).
    priorAgeDays: float | None = None
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
    # Message-mode diagnostics (arc P3, spec §17): the ATM receiver conditional
    # incoming precision q_i (§7.6 mapping) and the §14.3 no-lit-path tag.
    # None in smooth_field mode.
    qIncoming: float | None = None
    noLitPath: bool | None = None
    # Dynamic-harmonic decomposition (framework Phase 6 V0, exit-gate
    # contract): ATM mark == baseline + systematic + residual + harmonic.
    # residualSurpriseAtm is the §12.2 chi for certified observed targets.
    # All None outside layered_dynamic_harmonic mode.
    boundaryClass: str | None = None
    systematicAtmVol: float | None = None
    residualAtmVol: float | None = None
    residualAgeDays: float | None = None
    harmonicAtmVol: float | None = None
    residualSurpriseAtm: float | None = None


class GraphExtrapolateResponse(BaseModel):
    """Posterior field over every selected node (production extrapolation)."""

    nodes: list[GraphExtrapolateNode]
    #: Which propagation operator produced this field (message arc P3).
    propagationMode: str = "smooth_field"
    #: §16.4 inconsistent beta cycles (message/hybrid modes only; empty when
    #: the configured betas are gauge-consistent, as the auto relations are).
    cycleDiagnostics: list[GraphCycleFlag] = []


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


class GraphAttributionEntry(BaseModel):
    """One observed (lit) node's exact share of a target node's posterior ATM
    move: ``contributionBp = gain × innovationBp`` where ``gain`` is the
    Kalman-gain row entry K[target, source] of the update that produced the
    displayed posterior, and ``innovationBp`` the source's own ATM innovation
    (its calibration minus its transported prior). The entries sum to the
    target's shift to solver precision — arithmetic, not a heuristic.
    ``edgeBeta`` reports the DIRECT edge's ATM beta when the pair is directly
    connected (context only: the gain folds the whole precision structure, so
    influence also flows through indirect paths)."""

    ticker: str
    expiry: str
    innovationBp: float
    gain: float
    contributionBp: float
    edgeBeta: float | None = None


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
    # Full marginal posterior sds + the functional pushforward (R3 item 12).
    sdSkew: float | None = None
    sdCurv: float | None = None
    bandKind: str = ""  # "functional" | "level" (escape hatch) | "" (no curve)
    varSwapVol: float | None = None  # var-swap vol of the posterior slice
    varSwapVolSd: float | None = None  # its delta-method posterior sd
    tailMassLeft: float | None = None  # P(X <= display k_lo)
    tailMassLeftSd: float | None = None
    tailMassRight: float | None = None  # P(X >= display k_hi)
    tailMassRightSd: float | None = None
    post: list[SmilePoint]  # reconstructed posterior smile
    postBandLo: list[SmilePoint]  # 95% credible band (functional | ATM-level)
    postBandHi: list[SmilePoint]
    prior: list[SmilePoint]  # transported prior smile
    litCalibration: list[SmilePoint]  # the node's own calibration (lit nodes)
    quotes: list[GraphQuotePoint]
    metrics: GraphNodeMetrics | None = None
    #: Exact per-lit-node decomposition of the ATM shift (largest |contribution|
    #: first, capped); ``attributionOthersBp`` folds the truncated tail so the
    #: list + remainder always sum to (postAtmVol - priorAtmVol) in bp.
    attribution: list[GraphAttributionEntry] = []
    attributionOthersBp: float = 0.0


class GraphBacktestNode(BaseModel):
    """One held-out node's leave-one-node-out prediction vs its calibration."""

    ticker: str
    expiry: str
    priorSource: str
    calibratedAtmVol: float
    postAtmVol: float  # predicted from the other nodes (this one withheld)
    residualBp: float  # (post - calibrated) ATM vol, basis points
    standardizedResidual: float  # zeta under the posterior + obs uncertainty
    #: The node's transported-prior ATM vol (U7): the client derives the
    #: no-propagation comparator residual (calibrated − prior) from it.
    priorAtmVol: float | None = None


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
    #: Lit tickers whose LV (affine) surface has drifted since its last LV
    #: calibration (V3.5 item 9 — the "Local-Vol only" badge). 0 while Local-Vol
    #: is gated off; never-calibrated tickers are not counted (same "calibrated
    #: before, inputs drifted" semantics as staleNodes).
    lvStaleTickers: int = 0
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
    #: ``OptionsSettings.schedulerUnifiedFetch`` echoed: the auto chain timer runs
    #: the unified snapshot sequence (chains -> spot -> optional prior roll ->
    #: optional auto-calibrate) and absorbs the spot poll — so the status bar can
    #: label the countdown "Next snapshot" and the Snapshot verb can say it also
    #: rides the timer. False = the legacy split timers.
    unifiedFetch: bool = False


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
    """One scheduled event of the dilated clock: ``weight`` EXTRA EQUIVALENT
    DAYS of diffusion time lumped at year-fraction ``time`` (the production
    clock volfit.calib.weighted_time consumes day-weights; Note 11).
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
    #: Real per-node var-swap edit-history state (the SEPARATE var-swap session,
    #: volfit.api.varswap_session) so the Term editor's undo/redo buttons reflect
    #: each rung's own stack. Optional: None on older cached payloads. (V3.6)
    varSwapCanUndo: bool | None = None
    varSwapCanRedo: bool | None = None
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
    #: SIGNED, un-clipped pdf on the same grid (V3.3 item 11): equals ``density``
    #: wherever Durrleman g >= 0 and dips below zero exactly where the model
    #: carries butterfly arbitrage. ONLY attached when a negative region exists
    #: in the displayed window — absent for clean overlays and always for LQD
    #: (structurally positive), so the legacy payload is byte-identical.
    densityRaw: list[float] = []


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
    # --- sub-zero density evidence (V3.3 item 11). All absent unless the
    # displayed model's SIGNED pdf goes negative somewhere in the displayed
    # window (butterfly arbitrage): LQD is structurally positive so the fields
    # never appear for it; SVI / MCS overlays attach them only when dipping.
    #: SIGNED, un-clipped pdf on the same x grid (== density where g >= 0).
    densityRaw: list[float] = []
    #: Minimum of the signed pdf over the displayed window, computed on the
    #: FULL grid BEFORE chart striding (a narrow dip is still reported).
    minDensity: float | None = None
    #: Log-return x of that minimum (the circle-marker location).
    minDensityX: float | None = None


class StackedDensityResponse(BaseModel):
    """Risk-neutral densities of every fitted expiry of a ticker, nearest first
    (the Parametric 'Stacked densities' view — all curves overlaid show they
    stay non-negative, i.e. no butterfly arbitrage)."""

    ticker: str
    expiries: list[StackedDensityItem]
