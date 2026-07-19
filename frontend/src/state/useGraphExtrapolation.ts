// Production graph extrapolation state (plan Phases 3-8): the prior-anchored path,
// distinct from the manual-shift sandbox (useGraph).
//
// POST /graph/extrapolate transports each selected node's prior to the current
// spot, derives the lit-calibration innovations, propagates them through the graph
// and returns per-node posterior ATM handles + credible bands + provenance.
// POST /graph/backtest runs the leave-one-node-out validation. Live backend only.
import { useCallback, useState } from "react";
import { api } from "./api";
import { nodeKey, type GraphSolveNode, type SolverParams } from "./useGraph";

/** The /graph/extrapolate request body (solver knobs + production flags).
 *  Values are JSON-serializable; the U2 policy overrides ride as a nested
 *  object, hence the loose value type. */
export type ExtrapolateBody = Record<string, unknown>;

/** Build the /graph/extrapolate request body from the shared solver knobs plus
 *  the production-only flags (flat baselines, cross-ticker beta). Shared by the
 *  Extrapolate panel (run/backtest) and the drill-in focus (node-smile overlay)
 *  so the overlay reconstructs with the same knobs the table was solved with. */
export function buildExtrapolateBody(
  params: SolverParams,
  flatAtm: boolean,
  crossBeta: number | null,
): ExtrapolateBody {
  const body: ExtrapolateBody = {
    etaScale: params.etaScale,
    kappaScale: params.kappaScale,
    lambdaScale: params.lambdaScale,
    nu: params.nu,
    flatAtm,
  };
  if (params.calendarWeight !== null) body.calendarWeight = params.calendarWeight;
  if (params.crossWeight !== null) body.crossWeight = params.crossWeight;
  if (crossBeta !== null && crossBeta !== 1) body.crossBeta = crossBeta;
  // Message-mode knobs ride only when the operator is selected — an untouched
  // request stays byte-identical to the legacy smooth-field path.
  if (params.propagationMode !== "smooth_field") {
    body.propagationMode = params.propagationMode;
    body.calendarBetaExponent = params.alphaT;
    body.calendarAmplitude = params.ampCal;
    body.crossAmplitude = params.ampCross;
    body.calendarPrecisionScale = params.calPrecision;
    body.calendarPrecisionEpsilon = params.calEpsilon;
    body.calendarPrecisionDecay = params.calDecay;
    body.crossPrecisionScale = params.crossPrecision;
    // U2 calendar policy — ship only non-default state so an untouched
    // request stays minimal.
    if (!params.calendarEnabled) body.calendarEnabled = false;
    const overrides = Object.entries(params.calendarOverrides).filter(
      ([, o]) => !o.enabled || o.precisionScale !== null || o.betaExponent !== null,
    );
    if (overrides.length > 0) {
      body.calendarPolicyOverrides = Object.fromEntries(
        overrides.map(([ticker, o]) => [
          ticker,
          {
            enabled: o.enabled,
            ...(o.precisionScale !== null ? { precisionScale: o.precisionScale } : {}),
            ...(o.betaExponent !== null ? { betaExponent: o.betaExponent } : {}),
          },
        ]),
      );
    }
  }
  return body;
}

/** One node's prior -> posterior summary (backend GraphExtrapolateNode). */
export interface ExtrapolateNode {
  ticker: string;
  expiry: string;
  t: number;
  lit: boolean;
  calibrated: boolean;
  priorSource: string;
  priorAsOf: string | null;
  transportDistance: number;
  validForValidation: boolean;
  priorAtmVol: number;
  priorSkew: number;
  priorCurv: number;
  postAtmVol: number;
  postSkew: number;
  postCurv: number;
  shiftBp: number;
  sd: number;
  bandLo: number;
  bandHi: number;
  innovationBp: number | null;
  baselinePrecision: number[];
  obsPrecision: number[] | null;
  precisionFactors: Record<string, number>;
  /** Message-mode diagnostics (spec §17): the ATM receiver conditional
   *  incoming precision q_i and the §14.3 no-lit-path tag. Null in
   *  smooth_field mode. */
  qIncoming: number | null;
  noLitPath: boolean | null;
}

