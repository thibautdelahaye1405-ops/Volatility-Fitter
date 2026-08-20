// Built-in mock smile data for the Smile Viewer while the backend is offline.
//
// The shape of `SmileData` mirrors what the FastAPI backend will eventually
// return, so swapping this module for a real call is a one-liner in the view:
//   const smile = await api.get<SmileData>("/smiles/SPX/2026-12-18");

import type { FilterStepWire } from "./filterTimeline";
import type {
  InnovationPoint,
  PriorEvidenceStatus,
  PriorHistoryEntry,
} from "./priorEvidence";

/** A single point of a continuous model curve in (log-moneyness, vol) space. */
export interface SmilePoint {
  /** Log-moneyness k = ln(K / F). */
  k: number;
  /** Black-Scholes implied volatility (decimal, e.g. 0.206 = 20.6%). */
  vol: number;
}

/** A discrete market quote expressed as a bid/ask band of implied vols. */
export interface QuoteBand {
  k: number;
  bid: number;
  ask: number;
  mid: number;
  /** Stable quote identity, preserved across refits (unlike array position). */
  index: number;
  /** True when the quote is excluded from the calibration. */
  excluded: boolean;
  /** True when the mid has been manually amended by the user. */
  amended: boolean;
  /** The quote's strike — the layer-independent identity the viewer joins on
   *  (calibration quote / prevailing market quote / live tick at the same
   *  strike are the same option) and places at log(strike / layer forward).
   *  Optional for older payloads / mock. */
  strike?: number | null;
  /** Fit-target band edges resolved by the backend's own band rule
   *  (volfit.calib.band): fit_mode "bidask" → (bid, ask); "haircut" → the
   *  mid-clamped (bid+h, ask−h) around the (possibly amended) mid. Absent /
   *  null under fit_mode "mid" (the target is the mid polyline). Optional so
   *  older payloads still type-check. */
  targetLo?: number | null;
  targetHi?: number | null;
}

/** The PREVAILING market frame of a node (Smile Viewer layers 1 + 3): the
 *  latest fetched chain's quotes as the market quotes them (no user edits, with
 *  the viewed fit mode's target band and `index` = the calibration quote at the
 *  same strike, -1 when none) and the fit ROLLED to the prevailing spot (k
 *  relative to `forward`; empty when no fit). `live` flags a streaming source
 *  whose SSE tick stream refines this layer at ~1 Hz (state/useLiveTicks). */
export interface MarketLayer {
  forward: number;
  spot?: number | null;
  timestamp?: string | null;
  live?: boolean;
  quotes: QuoteBand[];
  model: SmilePoint[];
}

/** The CALIBRATION frame (layers 2 + 4): the fit on its own calibration spot
 *  (k relative to `forward` = F0) — comparable with `SmileData.quotes`. */
export interface CalibLayer {
  forward: number;
  spot?: number | null;
  model: SmilePoint[];
}

/** Headline diagnostics displayed next to the chart. */
export interface SmileDiagnostics {
  atmVol: number;
  skew: number;
  curvature: number;
  /** Left / right asymptotic total-variance slopes of the SVI wings. */
  aLeft: number;
  aRight: number;
  /** Lee moment-formula slope bounds implied by the wings. */
  leeLeft: number;
  leeRight: number;
  varSwapVol: number;
  /** Weighted RMS vol error of the fit (decimal vol; rendered as a percentage). */
  rmsError: number;
  /** Quote-derived 1σ handle uncertainty (fit Jacobian + bid-ask noise);
   *  null/absent when no calibration or the measurement failed. */
  atmVolStd?: number | null;
  skewStd?: number | null;
  curvStd?: number | null;
}

/** One displayed-model hyperparameter as a label/value pair (LQD degree, cores). */
export interface ModelParam {
  label: string;
  value: string;
}

/** The model family + hyperparameters that produced the displayed fit. */
export interface ModelInfo {
  id: "lqd" | "svi" | "sigmoid";
  /** Human family name ("LQD", "SVI-JW", "Multi-Core Sigmoid"). */
  label: string;
  params: ModelParam[];
}

