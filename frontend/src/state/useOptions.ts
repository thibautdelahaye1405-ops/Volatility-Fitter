// Load / edit the global Options settings (GET/PUT /settings/options).
//
// These are the app-wide meta toggles, engine defaults and the editable
// calendar penalty strength (ROADMAP Phase 10) — distinct from the live
// FitSettings the HyperparamPanel edits. The Options workspace holds a draft,
// PUTs it on Apply, and the caller refits the current smile afterwards.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { FitMode } from "./useSmile";

/** Spot-vol dynamics regime default (mirror of the backend literal).
 *  "custom" applies the explicit ``ssr`` value; the others are named regimes. */
export type DynamicsRegime =
  | "sticky_moneyness"
  | "sticky_strike"
  | "sticky_local_vol"
  | "sticky_local_vol_grid"
  | "custom";
/** Spot price mode: "realtime" = backend polls live spots; "static" = on-demand. */
export type SpotMode = "realtime" | "static";
/** Options-chain fetch mode: "auto" = scheduler timer; "on_demand" = button only. */
export type OptionsFetchMode = "auto" | "on_demand";

/** Prior-persistence mode (design note §10): how a fetched prior is persisted into
 *  the calibration. off/overlay add no penalty; strike_gap = legacy data-gap
 *  anchor; quote_operator/smile_factor persist trader factors only where
 *  under-observed; hybrid = operators + a deep-tail anchor; graph_only leaves lit
 *  calibration market-pure (the graph carries the prior). */
export type PriorPersistenceMode =
  | "off"
  | "overlay"
  | "strike_gap"
  | "quote_operator"
  | "smile_factor"
  | "hybrid"
  | "graph_only";

