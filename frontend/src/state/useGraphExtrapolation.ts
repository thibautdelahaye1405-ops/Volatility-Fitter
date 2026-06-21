// Production graph extrapolation state (plan Phases 3-8): the prior-anchored path,
// distinct from the manual-shift sandbox (useGraph).
//
// POST /graph/extrapolate transports each selected node's prior to the current
// spot, derives the lit-calibration innovations, propagates them through the graph
// and returns per-node posterior ATM handles + credible bands + provenance.
// POST /graph/backtest runs the leave-one-node-out validation. Live backend only.
import { useCallback, useState } from "react";
import { api } from "./api";
import { nodeKey, type GraphSolveNode } from "./useGraph";

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
}

interface ExtrapolateResponse {
  nodes: ExtrapolateNode[];
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
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const run = useCallback(async (body: Record<string, unknown>) => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.post<ExtrapolateResponse>("/graph/extrapolate", { body });
      setNodes(res.nodes);
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
      setBacktest(await api.post<BacktestResult>("/graph/backtest", { body }));
    } catch (err: unknown) {
      setBacktestError(messageOf(err));
    } finally {
      setBacktesting(false);
    }
  }, []);

  const clear = useCallback(() => {
    setNodes(null);
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
    backtest,
    backtesting,
    backtestError,
    run,
    runBacktest,
    clear,
  };
}
