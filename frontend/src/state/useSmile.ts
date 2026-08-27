// Universe-level smile session (the root of truth behind SmileSessionProvider).
//
// Talks to the FastAPI backend (GET /universe, GET /settings/options) and
// falls back to the built-in mock smile when the backend is unreachable, so
// `npm run dev` keeps working standalone. Owns what is shared by every node:
// the universe + the selected (ticker, expiry), the fit mode, the view
// version every fetcher folds in, the spot mode and the dynamics regime. The
// selected node's own state (smile, edits, distribution, spot move) comes
// from useNodeSmile (UI SHELL v2 wave 3, C3 — a second editor group mounts
// that hook on its own node through state/nodeScope).
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getMockSmile } from "../lib/mockData";
import type { SmileData } from "../lib/mockData";
import type { Regime } from "./useScenario";
import { UNIVERSE_RETRY_MS, useNodeSmile } from "./useNodeSmile";
import type { FitMode, NodeSmileResult, SmileSource } from "./useNodeSmile";

export type { EditAction, FitMode, SmileSource, VarSwapAction } from "./useNodeSmile";

/** Listing class of an expiry, driving the header's bulk filter chips. */
export type ExpiryClass = "daily" | "weekly" | "monthly" | "quarterly" | "leaps";

/** One expiry rung of a ticker's listed ladder. */
export interface UniverseExpiry {
  /** ISO date "YYYY-MM-DD". */
  expiry: string;
  /** Year-fraction to expiry. */
  t: number;
  /** Listing class; optional so an older backend payload still type-checks. */
  expiryType?: ExpiryClass;
}

/** Response of GET /universe. */
export interface UniverseResponse {
  asOf: string;
  tickers: string[];
  expiries: Record<string, UniverseExpiry[]>;
}

/** Mid-ladder rung (3rd if ≥ 3 expiries): neither the noisy front month nor
 *  an illiquid back month. */
export function midLadderExpiry(ladder: UniverseExpiry[]): string {
  if (ladder.length === 0) return "";
  return (ladder.length > 2 ? ladder[2] : ladder[0]).expiry;
}

/** First ticker whose ladder has expiries (a throttled feed can return bare
 *  ladders for some names), or null when the whole universe is empty. */
