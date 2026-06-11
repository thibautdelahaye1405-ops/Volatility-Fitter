// Data-loading hook for the Smile Viewer.
//
// Talks to the FastAPI backend (GET /universe, GET /smiles/{ticker}/{expiry},
// POST /smiles/{ticker}/{expiry}/edits|undo|redo) and falls back to the
// built-in mock smile when the backend is unreachable, so `npm run dev`
// keeps working standalone. The consuming view only sees a uniform
// { smile, universe, source, ... } surface.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { getMockSmile } from "../lib/mockData";
import type { SmileData, SmilePoint } from "../lib/mockData";
import { useDistribution, useScenarioCurve } from "./useScenario";
import type { DistributionData, ScenarioState } from "./useScenario";

/** Quote-fitting objective, passed to the backend as `fit_mode`. */
export type FitMode = "mid" | "bidask" | "haircut";

/** Quote-level edit verbs accepted by POST /smiles/{ticker}/{expiry}/edits. */
export type EditAction = "exclude" | "include" | "amend" | "reset";

/** One expiry rung of a ticker's listed ladder. */
export interface UniverseExpiry {
  /** ISO date "YYYY-MM-DD". */
  expiry: string;
  /** Year-fraction to expiry. */
  t: number;
}

/** Response of GET /universe. */
export interface UniverseResponse {
  asOf: string;
  tickers: string[];
  expiries: Record<string, UniverseExpiry[]>;
}

/** Where the currently displayed smile came from. */
export type SmileSource = "live" | "mock";

/**
 * Default expiry selection for a ladder: a mid-ladder rung (3rd if the
 * ladder has at least three expiries) so the initial smile is neither the
 * noisy front month nor an illiquid back month.
 */
function midLadderExpiry(ladder: UniverseExpiry[]): string {
  if (ladder.length === 0) return "";
  return (ladder.length > 2 ? ladder[2] : ladder[0]).expiry;
}

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Short message for a failed quote edit. FastAPI 422/404 payloads carry a
 * `detail` field; surface that verbatim, otherwise fall back to the status.
 */
function editMessageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(err.body);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        typeof (parsed as { detail?: unknown }).detail === "string"
      ) {
        return (parsed as { detail: string }).detail;
      }
    } catch {
      // Non-JSON error body: fall through to the generic message.
    }
    return `Edit rejected (HTTP ${err.status})`;
  }
  return messageOf(err);
}

/** Everything `useSmile` exposes to the view. */
export interface UseSmileResult {
  /** Currently displayed smile, or null before the first load completes. */
  smile: SmileData | null;
  universe: UniverseResponse | null;
  source: SmileSource;
  /** True until the very first smile (live or mock) is available. */
  loading: boolean;
  /** True while a newer smile is in flight and the previous one still shows. */
  refreshing: boolean;
  error: string | null;
  /** Last quote-edit failure (e.g. 422 invalid edit), cleared on success. */
  editError: string | null;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  setTicker: (ticker: string) => void;
  setExpiry: (expiry: string) => void;
  setFitMode: (mode: FitMode) => void;
  /** Apply a quote edit (exclude/include/amend/reset) and refit. */
  applyEdit: (action: EditAction, index?: number, mid?: number) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  /** Persist the current fit as the prior, then refetch the smile.
   *  No-op in mock mode; rejects (after surfacing editError) on failure. */
  savePrior: () => Promise<void>;
  /** Spot-scenario inputs (regime + spot return) driving the SSR overlay. */
  scenario: ScenarioState;
  setScenario: (next: ScenarioState) => void;
  /** Shifted smile under the scenario; null when the slider sits at 0,
   *  in mock mode, or when the scenario fetch failed. */
  scenarioCurve: SmilePoint[] | null;
  /** Skew-stickiness ratio reported by the scenario engine, or null. */
  scenarioSsr: number | null;
  /** Risk-neutral density/quantile of the current node (lazy; live only). */
  distribution: DistributionData | null;
  distributionLoading: boolean;
  /** Arm the distribution fetcher (first switch to a Density view). */
  loadDistribution: () => void;
}

