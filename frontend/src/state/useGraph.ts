// Data + interaction state for the Graph Viewer.
//
// Talks to the FastAPI graph endpoints:
//   GET  /graph/nodes — baseline fitted handles (ATM vol, skew, curvature)
//                       for every (ticker, expiry) node of the universe.
//                       Fitted on demand server-side, so the first call can
//                       take about a second.
//   POST /graph/solve — propagates the lit-node observations through the
//                       smile graph (OT-Bayesian solver) and returns
//                       posterior ATM-vol shifts and uncertainty bands for
//                       every node.
//
// Unlike the smile session there is NO mock fallback here: the solver only
// makes sense against the live backend, so a failed load surfaces an error
// and the view renders a retry card instead of synthetic data.
//
// NOTE: this hook is mounted by the GraphViewer view itself, so lit nodes
// and solve results are reset when the user switches workspace tabs.
// Hoisting it into SmileSessionProvider would preserve them across tabs;
// deliberately deferred to keep the provider single-purpose.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** Baseline fitted handles of one smile node (GET /graph/nodes). */
export interface GraphNodeBase {
  ticker: string;
  expiry: string;
  /** Year-fraction to expiry. */
  t: number;
  atmVol: number;
  skew: number;
  curvature: number;
}

/** Response of GET /graph/nodes. */
interface GraphNodesResponse {
  nodes: GraphNodeBase[];
}

/** Posterior state of one node after a solve (POST /graph/solve). */
export interface GraphSolveNode {
  ticker: string;
  expiry: string;
  t: number;
  baseAtmVol: number;
  postAtmVol: number;
  /** Posterior ATM-vol shift in basis points (signed). */
  shiftBp: number;
  /** Posterior standard deviation of the shift (vol units). */
  sd: number;
  bandLo: number;
  bandHi: number;
  /** True when this node carried a user observation. */
  observed: boolean;
}

/** Response of POST /graph/solve. */
interface GraphSolveResponse {
  nodes: GraphSolveNode[];
}

/** Canonical map key for a smile node. */
export function nodeKey(ticker: string, expiry: string): string {
  return `${ticker}|${expiry}`;
}

/** Default observation when a node is first lit: +1.0 vol pt on ATM. */
const DEFAULT_D_ATM_VOL = 0.01;

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Everything `useGraph` exposes to the Graph Viewer. */
export interface UseGraphResult {
  /** Baseline nodes, or null before the first successful load. */
  nodes: GraphNodeBase[] | null;
  /** True while GET /graph/nodes is in flight. */
  loading: boolean;
  /** Load failure message (backend offline), or null. */
  error: string | null;
  /** Re-attempt the baseline load after a failure. */
  reload: () => void;
  /** Lit (observed) nodes: key -> dAtmVol observation (decimal vol). */
  lit: Record<string, number>;
  /** Light a dark node (default observation) or dim a lit one. */
  toggleLit: (key: string) => void;
  /** Update the dAtmVol observation of a lit node (decimal vol). */
  setShift: (key: string, dAtmVol: number) => void;
  /** Remove a node from the lit set. */
  unlight: (key: string) => void;
  /** Propagation-reach multiplier η (log-scaled slider in the UI). */
  etaScale: number;
  setEtaScale: (v: number) => void;
  /** POST the lit observations to /graph/solve; no-op with 0 lit nodes. */
  solve: () => Promise<void>;
  /** True while a solve is in flight. */
  solving: boolean;
  /** Last solve failure, cleared on the next attempt. */
  solveError: string | null;
  /** Posterior nodes keyed by nodeKey(), or null before the first solve. */
  results: Record<string, GraphSolveNode> | null;
  /** Drop the solve results (keeps the lit set). */
  clear: () => void;
}

export function useGraph(): UseGraphResult {
  const [nodes, setNodes] = useState<GraphNodeBase[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumping this re-runs the load effect (the Retry button).
  const [loadAttempt, setLoadAttempt] = useState(0);

  const [lit, setLit] = useState<Record<string, number>>({});
  const [etaScale, setEtaScale] = useState(1);
  const [results, setResults] = useState<Record<string, GraphSolveNode> | null>(
    null,
  );
  const [solving, setSolving] = useState(false);
  const [solveError, setSolveError] = useState<string | null>(null);

  // Load the baseline node handles once (and again on each Retry).
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .get<GraphNodesResponse>("/graph/nodes", { signal: controller.signal })
      .then((res) => {
        setNodes(res.nodes);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // unmounted, not an outage
        setError(messageOf(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [loadAttempt]);

  const reload = useCallback(() => setLoadAttempt((n) => n + 1), []);

  const toggleLit = useCallback((key: string) => {
    setLit((prev) => {
      const next = { ...prev };
      if (key in next) delete next[key];
      else next[key] = DEFAULT_D_ATM_VOL;
      return next;
    });
  }, []);

  const setShift = useCallback((key: string, dAtmVol: number) => {
    setLit((prev) => ({ ...prev, [key]: dAtmVol }));
  }, []);

  const unlight = useCallback((key: string) => {
    setLit((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const solve = useCallback(async (): Promise<void> => {
    const observations = Object.entries(lit).map(([key, dAtmVol]) => {
      const [ticker = "", expiry = ""] = key.split("|");
      return { ticker, expiry, dAtmVol };
    });
    if (observations.length === 0) return; // backend requires >= 1
    setSolving(true);
    setSolveError(null);
    try {
      const res = await api.post<GraphSolveResponse>("/graph/solve", {
        body: { observations, etaScale },
      });
      const map: Record<string, GraphSolveNode> = {};
      for (const n of res.nodes) map[nodeKey(n.ticker, n.expiry)] = n;
      setResults(map);
    } catch (err: unknown) {
      setSolveError(messageOf(err));
    } finally {
      setSolving(false);
    }
  }, [lit, etaScale]);

  const clear = useCallback(() => {
    setResults(null);
    setSolveError(null);
  }, []);

  return {
    nodes,
    loading,
    error,
    reload,
    lit,
    toggleLit,
    setShift,
    unlight,
    etaScale,
    setEtaScale,
    solve,
    solving,
    solveError,
    results,
    clear,
  };
}