/** Variance-swap quote state of a node (shared by Parametric & Local Vol). */
export interface VarSwapInfo {
  /** Quoted var-swap vol (decimal), or null when no quote exists. */
  level: number | null;
  /** Quote present but excluded from the calibration penalty. */
  excluded: boolean;
  /** The model's own fair var-swap vol (used to seed a new quote). */
  modelVol: number;
  /** Mirrors OptionsSettings.varSwapEnabled — gates the whole affordance. */
  enabled: boolean;
  /** Separate undo/redo history for var-swap edits (not the quote edits). */
  canUndo: boolean;
  canRedo: boolean;
  // ---- V3.6 optional readouts (absent on older payloads / mock). ----
  /** Quote-minus-model basis in vol basis points ((level − modelVol)·1e4);
   *  positive ⇒ the quote sits above the model. Null without a quote. */
  basisBp?: number | null;
  /** OptionsSettings.varSwapWeightPct echoed at the point of use (null while
   *  var-swap quoting is disabled). Set in Options ▸ Calibration. */
  weightPct?: number | null;
  /** Resolved absolute penalty weight: (weightPct/100) · Σ option-quote
   *  weights of the node. Null when no ACTIVE target. */
  weightAbs?: number | null;
  /** Mirrors SmileData.stale for this node (frozen fit, inputs drifted). */
  stale?: boolean | null;
  /** Var-swap share of the node's weighted squared vol error, in [0, 1]. */
  rmsShare?: number | null;
}

/** Everything the Smile Viewer needs for one (underlying, expiry) node. */
export interface SmileData {
  ticker: string;
  expiry: string;
  /** Year-fraction to expiry. */
  T: number;
  /** Forward level, used when rendering in fixed-strike axis mode. */
  forward: number;
  model: SmilePoint[];
  prior: SmilePoint[];
  /** True when `prior` is the active fetched prior, spot-updated under the
   *  dynamics regime (drawn as a dotted spot-updated prior). */
  priorTransported: boolean;
  quotes: QuoteBand[];
  /** Full k extent of the data (brush bounds). */
  kMin: number;
  kMax: number;
  /** Whether the backend fit session has edits to undo / redo. */
  canUndo: boolean;
  canRedo: boolean;
  diagnostics: SmileDiagnostics;
  /** Displayed model family + hyperparameters (degree / cores). Optional for
   *  older payloads; always present from the current backend. */
  modelInfo?: ModelInfo;
  /** Variance-swap quote + model level for this node. */
  varSwap: VarSwapInfo;
  /** False when the node has never been calibrated (gated workflow, before the
   *  Calibrate button): `model` is empty and the view shows quotes (if fetched)
   *  + the dotted prior (if any). Optional/true for older payloads / mock. */
  hasFit?: boolean;
  /** Named degraded-market condition ("no_parity_forward" |
   *  "no_fittable_market"): the node's data is unfittable, the dotted
   *  transported prior is the served surface and the cue says so. */
  degraded?: string | null;
  /** Inputs drifted since the last calibration — the displayed fit is frozen
   *  (stale) until an explicit Calibrate. Optional for older payloads / mock. */
  stale?: boolean;
  /** Whole-surface weighted RMS vol error of the ticker (all expiries pooled,
   *  same fit-target / scheme / var-swap basis as diagnostics.rmsError). */
  surfaceRmsError?: number;
  /** Pre-transport calibration curve, present only while a spot move is active,
   *  so the chart can overlay the original fit (dimmed) under the transported
   *  smile. None/undefined when no spot move. */
  anchorModel?: SmilePoint[] | null;
  /** The two comparable frames of the Smile Viewer (optional additions): the
   *  prevailing market (+ fit rolled to its spot) and the calibration frame
   *  (fit on its calibration spot; pairs with `quotes`). */
  market?: MarketLayer | null;
  calib?: CalibLayer | null;
}

/* ------------------------------------------------------------------ */
/* Raw-SVI model                                                       */
/* ------------------------------------------------------------------ */

/** Raw SVI parameterisation of total implied variance w(k). */
interface SviParams {
  a: number;
  b: number;
  rho: number;
  m: number;
  sigma: number;
}

/** Realistic SPX-like 6-month smile (raw SVI in total-variance space). */
const SVI: SviParams = {
  a: 0.010625,
  b: 0.0728869,
  rho: -0.5,
  m: 0.0583095,
  sigma: 0.100995,
};

const T = 0.5;
const K_MIN = -0.4;
const K_MAX = 0.35;

