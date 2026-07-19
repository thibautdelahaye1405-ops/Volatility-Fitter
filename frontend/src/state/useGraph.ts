// Data + interaction state for the Graph Viewer.
//
// GET /graph/nodes returns the baseline fitted handles (ATM vol/skew/curvature)
// for every (ticker, expiry) node (fitted on demand, so the first call is slow).
// The lit set doubles as the what-if pulse set (P5b U3): the unified test
// pulse rides POST /graph/extrapolate via syntheticObservations — the old
// sandbox POST /graph/solve is no longer called from the UI (the endpoint
// stays for its golden-math tests until the P6 cleanup). Auto-tune still
// rides its sandbox endpoint until it is re-pointed (P6). Live backend only
// (no mock fallback). The hook is mounted by the GraphViewer view, so lit
// nodes reset on a workspace-tab switch (and re-seed from the shared lit
// designation + Options graph-prior defaults).
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

/** Posterior state of one node on the chart (the production solve mapped via
 *  useGraphExtrapolation.asSolveNode; historically the sandbox solve shape). */
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
  /** True when this node carried an observation. */
  observed: boolean;
}

/** Production propagation operator (message arc; hybrid stays config-only). */
export type PropagationMode = "smooth_field" | "precision_messages";

/** §9.2 calendar precision families. */
export type CalendarDecay = "inverse_sqrt_gap" | "constant" | "log_distance";

/** U2 per-ticker calendar-policy override; null numeric fields inherit the
 *  request-level dials (mirrors the backend CalendarPolicyOverride). */
export interface CalendarOverride {
  enabled: boolean;
  /** §9.2 precision scale (1/vol²), or null ⇒ inherit. */
  precisionScale: number | null;
  /** §8.1 shape exponent αT, or null ⇒ inherit. */
  betaExponent: number | null;
}

/**
 * Tunable hyperparameters of the increment prior Q_Δ and the graph edges,
 * mirroring the backend GraphSolverParams schema. Scales multiply the
 * per-handle base regime; weights are null when the service defaults apply.
 * The message-mode knobs (alphaT / amplitudes / precision family) only ride
 * the production request when propagationMode = "precision_messages".
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
  /** Propagation operator (smooth_field = the legacy path, byte-identical). */
  propagationMode: PropagationMode;
  /** §8.1 calendar amplitude SHAPE exponent alphaT (locked default 1.0). */
  alphaT: number;
  /** §8.4 amplitude LEVEL multipliers ρ (desk = 1; learned ≈ 0.23 / 0.39). */
  ampCal: number;
  ampCross: number;
  /** §9.2 calendar precision family (Phase-0 empirical seeds). */
  calPrecision: number;
  calEpsilon: number;
  calDecay: CalendarDecay;
  /** Cross-relation message precision scale (Phase-0 index seed). */
  crossPrecision: number;
  /** U2 calendar policy: global switch + per-ticker overrides. */
  calendarEnabled: boolean;
  calendarOverrides: Record<string, CalendarOverride>;
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

/** Default solver regime: legacy behavior (OT off, service edge weights,
 *  smooth-field operator, spec-default message knobs). */
const DEFAULT_PARAMS: SolverParams = {
  etaScale: 1,
  kappaScale: 1,
  lambdaScale: 0,
  nu: 0.1,
  calendarWeight: null,
  crossWeight: null,
  propagationMode: "smooth_field",
  alphaT: 1,
  ampCal: 1,
  ampCross: 1,
  calPrecision: 1700,
  calEpsilon: 0.97,
  calDecay: "inverse_sqrt_gap",
  crossPrecision: 13000,
  calendarEnabled: true,
  calendarOverrides: {},
};

/** Options graph-prior defaults that seed the solver panel. */
interface GraphPriorDefaults {
  graphKappaScale: number;
  graphEtaScale: number;
  graphLambdaScale: number;
  graphNu: number;
  graphPropagationMode?: string;
}

/** Apply the Options graph-prior defaults to untouched solver params. */
function seedSolverParams(p: SolverParams, o: GraphPriorDefaults): SolverParams {
  const untouched =
    p.kappaScale === DEFAULT_PARAMS.kappaScale &&
    p.etaScale === DEFAULT_PARAMS.etaScale &&
    p.lambdaScale === DEFAULT_PARAMS.lambdaScale &&
    p.nu === DEFAULT_PARAMS.nu &&
    p.propagationMode === DEFAULT_PARAMS.propagationMode;
  const mode: PropagationMode =
    o.graphPropagationMode === "precision_messages"
      ? "precision_messages"
      : "smooth_field"; // hybrid stays config-only — never a UI default
  return untouched
    ? {
        ...p,
        kappaScale: o.graphKappaScale,
        etaScale: o.graphEtaScale,
        lambdaScale: o.graphLambdaScale,
        nu: o.graphNu,
        propagationMode: mode,
      }
    : p;
}

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

/** Click-to-light default: +1.0 vol pt (visible propagation); designation-
 *  seeded lit nodes start at 0 (observed anchors, no perturbation). */
const DEFAULT_D_ATM_VOL = 0.01;

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Persist a node's lit/dark designation (fire-and-forget; keeps Universe and
 *  Graph in sync). */
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
  /** Replace the whole what-if pulse set (scenario shortcuts). LOCAL only —
   *  unlike toggleLit this never rewrites the shared lit/dark designation. */
  replaceLit: (entries: Record<string, number>) => void;
  /** Current solver hyperparameters. */
  params: SolverParams;
  /** Update one solver hyperparameter. */
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
  /** Reset all solver hyperparameters to the default regime. */
  resetParams: () => void;
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
  const [autotuning, setAutotuning] = useState(false);
  const [autotuneResult, setAutotuneResult] = useState<AutotuneResult | null>(null);
  const [autotuneError, setAutotuneError] = useState<string | null>(null);

  // Seed the lit (observed) set from the shared designation exactly once, on
  // the first successful node load; subsequent Retries keep the user's edits.
  const seededRef = useRef(false);

  // Seed the solver hyperparameters from the Options graph-prior defaults once
  // (κ prior strength / η reach / λ OT flux / ν); edge weights stay at the
  // service defaults. Best-effort — failures keep DEFAULT_PARAMS.
  const paramsSeededRef = useRef(false);
  useEffect(() => {
    if (paramsSeededRef.current) return;
    const controller = new AbortController();
    api
      .get<GraphPriorDefaults>("/settings/options", { signal: controller.signal })
      .then((o) => setParams((p) => seedSolverParams(p, o)))
      .catch(() => undefined)
      .finally(() => (paramsSeededRef.current = true));
    return () => controller.abort();
  }, []);

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

  const replaceLit = useCallback((entries: Record<string, number>) => {
    setLit({ ...entries });
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

  const autotune = useCallback(async (): Promise<void> => {
    const observations = observationList();
    if (observations.length < 2) return; // LOO needs >= 2 observations
    setAutotuning(true);
    setAutotuneError(null);
    try {
      // Autotune sweeps a leave-one-out grid over eta — slow on big universes.
      const res = await api.post<AutotuneResult>("/graph/autotune", {
        body: { observations, ...paramsBody(params) },
        timeoutMs: 300_000,
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
    replaceLit,
    params,
    setParam,
    resetParams,
    autotune,
    autotuning,
    autotuneResult,
    autotuneError,
  };
}
