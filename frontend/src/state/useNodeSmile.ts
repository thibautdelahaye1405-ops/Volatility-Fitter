// Per-NODE smile state (UI SHELL v2 wave 3, C3 — extracted from useSmile).
//
// Everything about ONE (ticker, expiry): the smile fetch (with retries, never
// a mock fallback — that is the universe poll's job), quote / var-swap edits
// with undo-redo, Save prior, the spot-scenario overlay, the lazy risk-neutral
// distribution, and the per-ticker spot move. The universe-level session
// (universe, selection, fit mode, versions) stays in useSmile; a second editor
// group mounts this hook on ITS node through state/nodeScope so two nodes can
// show at once. `enabled: false` makes the hook inert (the focused group
// reads the root session instead of fetching the same node twice).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { SmileData, SmilePoint } from "../lib/mockData";
import { useDistribution, useScenarioCurve } from "./useScenario";
import type { DistributionData, Regime, ScenarioState } from "./useScenario";
import { useSpot } from "./useSpot";
import type { SpotFollow, SpotNote, SpotState } from "./useSpot";
import type { CalibScope } from "../lib/calibScope";

/** Quote-fitting objective, passed to the backend as `fit_mode`. */
export type FitMode = "mid" | "bidask" | "haircut";
/** Quote-level edit verbs accepted by POST /smiles/{ticker}/{expiry}/edits. */
export type EditAction = "exclude" | "include" | "amend" | "reset";
/** Var-swap quote verbs accepted by POST .../varswap (volfit.api.varswap). */
export type VarSwapAction = "set" | "exclude" | "include" | "remove" | "reset";
/** Where the currently displayed smile came from. */
export type SmileSource = "live" | "mock";

/** Retry cadence while a reachable backend has no chain for the node yet. */
export const UNIVERSE_RETRY_MS = 2500;
/** Max smile-fetch retries before giving up on a node (a persistent failure is
 *  a node-level error — surface it, never mock). */
const SMILE_MAX_RETRIES = 4;

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Short message for a failed quote edit (FastAPI `detail` when present). */
function editMessageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(err.body);
      if (typeof parsed === "object" && parsed !== null && typeof (parsed as { detail?: unknown }).detail === "string") {
        return (parsed as { detail: string }).detail;
      }
    } catch { /* non-JSON error body */ }
    return `Edit rejected (HTTP ${err.status})`;
  }
  return messageOf(err);
}

export interface NodeSmileResult {
  smile: SmileData | null;
  /** True until the very first smile (live or mock) is available. */
  loading: boolean;
  /** True while a newer smile is in flight and the previous one still shows. */
  refreshing: boolean;
  error: string | null;
  editError: string | null;
  applyEdit: (action: EditAction, index?: number, mid?: number) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  applyVarSwap: (action: VarSwapAction, level?: number) => Promise<void>;
  undoVarSwap: () => Promise<void>;
  redoVarSwap: () => Promise<void>;
  savePrior: () => Promise<void>;
  reload: () => void;
  scenario: ScenarioState;
  setScenario: (next: ScenarioState) => void;
  scenarioCurve: SmilePoint[] | null;
  scenarioSsr: number | null;
  distribution: DistributionData | null;
  distributionLoading: boolean;
  loadDistribution: () => void;
  spotReturn: number;
  spotState: SpotState | null;
  setSpotReturn: (r: number) => void;
  /** Follow the market spot or the scenario dial (Spot move card selector). */
  setFollow: (follow: SpotFollow) => Promise<void>;
  /** Recalibrate the ticker with the top bar's scope (background job). */
  recalibrate: (scope: CalibScope) => Promise<void>;
  /** Probe the market spot once (Spot move card). */
  probeLive: () => Promise<void>;
  spotNote: SpotNote | null;
}

export interface NodeSmileOptions {
  enabled?: boolean;
  source: SmileSource;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** The universe's view version (spot moves / calibrations refetch). */
  spotVersion: number;
  refreshViews: () => void;
  /** Bumped by the root session's reload() (settings applied, prior saved…). */
  reloadSignal: number;
  /** The spot-vol dynamics regime from Options (seeds the scenario). */
  regime: Regime | number;
  /** The mock smile to show when `source` is "mock". */
  mock: SmileData | null;
}