/** Raw-SVI total variance: w(k) = a + b (rho (k-m) + sqrt((k-m)^2 + sigma^2)). */
function sviTotalVariance(p: SviParams, k: number): number {
  const x = k - p.m;
  return p.a + p.b * (p.rho * x + Math.sqrt(x * x + p.sigma * p.sigma));
}

/** Implied vol from total variance: sigma(k) = sqrt(w(k) / T). */
function sviVol(p: SviParams, k: number, t: number): number {
  return Math.sqrt(sviTotalVariance(p, k) / t);
}

/* ------------------------------------------------------------------ */
/* Deterministic pseudo-randomness (seeded LCG, no Math.random)        */
/* ------------------------------------------------------------------ */

/** Numerical-Recipes LCG returning uniforms in [0, 1). Fully deterministic. */
function makeLcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/* ------------------------------------------------------------------ */
/* Mock data generation                                                */
/* ------------------------------------------------------------------ */

/** Sample a curve on a dense uniform k grid. */
function sampleCurve(
  n: number,
  volOf: (k: number) => number,
): SmilePoint[] {
  const points: SmilePoint[] = [];
  for (let i = 0; i < n; i++) {
    const k = K_MIN + ((K_MAX - K_MIN) * i) / (n - 1);
    points.push({ k, vol: volOf(k) });
  }
  return points;
}

/** Generate ~25 discrete quotes with wing-widening spreads and LCG jitter. */
function generateQuotes(count: number, seed: number): QuoteBand[] {
  const rand = makeLcg(seed);
  const quotes: QuoteBand[] = [];
  // Slightly inset strike range so wing quotes stay inside the chart.
  const lo = K_MIN + 0.02;
  const hi = K_MAX - 0.03;

  for (let i = 0; i < count; i++) {
    // Evenly spaced strikes with a small deterministic placement jitter.
    const base = lo + ((hi - lo) * i) / (count - 1);
    const k = base + (rand() - 0.5) * 0.008;

    // Mid quotes scatter around the model, more noisily in the wings.
    const wing = 1 + 4 * k * k;
    const mid = sviVol(SVI, k, T) + (rand() - 0.5) * 0.0016 * wing;

    // Half-spread: ~0.3 vol pt at the money, widening quadratically in wings.
    const half = (0.0015 + 0.02 * k * k) * (0.85 + 0.3 * rand());
    // Haircut fit-target band (backend default h = 0.5 vol pt), mid-clamped —
    // narrow ATM quotes collapse to the mid, wing quotes keep a shrunk band.
    const h = 0.005;
    quotes.push({
      k,
      bid: mid - half,
      ask: mid + half,
      mid,
      index: i,
      excluded: false,
      amended: false,
      targetLo: Math.min(mid - half + h, mid),
      targetHi: Math.max(mid, mid + half - h),
    });
  }
  return quotes;
}

/** Build the full mock smile payload (memoise at call site; it is pure). */
export function getMockSmile(): SmileData {
  const volOf = (k: number) => sviVol(SVI, k, T);
  return {
    ticker: "SPX",
    expiry: "2026-12-18",
    T,
    forward: 6150,
    model: sampleCurve(161, volOf),
    // Prior fit: same shape shifted down by 0.8 vol pt for visual comparison.
    prior: sampleCurve(161, (k) => volOf(k) - 0.008),
    priorTransported: false,
    quotes: generateQuotes(25, 20260610),
    kMin: K_MIN,
    kMax: K_MAX,
    // No fit session in mock mode, so there is never anything to undo.
    canUndo: false,
    canRedo: false,
    diagnostics: {
      atmVol: 0.206,
      skew: -0.355,
      curvature: 1.64,
      aLeft: 0.214,
      aRight: 0.069,
      leeLeft: 0.097,
      leeRight: 0.036,
      varSwapVol: 0.212,
      rmsError: 0.0021,
    },
    modelInfo: { id: "lqd", label: "LQD", params: [{ label: "Degree N", value: "6" }] },
    varSwap: {
      level: null,
      excluded: false,
      modelVol: 0.212,
      enabled: true,
      canUndo: false,
      canRedo: false,
      basisBp: null,
      weightPct: 10,
      weightAbs: null,
      stale: false,
      rmsShare: null,
    },
  };
}

/* ------------------------------------------------------------------ */
/* Model comparison (V3.2 item 12)                                     */
/* ------------------------------------------------------------------ */

/** Comparable smile families (the compare endpoint's model ids). */
export type CompareModelId = "lqd" | "svi" | "sigmoid";

