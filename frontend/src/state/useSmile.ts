// Data-loading hook for the Smile Viewer.
//
// Talks to the FastAPI backend (GET /universe, GET /smiles/{ticker}/{expiry})
// and falls back to the built-in mock smile when the backend is unreachable,
// so `npm run dev` keeps working standalone. The consuming view only sees a
// uniform { smile, universe, source, ... } surface.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getMockSmile } from "../lib/mockData";
import type { SmileData } from "../lib/mockData";

/** Quote-fitting objective, passed to the backend as `fit_mode`. */
export type FitMode = "mid" | "bidask" | "haircut";

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
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  setTicker: (ticker: string) => void;
  setExpiry: (expiry: string) => void;
  setFitMode: (mode: FitMode) => void;
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

  // (Re)load the smile whenever the live selection or fit mode changes.
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
  }, [source, ticker, expiry, fitMode, fallBackToMock]);

  /** Select a ticker and jump to its mid-ladder expiry. */
  const setTicker = useCallback(
    (next: string) => {
      setTickerState(next);
      setExpiryState(midLadderExpiry(universe?.expiries[next] ?? []));
    },
    [universe],
  );

  return {
    smile,
    universe,
    source,
    loading,
    refreshing,
    error,
    ticker,
    expiry,
    fitMode,
    setTicker,
    setExpiry: setExpiryState,
    setFitMode,
  };
}