export function useSmile(): UseSmileResult {
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [ticker, setTickerState] = useState("");
  const [expiry, setExpiryState] = useState("");
  const [fitMode, setFitMode] = useState<FitMode>("mid");
  const [smile, setSmile] = useState<SmileData | null>(null);
  const [source, setSource] = useState<SmileSource>("live");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  // Bumped after POST /prior so the regular smile effect refetches and the
  // updated `prior` curve flows through the normal load path.
  const [reloadNonce, setReloadNonce] = useState(0);
  // Spot-scenario inputs; the derived overlay lives in useScenarioCurve.
  const [scenario, setScenario] = useState<ScenarioState>({
    spotReturn: 0,
    regime: "sticky_moneyness",
  });

  // Whether any smile has been displayed yet (read inside effects without
  // adding `smile` to dependency arrays, which would cause refetch loops).
  const hasSmileRef = useRef(false);

  /** Switch the whole hook to the deterministic mock payload. */
  const fallBackToMock = useCallback((reason: string) => {
    const mock = getMockSmile();
    setSmile(mock);
    hasSmileRef.current = true;
    // Synthesize a single-node universe so the selectors still render.
    setUniverse({
      asOf: "mock",
      tickers: [mock.ticker],
      expiries: { [mock.ticker]: [{ expiry: mock.expiry, t: mock.T }] },
    });
    setTickerState(mock.ticker);
    setExpiryState(mock.expiry);
    setSource("mock");
    setError(reason);
    setLoading(false);
    setRefreshing(false);
  }, []);

  // On mount: load the universe and pick an initial (ticker, expiry).
  // Any failure (connection refused, non-2xx, empty payload) -> mock mode.
  useEffect(() => {
    const controller = new AbortController();
    api
      .get<UniverseResponse>("/universe", { signal: controller.signal })
      .then((u) => {
        const firstTicker = u.tickers[0];
        const ladder = firstTicker ? (u.expiries[firstTicker] ?? []) : [];
        if (!firstTicker || ladder.length === 0) {
          fallBackToMock("Backend returned an empty universe");
          return;
        }
        setUniverse(u);
        setSource("live");
        setTickerState(firstTicker);
        setExpiryState(midLadderExpiry(ladder));
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // unmounted, not an outage
        fallBackToMock(`Backend unreachable (${messageOf(err)})`);
      });
    return () => controller.abort();
  }, [fallBackToMock]);

  // (Re)load the smile whenever the live selection or fit mode changes
  // (or savePrior bumps reloadNonce after persisting a new prior).
  // Stale in-flight requests are aborted; the previous smile keeps showing
  // behind a `refreshing` flag until the replacement arrives.
  useEffect(() => {
    if (source !== "live" || ticker === "" || expiry === "") return;
    const controller = new AbortController();
    if (hasSmileRef.current) setRefreshing(true);
    api
      .get<SmileData>(`/smiles/${ticker}/${expiry}`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((data) => {
        setSmile(data);
        hasSmileRef.current = true;
        setError(null);
        setEditError(null); // fresh node / refit: stale edit errors are moot
        setLoading(false);
        setRefreshing(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        if (!hasSmileRef.current) {
          // Nothing on screen yet: degrade to mock rather than a blank view.
          fallBackToMock(`Smile fetch failed (${messageOf(err)})`);
          return;
        }
        // Keep the previous smile; just surface the error.
        setError(messageOf(err));
        setRefreshing(false);
      });
    return () => controller.abort();
  }, [source, ticker, expiry, fitMode, reloadNonce, fallBackToMock]);

  /** Select a ticker and jump to its mid-ladder expiry. */
  const setTicker = useCallback(
    (next: string) => {
      setTickerState(next);
      setExpiryState(midLadderExpiry(universe?.expiries[next] ?? []));
    },
    [universe],
  );

  // Shared POST helper for edits / undo / redo: the backend refits and
  // returns the updated smile, which replaces the current one. On failure
  // the current smile stays on screen and only `editError` is surfaced.
  // All edit endpoints are no-ops in mock mode (there is no fit session).
  const postEdit = useCallback(
    async (suffix: "edits" | "undo" | "redo", body?: unknown): Promise<void> => {
      if (source !== "live" || ticker === "" || expiry === "") return;
      setRefreshing(true);
      try {
        const data = await api.post<SmileData>(
          `/smiles/${ticker}/${expiry}/${suffix}`,
          { params: { fit_mode: fitMode }, body },
        );
        setSmile(data);
        hasSmileRef.current = true;
        setEditError(null);
      } catch (err: unknown) {
        setEditError(editMessageOf(err));
      } finally {
        setRefreshing(false);
      }
    },
    [source, ticker, expiry, fitMode],
  );

  const applyEdit = useCallback(
    (action: EditAction, index?: number, mid?: number) =>
      // undefined index/mid are dropped by JSON.stringify, as the API expects.
      postEdit("edits", { action, index, mid }),
    [postEdit],
  );
  const undo = useCallback(() => postEdit("undo"), [postEdit]);
  const redo = useCallback(() => postEdit("redo"), [postEdit]);

  /** Persist the current fit as the prior, then refetch through the regular
   *  smile effect (so `prior` updates atomically with the full payload). */
  const savePrior = useCallback(async (): Promise<void> => {
    if (source !== "live" || ticker === "" || expiry === "") return; // mock: no-op
    try {
      await api.post<{ saved: boolean }>(`/smiles/${ticker}/${expiry}/prior`);
    } catch (err: unknown) {
      setEditError(editMessageOf(err));
      throw err; // lets the caller skip its "Saved" confirmation
    }
    setEditError(null);
    setReloadNonce((n) => n + 1);
  }, [source, ticker, expiry]);

  // Derived side-channels: SSR scenario overlay + lazy distribution views.
  const live = source === "live";
  const { scenarioCurve, scenarioSsr } = useScenarioCurve(
    live,
    ticker,
    expiry,
    fitMode,
    scenario,
  );
  const { distribution, distributionLoading, loadDistribution } =
    useDistribution(live, ticker, expiry, fitMode, smile);

  return {
    smile,
    universe,
    source,
    loading,
    refreshing,
    error,
    editError,
    ticker,
    expiry,
    fitMode,
    setTicker,
    setExpiry: setExpiryState,
    setFitMode,
    applyEdit,
    undo,
    redo,
    savePrior,
    scenario,
    setScenario,
    scenarioCurve,
    scenarioSsr,
    distribution,
    distributionLoading,
    loadDistribution,
  };
}
