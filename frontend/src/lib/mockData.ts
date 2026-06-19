// Built-in mock smile data for the Smile Viewer while the backend is offline.
//
// The shape of `SmileData` mirrors what the FastAPI backend will eventually
// return, so swapping this module for a real call is a one-liner in the view:
//   const smile = await api.get<SmileData>("/smiles/SPX/2026-12-18");

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
}

/** One displayed-model hyperparameter as a label/value pair (LQD degree, cores). */
export interface ModelParam {
  label: string;
  value: string;
}

/** The model family + hyperparameters that produced the displayed fit. */
export interface ModelInfo {
  id: "lqd" | "svi" | "sigmoid";
  /** Human family name ("LQD", "SVI-JW", "Multi-Core SIV"). */
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
    quotes.push({
      k,
      bid: mid - half,
      ask: mid + half,
      mid,
      index: i,
      excluded: false,
      amended: false,
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
    },
  };
}