function firstPopulatedTicker(u: UniverseResponse): string | null {
  for (const t of u.tickers) if ((u.expiries[t]?.length ?? 0) > 0) return t;
  return null;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Everything the session exposes (universe-level + the selected node's). */
export interface UseSmileResult extends NodeSmileResult {
  universe: UniverseResponse | null;
  source: SmileSource;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  setTicker: (ticker: string) => void;
  setExpiry: (expiry: string) => void;
  setFitMode: (mode: FitMode) => void;
  /** Re-fetch the universe (add/remove/load-universe), keeping a valid selection. */
  refreshUniverse: () => Promise<void>;
  /** Bumps on every applied spot move / calibration / fetch; view hooks fold it
   *  into their fetch deps so one bump re-pulls every workspace's views. */
  spotVersion: number;
  refreshViews: () => void;
  /** Options spot mode: "static" (manual slider) or "realtime" (backend poll). */
  spotMode: "static" | "realtime";
  /** Advances on reload() — node scopes refetch on it. */
  reloadSignal: number;
  /** The dynamics regime from Options (node scopes seed their scenario from it). */
  regime: Regime | number;
}

export function useSmile(): UseSmileResult {
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [ticker, setTickerState] = useState("");
  const [expiry, setExpiryState] = useState("");
  const [fitMode, setFitMode] = useState<FitMode>("mid");
  const fitModeSeeded = useRef(false);
  const universeRefreshSeq = useRef(0);
  const [source, setSource] = useState<SmileSource>("live");
  const [mock, setMock] = useState<SmileData | null>(null);
  const [universeError, setUniverseError] = useState<string | null>(null);
  const [reloadSignal, setReloadSignal] = useState(0);
  const [regime, setRegime] = useState<Regime | number>("sticky_moneyness");
  const [spotMode, setSpotMode] = useState<"static" | "realtime">("static");
  const [viewVersion, setViewVersion] = useState(0);
  const refreshViews = useCallback(() => setViewVersion((n) => n + 1), []);
  const reload = useCallback(() => setReloadSignal((n) => n + 1), []);
  const sourceRef = useRef(source);
  useEffect(() => { sourceRef.current = source; }, [source]);

  /** Switch the whole session to the deterministic mock payload. */
  const fallBackToMock = useCallback((reason: string) => {
    const m = getMockSmile();
    setMock(m);
    setUniverse({ asOf: "mock", tickers: [m.ticker], expiries: { [m.ticker]: [{ expiry: m.expiry, t: m.T, expiryType: "quarterly" }] } });
    setTickerState(m.ticker);
    setExpiryState(m.expiry);
    setSource("mock");
    setUniverseError(reason);
  }, []);

  // Universe load with retries: a reachable backend with empty ladders keeps
  // polling live (never mock); an unreachable one shows mock and keeps trying.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const schedule = () => { timer = window.setTimeout(attempt, UNIVERSE_RETRY_MS); };
    const attempt = () => {
      api.get<UniverseResponse>("/universe", { signal: controller.signal })
        .then((u) => {
          if (cancelled) return;
          const first = firstPopulatedTicker(u);
          setUniverse(u);
          setSource("live");
          if (first === null) { setUniverseError("Connecting to market data…"); schedule(); return; }
          setTickerState(first);
          setExpiryState(midLadderExpiry(u.expiries[first] ?? []));
          setUniverseError(null);
        })
        .catch((err: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          if (sourceRef.current !== "mock") fallBackToMock(`Backend unreachable (${messageOf(err)})`);
          schedule();
        });
    };
    attempt();
    return () => { cancelled = true; controller.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [fallBackToMock]);

  // Options → dynamics regime, spot mode, and the fit-target seed (once).
  useEffect(() => {
    if (source !== "live") return;
    const controller = new AbortController();
    api.get<{ dynamicsRegime: string; ssr: number; spotMode: "static" | "realtime"; fitMode: FitMode }>("/settings/options", { signal: controller.signal })
      .then((o) => {
        setRegime(o.dynamicsRegime === "custom" ? o.ssr : (o.dynamicsRegime as Regime));
        setSpotMode(o.spotMode);
        if (!fitModeSeeded.current && o.fitMode) { fitModeSeeded.current = true; setFitMode(o.fitMode); }
      })
      .catch(() => { /* keep the current regime if Options is unreachable */ });
    return () => controller.abort();
  }, [source, reloadSignal]);

  /** Select a ticker and jump to its mid-ladder expiry. */
  const setTicker = useCallback((next: string) => {
    setTickerState(next);
    setExpiryState(midLadderExpiry(universe?.expiries[next] ?? []));
  }, [universe]);

  /** Re-fetch the universe, keeping the selection when it survives. Rapid
   *  refreshes can resolve out of order: only the newest response applies. */
  const refreshUniverse = useCallback(async (): Promise<void> => {
    const seq = ++universeRefreshSeq.current;
    const u = await api.get<UniverseResponse>("/universe");
    if (seq !== universeRefreshSeq.current || u.tickers.length === 0) return;
    const keepTicker = ticker !== "" && (u.expiries[ticker]?.length ?? 0) > 0 ? ticker : (firstPopulatedTicker(u) ?? u.tickers[0]);
    const ladder = u.expiries[keepTicker] ?? [];
    setUniverse(u);
    setSource("live");
    setTickerState(keepTicker);
    setExpiryState(ladder.some((r) => r.expiry === expiry) ? expiry : midLadderExpiry(ladder));
  }, [ticker, expiry]);

  const node = useNodeSmile({
    source, ticker, expiry, fitMode, spotVersion: viewVersion, refreshViews, reloadSignal, regime, mock,
  });

  return {
    ...node,
    error: universeError ?? node.error,
    loading: source === "live" && ticker === "" ? true : node.loading,
    reload,
    universe, source, ticker, expiry, fitMode,
    setTicker, setExpiry: setExpiryState, setFitMode, refreshUniverse,
    spotVersion: viewVersion, refreshViews, spotMode, reloadSignal, regime,
  };
}