export function useNodeSmile(o: NodeSmileOptions): NodeSmileResult {
  const enabled = o.enabled ?? true;
  const live = enabled && o.source === "live";
  const { ticker, expiry, fitMode, spotVersion, refreshViews, reloadSignal } = o;
  const [smile, setSmile] = useState<SmileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [scenario, setScenario] = useState<ScenarioState>({ spotReturn: 0, regime: o.regime });
  const hasSmileRef = useRef(false);
  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

  // Mock mode: the deterministic payload IS the node.
  useEffect(() => {
    if (!enabled || o.source !== "mock" || o.mock === null) return;
    setSmile(o.mock);
    hasSmileRef.current = true;
    setLoading(false);
    setRefreshing(false);
  }, [enabled, o.source, o.mock]);

  // (Re)load the smile whenever the node / fit mode / a version changes. A
  // failure NEVER falls back to mock: the backend is reachable (the universe
  // loaded), so a failed fetch is a warming chain or a node-level error —
  // retry a few times, then surface it and stay live.
  useEffect(() => {
    if (!live || ticker === "" || expiry === "") return;
    const controller = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    if (hasSmileRef.current) setRefreshing(true);
    const load = () => {
      api
        .get<SmileData>(`/smiles/${ticker}/${expiry}`, { params: { fit_mode: fitMode }, signal: controller.signal })
        .then((data) => {
          setSmile(data);
          hasSmileRef.current = true;
          setError(null);
          setEditError(null);
          setLoading(false);
          setRefreshing(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setError(messageOf(err));
          if (hasSmileRef.current) setRefreshing(false);
          else if (++attempts < SMILE_MAX_RETRIES) { setLoading(true); timer = window.setTimeout(load, UNIVERSE_RETRY_MS); }
          else setLoading(false);
        });
    };
    load();
    return () => { controller.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [live, ticker, expiry, fitMode, reloadNonce, reloadSignal, spotVersion]);

  // Keep the scenario's regime in step with Options (spotReturn is the node's).
  useEffect(() => {
    setScenario((s) => (s.regime === o.regime ? s : { ...s, regime: o.regime }));
  }, [o.regime]);

  // Edits / undo / redo / var-swap: the backend refits and returns the updated
  // smile; on failure the current smile stays and only editError surfaces.
  const post = useCallback(async (suffix: string, body?: unknown): Promise<void> => {
    if (!live || ticker === "" || expiry === "") return;
    setRefreshing(true);
    try {
      const data = await api.post<SmileData>(`/smiles/${ticker}/${expiry}/${suffix}`, { params: { fit_mode: fitMode }, body });
      setSmile(data);
      hasSmileRef.current = true;
      setEditError(null);
    } catch (err: unknown) {
      setEditError(editMessageOf(err));
    } finally {
      setRefreshing(false);
    }
  }, [live, ticker, expiry, fitMode]);

  const applyEdit = useCallback((action: EditAction, index?: number, mid?: number) => post("edits", { action, index, mid }), [post]);
  const undo = useCallback(() => post("undo"), [post]);
  const redo = useCallback(() => post("redo"), [post]);
  const applyVarSwap = useCallback((action: VarSwapAction, level?: number) => post("varswap", { action, level }), [post]);
  const undoVarSwap = useCallback(() => post("varswap/undo"), [post]);
  const redoVarSwap = useCallback(() => post("varswap/redo"), [post]);

  /** Persist the current fit as the prior, then refetch through the regular path. */
  const savePrior = useCallback(async (): Promise<void> => {
    if (!live || ticker === "" || expiry === "") return;
    try {
      await api.post<{ saved: boolean }>(`/smiles/${ticker}/${expiry}/prior`);
    } catch (err: unknown) {
      setEditError(editMessageOf(err));
      throw err;
    }
    setEditError(null);
    setReloadNonce((n) => n + 1);
  }, [live, ticker, expiry]);

  const { spotReturn, spotState, setSpotReturn, setFollow, recalibrate, probeLive, spotNote } =
    useSpot(live, ticker, fitMode, refreshViews, spotVersion);
  const { scenarioCurve, scenarioSsr } = useScenarioCurve(live, ticker, expiry, fitMode, scenario);
  const { distribution, distributionLoading, loadDistribution } = useDistribution(live, ticker, expiry, fitMode, smile);

  return {
    smile, loading, refreshing, error, editError,
    applyEdit, undo, redo, applyVarSwap, undoVarSwap, redoVarSwap, savePrior, reload,
    scenario, setScenario, scenarioCurve, scenarioSsr,
    distribution, distributionLoading, loadDistribution,
    spotReturn, spotState, setSpotReturn, setFollow, recalibrate, probeLive, spotNote,
  };
}
