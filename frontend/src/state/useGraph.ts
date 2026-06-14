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
import { useCallback, useEffect, useRef, useState } from "react";
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
  /** Lit/dark designation (shared with the Universe tab); lit = observed. */
  lit: boolean;
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

/**
 * Tunable hyperparameters of the increment prior Q_Δ and the graph edges,
 * mirroring the backend GraphSolverParams schema. Scales multiply the
 * per-handle base regime; weights are null when the service defaults apply.
 */
export interface SolverParams {
  /** Directed-smoothness reach η (propagation distance). */
  etaScale: number;
  /** Local precision κ (stiffness toward the baseline — higher = less spread). */
  kappaScale: number;
  /** Optimal-transport flux weight λ (0 disables the OT term). */
  lambdaScale: number;
  /** OT source/sink allowance ν (only used when λ > 0). */
  nu: number;
  /** Same-ticker calendar edge weight, or null for the service default (10). */
  calendarWeight: number | null;
  /** Cross-ticker equal-expiry edge weight, or null for the default (2). */
  crossWeight: number | null;
}

/** One scored grid point of an auto-tune sweep. */
export interface AutotuneCandidate {
  etaScale: number;
  rmseBp: number;
}

/** Response of POST /graph/autotune. */
export interface AutotuneResult {
  etaScale: number;
  rmseBp: number;
  candidates: AutotuneCandidate[];
}

/** Default solver regime: legacy behavior (OT off, service edge weights). */
const DEFAULT_PARAMS: SolverParams = {
  etaScale: 1,
  kappaScale: 1,
  lambdaScale: 0,
  nu: 0.1,
  calendarWeight: null,
  crossWeight: null,
};

/** JSON body for a solver request: drops null edge weights so the backend
 *  falls back to its defaults rather than receiving explicit nulls. */
function paramsBody(params: SolverParams): Record<string, number> {
  const body: Record<string, number> = {
    etaScale: params.etaScale,
    kappaScale: params.kappaScale,
    lambdaScale: params.lambdaScale,
    nu: params.nu,
  };
  if (params.calendarWeight !== null) body.calendarWeight = params.calendarWeight;
  if (params.crossWeight !== null) body.crossWeight = params.crossWeight;
  return body;
}

/** Canonical map key for a smile node. */
export function nodeKey(ticker: string, expiry: string): string {
  return `${ticker}|${expiry}`;
}

/** Default observation when a node is first lit by a click: +1.0 vol pt on ATM
 *  (so the propagation is immediately visible). The lit set seeded from the
 *  shared designation starts at 0 (observed anchors, no perturbation). */
const DEFAULT_D_ATM_VOL = 0.01;

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Persist a node's lit/dark designation to the backend (fire-and-forget, so a
 *  transient failure never blocks the local graph interaction). Keeps the
 *  Universe and Graph tabs in sync (ROADMAP Phase 10 follow-up). */
function persistLit(key: string, lit: boolean): void {
  const [ticker = "", expiry = ""] = key.split("|");
  if (ticker === "" || expiry === "") return;
  void api
    .put(`/universe/lit/${ticker}/${encodeURIComponent(expiry)}`, { body: { lit } })
    .catch(() => {
      /* designation is best-effort; the local lit set already updated */
    });
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
  /** Light several dark nodes at once (lasso); already-lit keys keep value. */
  lightMany: (keys: string[]) => void;
  /** Remove a node from the lit set. */
  unlight: (key: string) => void;
  /** Current solver hyperparameters. */
  params: SolverParams;
  /** Update one solver hyperparameter. */
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
  /** Reset all solver hyperparameters to the default regime. */
  resetParams: () => void;
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
  /** LOO cross-validate η over the lit set; needs >= 2 lit nodes. */
  autotune: () => Promise<void>;
  /** True while an auto-tune sweep is in flight. */
  autotuning: boolean;
  /** Last auto-tune result (chosen η + scored grid), or null. */
  autotuneResult: AutotuneResult | null;
  /** Last auto-tune failure, cleared on the next attempt. */
  autotuneError: string | null;
}