/** Mirror of the backend OptionsSettings schema (volfit/api/schemas.py). */
export interface OptionsSettings {
  /** Default fit target (Mid / Bid-Ask / Haircut); seeds the session on load. */
  fitMode: FitMode;
  enforceCalendar: boolean;
  /** Tapered no-arb enforcement in the extrapolated strike region (Notes 09/10
   *  Phase 2): SVI/MCS overlay fits lean on the time-value envelope. Off =
   *  byte-identical fits; the Quality tab's extrap measurement is always on. */
  extrapEnforce: boolean;
  eventsEnabled: boolean;
  normalizeEvents: boolean;
  /** 0DTE research clock: value maturities snapshot-timestamp -> exact
   *  settlement instant, variance accruing on the session-weighted profile.
   *  Off = byte-identical day-granular fits. */
  intradayClock: boolean;
  /** Fraction of a trading day's variance accruing during the session
   *  (09:30 ET -> close). 6.5/24 = flat density (legacy day convention);
   *  research ~0.7-0.9 makes a 0DTE's clock "remaining trading minutes". */
  sessionVarShare: number;
  /** Day-weight of a non-trading day (weekend/holiday) on the intraday
   *  clock; 1 = legacy (a 3-day weekend costs 3 days of variance). */
  nonTradingWeight: number;
  varSwapEnabled: boolean;
  varSwapWeightPct: number;
  /** Local-Vol model var-swap pricing: static log-contract replication, or the
   *  grid-robust backward source PDE g(0,1) (volfit.models.localvol.varswap_pde). */
  varSwapMethod: 'static' | 'source_pde';
  autoLoadPrior: boolean;
  /** Prior-anchor penalty weight as a % of summed quote weights (autoLoadPrior). */
  priorAnchorWeightPct: number;
  /** Per-side delta-locations the prior anchor pins (forward deltas in (0,0.5));
   *  ATM is always added, var-swap prior carries the tail below the smallest. */
  priorAnchorDeltas: number[];
  /** Which prior-persistence model the calibration uses (design note §10). */
  priorPersistenceMode: PriorPersistenceMode;
  /** Quote operators the prior may persist (quote_operator / hybrid). */
  priorOperatorSet: string[];
  priorOperatorStrengthPct: number;
  priorOperatorRequiredPrecision: number;
  priorOperatorGapExponent: number;
  /** Quote-support kernel bandwidth (also the smile-factor FD step). */
  priorOperatorBandwidth: number;
  priorOperatorCovarianceMode: "diagonal" | "full";
  /** Two-pass activation: fit data-only first, then refit only under-observed priors. */
  priorDataOnlyPrepass: boolean;
  /** Risk-reversal sign convention. */
  collarSign: "call_put" | "put_call";
  /** Smile factors the prior may persist (smile_factor mode). */
  priorFactorSet: string[];
  priorFactorStrengthPct: number;
  /** Residual deep-tail strike-anchor budget in hybrid mode (% of quote weights). */
  priorTailAnchorStrengthPct: number;
  /** Observation Kalman filter (Note 15): off = absent; overlay = draw the
   *  filtered handles, calibration untouched; active = one-stage MAP prior. */
  observationFilterMode: "off" | "overlay" | "active";
  /** Measurement covariance route: Jacobian-propagated (default) or the cheap
   *  precision-factor fallback (A/B diagnostic). */
  filterCovarianceMode: "jacobian" | "factors";
  /** ATM process noise, vol bp per sqrt(calendar day). */
  filterProcessVolBpSqrtDay: number;
  filterProcessSkewSqrtDay: number;
  filterProcessCurvSqrtDay: number;
  /** Extra process std per unit |log-forward| transport distance. */
  filterTransportNoiseScale: number;
  /** Inflate R by realized fit inconsistency chi^2/(m-d) (clipped). */
  filterResidualInflation: boolean;
  /** Innovation-gated adaptive process noise: surprises beyond this many
   *  sigmas raise the gain instead of lagging (0 = off). */
  filterAdaptiveSigma: number;
  /** Pilot safety cap on per-handle gains (1 = not binding). */
  filterMaxGain: number;
  /** Max data gap (hours) predicted across; longer resets the state. */
  filterResetHours: number;
  /** Fit data-only first so the measurement is a clean market observation. */
  filterDataOnlyPrepass: boolean;
  /** Strike-vertex placement: "delta" (dense near ATM, the default) or legacy
   *  "linear" uniform-in-x. */
  gridStrikeMode: "delta" | "linear";
  gridXNodes: number;
  gridTNodes: number;
  gridRegLambda: number;
  gridRegRho: number;
  /** Force local vol sigma(x,t) convex in x below the 5Δ-put strike (soft hinge). */
  convexWing: boolean;
  convexWingWeight: number;
  /** Pull the t=0 local-vol row toward the first calibrated row (short-end fix). */
  frontTie: boolean;
  frontTieWeight: number;
  /** Adaptive local-vol cap = max(60%, lvVolCapMult x highest observed IV). */
  lvVolCapMult: number;
  /** LV PDE time scheme: "rannacher" = 2nd-order Crank-Nicolson (~3x fewer time
   *  steps at equal accuracy — faster), "implicit" = 1st-order backward Euler (legacy). */
  timeScheme: 'implicit' | 'rannacher';
  /** Early-stop the cold LV fit when the quote-fit improvement stalls (~1.45x on
   *  slow-converging names up to ~3.3x on fast ones, +0.1-0.25 bp; warm recals
   *  unaffected). */
  lvEarlyStop: boolean;
  /** Use the compiled Numba vectorized-Thomas Dupire march (~6x the banded march)
   *  for the LV calibration hot path; falls back to banded if numba is unavailable. */
  lvFastKernel: boolean;
  /** LV solver: "trf" (default) or "gn" = matrix-free Gauss-Newton (avoids trf's
   *  SVD; ~1.3-1.65x faster with the fast kernel, surface within ~0.25 vol-bp). */
  lvSolver: 'trf' | 'gn';
  /** Left-wing (x<x_min) linear-extrap slope × first-cell slope (free if var-swap set). */
  leftWingSlopeMult: number;
  calendarWeight: number;
  /** Multi-Core SIV put-wing no-butterfly regularizer strength (% of base; 0 = off). */
  sivWingPenaltyPct: number;
  graphKappaScale: number;
  graphEtaScale: number;
  graphLambdaScale: number;
  graphNu: number;
  dynamicsRegime: DynamicsRegime;
  ssr: number;
  autoCalibrate: boolean;
  /** Master switch for Local-Vol (affine) calibration + the Local Vol tab. */
  localVolEnabled: boolean;
  spotMode: SpotMode;
  spotPollSeconds: number;
  optionsFetchMode: OptionsFetchMode;
  optionsFetchMinutes: number;
  /** Seconds between full refits while a live WS book streams (Massive realtime). */
  streamRefitSeconds: number;
  /** Auto-open the WS book on a streaming source (Massive) so Fetch/Calibrate serve
   *  from the fast in-memory book instead of the slow REST snapshot. */
  autoStream: boolean;
  /** Data-age staleness thresholds (minutes) for the loaded LIVE quotes: past
   *  amber the market pill warns; past red the quality report fails readiness
   *  and Calibrate shows a stale-data warning. Display/report policy only. */
  dataAgeAmberMin: number;
  dataAgeRedMin: number;
}