/** One inconsistent beta cycle (spec §16.4), flagged at its closing edge;
 *  betaProduct 0 is the nonpositive-beta sentinel. */
export interface CycleFlag {
  receiverTicker: string;
  receiverExpiry: string;
  informerTicker: string;
  informerExpiry: string;
  betaProduct: number;
}

interface ExtrapolateResponse {
  nodes: ExtrapolateNode[];
  propagationMode: string;
  cycleDiagnostics: CycleFlag[];
}

/** One held-out node's LOO prediction (backend GraphBacktestNode). */
export interface BacktestNode {
  ticker: string;
  expiry: string;
  priorSource: string;
  calibratedAtmVol: number;
  postAtmVol: number;
  residualBp: number;
  standardizedResidual: number;
}

/** Aggregate backtest summary (backend GraphBacktestResponse). */
export interface BacktestResult {
  nodes: BacktestNode[];
  nScored: number;
  nExcludedBootstrap: number;
  rmseBp: number;
  zetaMean: number;
  zetaStd: number;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Map a production node onto the sandbox GraphSolveNode shape so the existing
 *  GraphChart can render the posterior field (prior -> post shift + band). */
export function asSolveNode(n: ExtrapolateNode): GraphSolveNode {
  return {
    ticker: n.ticker,
    expiry: n.expiry,
    t: n.t,
    baseAtmVol: n.priorAtmVol,
    postAtmVol: n.postAtmVol,
    shiftBp: n.shiftBp,
    sd: n.sd,
    bandLo: n.bandLo,
    bandHi: n.bandHi,
    observed: n.calibrated,
  };
}

export interface UseGraphExtrapolationResult {
  nodes: ExtrapolateNode[] | null;
  results: Record<string, GraphSolveNode> | null;
  running: boolean;
  error: string | null;
  /** §16.4 inconsistent-cycle flags of the last solve (empty when clean). */
  cycles: CycleFlag[];
  backtest: BacktestResult | null;
  backtesting: boolean;
  backtestError: string | null;
  /** Run the production solve with the given request body (solver knobs + flags). */
  run: (body: Record<string, unknown>) => Promise<void>;
  /** Run the leave-one-node-out backtest with the same body. */
  runBacktest: (body: Record<string, unknown>) => Promise<void>;
  clear: () => void;
}

export function useGraphExtrapolation(): UseGraphExtrapolationResult {
  const [nodes, setNodes] = useState<ExtrapolateNode[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cycles, setCycles] = useState<CycleFlag[]>([]);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const run = useCallback(async (body: Record<string, unknown>) => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.post<ExtrapolateResponse>("/graph/extrapolate", { body });
      setNodes(res.nodes);
      setCycles(res.cycleDiagnostics ?? []);
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setRunning(false);
    }
  }, []);

  const runBacktest = useCallback(async (body: Record<string, unknown>) => {
    setBacktesting(true);
    setBacktestError(null);
    try {
      // LOO = one full solve per held-out node: legitimately slow on a large
      // universe, so give it well beyond the default request timeout.
      setBacktest(
        await api.post<BacktestResult>("/graph/backtest", { body, timeoutMs: 300_000 }),
      );
    } catch (err: unknown) {
      setBacktestError(messageOf(err));
    } finally {
      setBacktesting(false);
    }
  }, []);

  const clear = useCallback(() => {
    setNodes(null);
    setCycles([]);
    setBacktest(null);
    setError(null);
    setBacktestError(null);
  }, []);

  const results =
    nodes === null
      ? null
      : Object.fromEntries(nodes.map((n) => [nodeKey(n.ticker, n.expiry), asSolveNode(n)]));

  return {
    nodes,
    results,
    running,
    error,
    cycles,
    backtest,
    backtesting,
    backtestError,
    run,
    runBacktest,
    clear,
  };
}