/** Per-family analytic no-butterfly signal of one compared fit. */
export interface CompareValidity {
  /** "density" (LQD: density minimum, ≥ 0 by construction) | "g" (SVI / MCS:
   *  exact Durrleman g minimum, < 0 ⇒ arb) | "recon" (no analytic form). */
  kind: "density" | "g" | "recon";
  minValue?: number | null;
  /** minValue ≥ −tolerance for the kind; null when kind is "recon". */
  certified?: boolean | null;
}

/** One model family's fit + uniform metrics on the compared node. */
export interface CompareModelFit {
  model: CompareModelId;
  /** Display name ("LQD" | "SVI-JW" | "MCS"). */
  label: string;
  ok: boolean;
  error?: string | null;
  /** IV curve on the same display grid as the smile payload. */
  curve: SmilePoint[];
  rmsBp?: number | null;
  maxIvBp?: number | null;
  atmVol?: number | null;
  skew?: number | null;
  leeLeft?: number | null;
  leeRight?: number | null;
  varSwapVol?: number | null;
  validity?: CompareValidity | null;
  nParams?: number | null;
  /** Ad-hoc fit wall time (ms); null when the committed record was reused. */
  fitMs?: number | null;
  reused?: boolean;
}

/** Response of GET /smiles/{ticker}/{expiry}/compare. */
export interface CompareResponse {
  ticker: string;
  expiry: string;
  fitMode: string;
  activeModel: string;
  models: CompareModelFit[];
}

/* ------------------------------------------------------------------ */
/* Prior-persistence evidence (V3.9 item 8)                            */
/* ------------------------------------------------------------------ */

/** Everything the Prior Evidence tab fetches, in one mock bundle. */
export interface MockPriorEvidence {
  status: PriorEvidenceStatus;
  history: PriorHistoryEntry[];
  innovations: InnovationPoint[];
  residualHalfLifeDays: number | null;
}

/** Deterministic backendless Prior Evidence payload: a 2-day-old saved prior
 *  with a 3-deep history, and a 10-day × 3-expiry ATM innovation tape whose
 *  |bp| drifts believably (seeded LCG — no Math.random). */
export function getMockPriorEvidence(): MockPriorEvidence {
  const rand = makeLcg(20260610);
  const days = Array.from({ length: 10 }, (_, i) => {
    const d = new Date(Date.UTC(2026, 5, 1 + i)); // 2026-06-01 … 2026-06-10
    return d.toISOString().slice(0, 10);
  });
  const expiries = ["2026-09-18", "2026-12-18", "2027-03-19"];
  const innovations: InnovationPoint[] = [];
  for (const [j, expiry] of expiries.entries()) {
    let level = 12 + 6 * j; // farther expiries drift wider in this mock
    for (const day of days) {
      level = Math.max(2, level + (rand() - 0.5) * 8);
      innovations.push({
        day,
        expiry,
        innovationBp: +( (rand() < 0.5 ? -1 : 1) * level ).toFixed(1),
      });
    }
  }
  const history: PriorHistoryEntry[] = [
    { dataTs: "2026-06-08T19:45:00", savedTs: "2026-06-08T19:46:12", nodeCount: 8, asOfLabel: "live" },
    { dataTs: "2026-06-05T19:45:00", savedTs: "2026-06-05T19:47:03", nodeCount: 8, asOfLabel: "live" },
    { dataTs: "2026-06-01T19:45:00", savedTs: "2026-06-01T19:50:31", nodeCount: 7, asOfLabel: "prev_close 2026-05-29" },
  ];
  return {
    status: {
      ticker: "SPX",
      dataTs: history[0].dataTs,
      savedTs: history[0].savedTs,
      asOfLabel: history[0].asOfLabel,
      nodeCount: history[0].nodeCount,
      hasLvSurface: true,
      activeSource: "saved",
      activeDataTs: history[0].dataTs,
      ageDays: 2,
      activeAgeDays: 2,
    },
    history,
    innovations,
    residualHalfLifeDays: 5,
  };
}

/** Three plausible mock comparison fits so the Compare view works backendless:
 *  LQD hugs the base smile, SVI heavies the wings a touch, MCS sits slightly
 *  under with a mild |k| tilt — and the MCS row carries a small g-breach so
 *  the validity chip's rose state is visible in mock mode. */