export function useGraph(): UseGraphResult {
  const [nodes, setNodes] = useState<GraphNodeBase[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumping this re-runs the load effect (the Retry button).
  const [loadAttempt, setLoadAttempt] = useState(0);

  const [lit, setLit] = useState<Record<string, number>>({});
  const [params, setParams] = useState<SolverParams>(DEFAULT_PARAMS);
  const [results, setResults] = useState<Record<string, GraphSolveNode> | null>(
    null,
  );
  const [solving, setSolving] = useState(false);
  const [solveError, setSolveError] = useState<string | null>(null);
  const [autotuning, setAutotuning] = useState(false);
  const [autotuneResult, setAutotuneResult] = useState<AutotuneResult | null>(null);
  const [autotuneError, setAutotuneError] = useState<string | null>(null);

  // Seed the lit (observed) set from the shared designation exactly once, on
  // the first successful node load; subsequent Retries keep the user's edits.
  const seededRef = useRef(false);

  // Load the baseline node handles once (and again on each Retry).
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .get<GraphNodesResponse>("/graph/nodes", { signal: controller.signal })
      .then((res) => {
        setNodes(res.nodes);
        if (!seededRef.current) {
          seededRef.current = true;
          // Lit-designated nodes become observed anchors (shift 0); dark ones
          // are extrapolation targets (absent from the observed set).
          const seed: Record<string, number> = {};
          for (const n of res.nodes) if (n.lit) seed[nodeKey(n.ticker, n.expiry)] = 0;
          setLit(seed);
        }
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
      if (key in next) {
        delete next[key];
        persistLit(key, false);
      } else {
        next[key] = DEFAULT_D_ATM_VOL;
        persistLit(key, true);
      }
      return next;
    });
  }, []);

  const setShift = useCallback((key: string, dAtmVol: number) => {
    setLit((prev) => ({ ...prev, [key]: dAtmVol }));
  }, []);

  const lightMany = useCallback((keys: string[]) => {
    if (keys.length === 0) return;
    setLit((prev) => {
      const next = { ...prev };
      for (const key of keys) {
        if (!(key in next)) {
          next[key] = DEFAULT_D_ATM_VOL;
          persistLit(key, true);
        }
      }
      return next;
    });
  }, []);

  const unlight = useCallback((key: string) => {
    setLit((prev) => {
      const next = { ...prev };
      delete next[key];
      persistLit(key, false);
      return next;
    });
  }, []);

  const setParam = useCallback(
    <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => {
      setParams((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const resetParams = useCallback(() => setParams(DEFAULT_PARAMS), []);

  /** Lit set as the backend's observation list (absolute handle shifts). */
  const observationList = useCallback(
    () =>
      Object.entries(lit).map(([key, dAtmVol]) => {
        const [ticker = "", expiry = ""] = key.split("|");
        return { ticker, expiry, dAtmVol };
      }),
    [lit],
  );

  const solve = useCallback(async (): Promise<void> => {
    const observations = observationList();
    if (observations.length === 0) return; // backend requires >= 1
    setSolving(true);
    setSolveError(null);
    try {
      const res = await api.post<GraphSolveResponse>("/graph/solve", {
        body: { observations, ...paramsBody(params) },
      });
      const map: Record<string, GraphSolveNode> = {};
      for (const n of res.nodes) map[nodeKey(n.ticker, n.expiry)] = n;
      setResults(map);
    } catch (err: unknown) {
      setSolveError(messageOf(err));
    } finally {
      setSolving(false);
    }
  }, [observationList, params]);

  const autotune = useCallback(async (): Promise<void> => {
    const observations = observationList();
    if (observations.length < 2) return; // LOO needs >= 2 observations
    setAutotuning(true);
    setAutotuneError(null);
    try {
      const res = await api.post<AutotuneResult>("/graph/autotune", {
        body: { observations, ...paramsBody(params) },
      });
      setAutotuneResult(res);
      // Adopt the chosen reach so the next Solve uses it.
      setParams((prev) => ({ ...prev, etaScale: res.etaScale }));
    } catch (err: unknown) {
      setAutotuneError(messageOf(err));
    } finally {
      setAutotuning(false);
    }
  }, [observationList, params]);

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
    lightMany,
    unlight,
    params,
    setParam,
    resetParams,
    solve,
    solving,
    solveError,
    results,
    clear,
    autotune,
    autotuning,
    autotuneResult,
    autotuneError,
  };
}