export const OPTIONS_DEFAULTS: OptionsSettings = {
  fitMode: "mid",
  enforceCalendar: true,
  extrapEnforce: false,
  eventsEnabled: true,
  normalizeEvents: false,
  intradayClock: false,
  sessionVarShare: 6.5 / 24.0,
  nonTradingWeight: 1.0,
  varSwapEnabled: true,
  varSwapWeightPct: 10.0,
  varSwapMethod: 'static',
  autoLoadPrior: false,
  priorAnchorWeightPct: 50.0,
  priorAnchorDeltas: [0.02, 0.05, 0.1, 0.25, 0.4],
  priorPersistenceMode: "hybrid",
  priorOperatorSet: ["ATM", "RR25", "BF25", "VarSwap"],
  priorOperatorStrengthPct: 50.0,
  priorOperatorRequiredPrecision: 1.0,
  priorOperatorGapExponent: 1.0,
  priorOperatorBandwidth: 0.06,
  priorOperatorCovarianceMode: "diagonal",
  priorDataOnlyPrepass: false,
  collarSign: "call_put",
  priorFactorSet: ["ATM", "skew", "curvature", "VarSwap"],
  priorFactorStrengthPct: 50.0,
  priorTailAnchorStrengthPct: 20.0,
  observationFilterMode: "off",
  filterCovarianceMode: "jacobian",
  filterProcessVolBpSqrtDay: 30.0,
  filterProcessSkewSqrtDay: 0.02,
  filterProcessCurvSqrtDay: 0.05,
  filterTransportNoiseScale: 0.1,
  filterResidualInflation: true,
  filterAdaptiveSigma: 3.0,
  filterMaxGain: 1.0,
  filterResetHours: 96.0,
  filterDataOnlyPrepass: false,
  gridStrikeMode: "delta",
  gridXNodes: 12,
  gridTNodes: 10,
  gridRegLambda: 1e-2,
  gridRegRho: 1.0,
  convexWing: false,
  convexWingWeight: 1e3,
  frontTie: true,
  frontTieWeight: 1e-2,
  lvVolCapMult: 3.0,
  timeScheme: 'implicit',
  lvEarlyStop: true,
  lvFastKernel: true,
  lvSolver: 'gn',
  leftWingSlopeMult: 1.5,
  calendarWeight: 1e6,
  sivWingPenaltyPct: 100,
  graphKappaScale: 1.0,
  graphEtaScale: 1.0,
  graphLambdaScale: 0.0,
  graphNu: 0.1,
  dynamicsRegime: "sticky_strike",
  ssr: 2.0,
  autoCalibrate: true,
  localVolEnabled: true,
  spotMode: "static",
  spotPollSeconds: 5.0,
  optionsFetchMode: "on_demand",
  optionsFetchMinutes: 5.0,
  streamRefitSeconds: 5.0,
  autoStream: true,
  dataAgeAmberMin: 20.0,
  dataAgeRedMin: 120.0,
};

export interface UseOptionsResult {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  dirty: boolean;
  busy: boolean;
  flash: boolean;
  /** Commit the draft (PUT); resolves once saved (a no-op when not dirty). */
  apply: () => Promise<void>;
  /** Adopt a server-authoritative value (e.g. after a defaults reset). */
  adopt: (s: OptionsSettings) => void;
  /** True until the backend's current settings have loaded. */
  loaded: boolean;
}

export function useOptions(enabled: boolean, onApplied: () => void): UseOptionsResult {
  const [saved, setSaved] = useState<OptionsSettings>(OPTIONS_DEFAULTS);
  const [draft, setDraft] = useState<OptionsSettings>(OPTIONS_DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    api
      .get<OptionsSettings>("/settings/options", { signal: controller.signal })
      .then((s) => {
        setSaved(s);
        setDraft(s);
        setLoaded(true);
      })
      .catch(() => {
        /* keep defaults; the Apply PUT will surface real failures */
      });
    return () => controller.abort();
  }, [enabled]);

  const patch = useCallback(
    (p: Partial<OptionsSettings>) => setDraft((d) => ({ ...d, ...p })),
    [],
  );

  const dirty = (Object.keys(draft) as (keyof OptionsSettings)[]).some(
    (k) => draft[k] !== saved[k],
  );

  const apply = useCallback((): Promise<void> => {
    if (!dirty || busy) return Promise.resolve();
    setBusy(true);
    return api
      .put<OptionsSettings>("/settings/options", { body: draft })
      .then((s) => {
        setSaved(s);
        setDraft(s);
        setFlash(true);
        setTimeout(() => setFlash(false), 1200);
        onApplied();
      })
      .catch(() => {
        /* leave the draft dirty so the user can retry */
      })
      .finally(() => setBusy(false));
  }, [dirty, busy, draft, onApplied]);

  const adopt = useCallback((s: OptionsSettings) => {
    setSaved(s);
    setDraft(s);
  }, []);

  return { draft, patch, dirty, busy, flash, apply, adopt, loaded };
}