export function getMockComparison(): CompareResponse {
  const volOf = (k: number) => sviVol(SVI, k, T);
  const fit = (
    model: CompareModelId,
    label: string,
    vol: (k: number) => number,
    metrics: Omit<CompareModelFit, "model" | "label" | "ok" | "curve">,
  ): CompareModelFit => ({ model, label, ok: true, curve: sampleCurve(161, vol), ...metrics });
  return {
    ticker: "SPX",
    expiry: "2026-12-18",
    fitMode: "mid",
    activeModel: "lqd",
    models: [
      fit("lqd", "LQD", volOf, {
        rmsBp: 18.4, maxIvBp: 52.1, atmVol: 0.206, skew: -0.355,
        leeLeft: 0.097, leeRight: 0.036, varSwapVol: 0.212,
        validity: { kind: "density", minValue: 1.2e-6, certified: true },
        nParams: 7, fitMs: null, reused: true,
      }),
      fit("svi", "SVI-JW", (k) => volOf(k) + 0.004 * k * k, {
        rmsBp: 24.9, maxIvBp: 68.3, atmVol: 0.205, skew: -0.348,
        leeLeft: 0.104, leeRight: 0.041, varSwapVol: 0.213,
        validity: { kind: "g", minValue: 2.4e-4, certified: true },
        nParams: 5, fitMs: 6.2, reused: false,
      }),
      fit("sigmoid", "MCS", (k) => volOf(k) - 0.002 + 0.006 * Math.abs(k), {
        rmsBp: 22.7, maxIvBp: 61.5, atmVol: 0.204, skew: -0.36,
        leeLeft: 0.093, leeRight: 0.034, varSwapVol: 0.211,
        validity: { kind: "g", minValue: -3.1e-4, certified: false },
        nParams: 12, fitMs: 41.8, reused: false,
      }),
    ],
  };
}

/** Eight plausible observation-filter history steps (V3.9 item 7): a seed,
 *  quiet 30-minute updates, one genuine surprise step (large ζ, the adaptive
 *  Q component tripped, gain snaps toward the data) and one contaminated
 *  measurement — so every FilterTimeline element is visible backendless. */
export function getMockFilterHistory(): { active: boolean; steps: FilterStepWire[] } {
  const t0 = Date.UTC(2026, 5, 10, 14, 0) / 1000;
  const dt = 1800 / 86400; // the 30-minute calendar-clock charge
  // ATM observations: quiet drift, then a 1.3-point jump at step 5.
  const atm = [0.206, 0.205, 0.207, 0.204, 0.206, 0.219, 0.217, 0.216];
  const steps: FilterStepWire[] = atm.map((z, i) => {
    const seed = i === 0;
    const surprise = i === 5;
    const pred = seed ? z : atm[i - 1];
    const predStd = seed ? 0.011 : surprise ? 0.013 : 0.006;
    const obsStd = 0.004;
    const nu = z - pred;
    const zeta = nu / Math.sqrt(predStd * predStd + obsStd * obsStd);
    const k = surprise ? 0.93 : 0.68;
    const clock = seed ? 0 : 1e-3 * 1e-3 * dt; // (10 bp/√day)² · dt
    return {
      ts: t0 + i * 1800,
      dtDays: seed ? 0 : dt,
      prediction: [pred, -0.35, 0.1],
      predictionStd: [predStd, 0.028, 0.31],
      observation: [z, -0.35 + 0.01 * Math.sin(i), 0.1 + 0.01 * i],
      observationStd: [obsStd, 0.018, 0.24],
      innovation: [nu, 0.01 * Math.sin(i), 0.01 * i],
      zeta: [zeta, 0.4 * Math.sin(i + 1), 0.3],
      gain: [k, k - 0.12, k - 0.25],
      posterior: [pred + k * nu, -0.349, 0.1 + 0.007 * i],
      posteriorStd: [predStd * Math.sqrt(1 - k), 0.02, 0.22],
      processBreakdown: {
        clock: [clock, 8.3e-6, 5.2e-5],
        spot: [2e-8, 5e-8, 1e-6],
        ...(surprise ? { adaptive: [2.2e-5, 0, 0] } : {}),
      },
      transportDistance: seed ? 0 : 0.0012,
      provenance: seed ? "seed:today_fit" : "update",
      resetReason: seed ? "first" : null,
      contaminated: i === 6,
    };
  });
  return { active: true, steps };
}
