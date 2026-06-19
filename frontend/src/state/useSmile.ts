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
import type { DistributionData, Regime, ScenarioState } from "./useScenario";
import { useSpot } from "./useSpot";
import type { SpotState } from "./useSpot";

/** How often to re-poll /universe while the backend is reachable but has no
 *  data yet (provider warming up / throttled) or is unreachable — so the app
 *  reconnects to live automatically instead of latching onto the mock payload. */
const UNIVERSE_RETRY_MS = 2500;

/** Max smile-fetch retries before giving up on a node (the backend is reachable,
 *  so a persistent failure is a node-level error — surface it, never mock). */
const SMILE_MAX_RETRIES = 4;

/** Quote-fitting objective, passed to the backend as `fit_mode`. */
export type FitMode = "mid" | "bidask" | "haircut";

/** Quote-level edit verbs accepted by POST /smiles/{ticker}/{expiry}/edits. */
export type EditAction = "exclude" | "include" | "amend" | "reset";

/** Var-swap quote verbs accepted by POST .../varswap (volfit.api.varswap). */
export type VarSwapAction = "set" | "exclude" | "include" | "remove" | "reset";

/** Listing class of an expiry, driving the header's bulk filter chips. */
export type ExpiryClass = "daily" | "weekly" | "monthly" | "quarterly" | "leaps";

/** One expiry rung of a ticker's listed ladder. */
export interface UniverseExpiry {
  /** ISO date "YYYY-MM-DD". */
  expiry: string;
  /** Year-fraction to expiry. */
  t: number;
  /** Listing class (daily/weekly/monthly/quarterly/leaps); optional so a
   *  payload from an older backend still type-checks at the boundary. */
  expiryType?: ExpiryClass;
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

/**
 * First watchlist ticker whose ladder actually has expiries, or null if the
 * whole universe is empty. A live feed (notably Yahoo, which throttles
 * `Ticker.options`) can return an empty ladder for some names while others
 * have data — keying off `tickers[0]` alone would then drop a perfectly
 * connected backend into mock mode just because the first name came back bare.
 */
function firstPopulatedTicker(u: UniverseResponse): string | null {
  for (const t of u.tickers) {
    if ((u.expiries[t]?.length ?? 0) > 0) return t;
  }
  return null;
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
  /** Apply a var-swap quote edit (set/exclude/include/remove/reset) and refit. */
  applyVarSwap: (action: VarSwapAction, level?: number) => Promise<void>;
  undoVarSwap: () => Promise<void>;
  redoVarSwap: () => Promise<void>;
  /** Persist the current fit as the prior, then refetch the smile.
   *  No-op in mock mode; rejects (after surfacing editError) on failure. */
  savePrior: () => Promise<void>;
  /** Force a refetch of the current smile through the regular load path
   *  (used after server-side state changes, e.g. PUT /settings/fit). */
  reload: () => void;
  /** Re-fetch the universe after add/remove/load-universe, keeping a valid
   *  (ticker, expiry) selection; recovers from mock mode if the backend is up. */
  refreshUniverse: () => Promise<void>;
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
  /** Fast spot-move: the active per-ticker shift (proportional return). */
  spotReturn: number;
  /** Backend spot state (anchor/shifted spot, dynamics regime + SSR). */
  spotState: SpotState | null;
  /** Bumps on every applied spot move / calibration / fetch; view hooks fold it
   *  into their fetch deps so one bump re-pulls every workspace's views. */
  spotVersion: number;
  /** Force every workspace to re-pull its (transported / recalibrated) views. */
  refreshViews: () => void;
  /** Options spot mode: "static" (manual slider) or "realtime" (backend poll). */
  spotMode: "static" | "realtime";
  /** Move the spot (no recalibration): transports smile / term / LV grid. */
  setSpotReturn: (r: number) => void;
  /** Re-anchor: clear the shift and recalibrate at the live spot. */
  recalibrate: () => Promise<void>;
}

export function useSmile(): UseSmileResult {
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [ticker, setTickerState] = useState("");
  const [expiry, setExpiryState] = useState("");
  const [fitMode, setFitMode] = useState<FitMode>("mid");
  const fitModeSeeded = useRef(false); // seed fitMode from the saved default once
  // Monotonic counter so only the latest refreshUniverse() response is applied
  // (rapid expiry edits can resolve GET /universe out of order — see below).
  const universeRefreshSeq = useRef(0);
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

  /** Refetch the current node through the regular smile effect. */
  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);
  const live = source === "live";

  // One refresh counter folded into every workspace's fetchers (smile / term /
  // affine / surface). Bumped on a transported spot move, after a calibration,
  // or a backend fetch — the no-recal way to re-pull all the views at once.
  const [viewVersion, setViewVersion] = useState(0);
  const refreshViews = useCallback(() => setViewVersion((n) => n + 1), []);
  const spotVersion = viewVersion; // kept name: the version the fetchers depend on

  // Manual spot-move slider state (the backend scheduler owns real-time polling).
  const { spotReturn, spotState, setSpotReturn, recalibrate } = useSpot(
    live,
    ticker,
    refreshViews,
    spotVersion, // re-read the spot readout when the backend RT poll transports it
  );
  const [spotMode, setSpotMode] = useState<"static" | "realtime">("static");

  // Whether any smile has been displayed yet (read inside effects without
  // adding `smile` to dependency arrays, which would cause refetch loops).
  const hasSmileRef = useRef(false);
  // Latest `source`, readable inside the universe-poll closure without making it
  // a dependency (which would restart the poll on every source flip).
  const sourceRef = useRef(source);
  useEffect(() => {
    sourceRef.current = source;
  }, [source]);

  /** Switch the whole hook to the deterministic mock payload. */
  const fallBackToMock = useCallback((reason: string) => {
    const mock = getMockSmile();
    setSmile(mock);
    hasSmileRef.current = true;
    // Synthesize a single-node universe so the selectors still render.
    setUniverse({
      asOf: "mock",
      tickers: [mock.ticker],
      expiries: {
        // 2026-12-18 is a third-Friday December listing: quarterly class.
        [mock.ticker]: [{ expiry: mock.expiry, t: mock.T, expiryType: "quarterly" }],
      },
    });
    setTickerState(mock.ticker);
    setExpiryState(mock.expiry);
    setSource("mock");
    setError(reason);
    setLoading(false);
    setRefreshing(false);
  }, []);

  // On mount: load the universe and pick an initial (ticker, expiry), RETRYING
  // until live data is available. The mock payload is reserved for a genuinely
  // unreachable backend (so `npm run dev` works standalone) — it must NOT be
  // triggered by a reachable backend that just hasn't resolved a ladder yet.
  //
  // Two distinct failure modes, handled differently so a restart self-heals:
  //  * `/universe` returns 200 but every ladder is empty — the active provider
  //    is warming up / throttling a fresh process (Yahoo rate-limits the first
  //    burst) or temporarily capped. The backend IS reachable, so we stay on the
  //    live source, show a "connecting" state, and re-poll until a ladder
  //    appears. This is the bug behind the recurring false "Mock Data" on
  //    restart: the old code latched onto mock the instant the first payload was
  //    empty and never re-checked.
  //  * the request itself throws (connection refused / network) — the backend is
  //    down: fall back to mock for standalone dev, but keep polling so a backend
  //    that comes up later reconnects to live automatically.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const schedule = () => {
      timer = window.setTimeout(attempt, UNIVERSE_RETRY_MS);
    };

    const attempt = () => {
      api
        .get<UniverseResponse>("/universe", { signal: controller.signal })
        .then((u) => {
          if (cancelled) return;
          const firstTicker = firstPopulatedTicker(u);
          if (firstTicker === null) {
            // Reachable but no data yet: stay live, keep trying — never mock.
            setUniverse(u);
            setSource("live");
            setError("Connecting to market data…");
            setLoading(true);
            schedule();
            return;
          }
          setUniverse(u);
          setSource("live");
          setTickerState(firstTicker);
          setExpiryState(midLadderExpiry(u.expiries[firstTicker] ?? []));
          setError(null);
          setLoading(false);
          // Populated: stop polling; the smile effect now drives the load.
        })
        .catch((err: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          // Backend unreachable: show mock once (dev standalone), keep retrying.
          if (sourceRef.current !== "mock") {
            fallBackToMock(`Backend unreachable (${messageOf(err)})`);
          }
          schedule();
        });
    };

    attempt();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [fallBackToMock]);

  // (Re)load the smile whenever the live selection or fit mode changes
  // (or savePrior bumps reloadNonce after persisting a new prior).
  // Stale in-flight requests are aborted; the previous smile keeps showing
  // behind a `refreshing` flag until the replacement arrives.
  //
  // A failure here NEVER falls back to mock: the universe already loaded, so the
  // backend is reachable — a smile fetch can still fail transiently because the
  // node's CHAIN quotes are warming up / throttled even though its expiry ladder
  // resolved (Yahoo lists expiries before the quote pull recovers), or the fit
  // is momentarily unavailable. We surface the error and RETRY until it resolves;
  // mock is reserved exclusively for a genuinely unreachable backend (the
  // universe poll above). This is the other half of the false-"Mock Data" fix:
  // the app used to load the universe ("Live"), then drop to mock the instant the
  // first smile fetch failed.
  useEffect(() => {
    if (source !== "live" || ticker === "" || expiry === "") return;
    const controller = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    if (hasSmileRef.current) setRefreshing(true);

    const load = () => {
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
          setError(messageOf(err));
          if (hasSmileRef.current) {
            // A smile already shows: keep it, just surface the refit error.
            setRefreshing(false);
          } else if (++attempts < SMILE_MAX_RETRIES) {
            // Nothing on screen yet: the chain may still be warming — keep the
            // live "connecting" state and retry (never drop to mock).
            setLoading(true);
            timer = window.setTimeout(load, UNIVERSE_RETRY_MS);
          } else {
            // Persistent node-level failure (a real fit/data error, not an
            // outage): give up retrying, stay LIVE, and surface the error so the
            // user can pick another node — but never show the false mock badge.
            setLoading(false);
          }
        });
    };
    load();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // spotVersion: a spot move transports the smile; refetch via the same path.
  }, [source, ticker, expiry, fitMode, reloadNonce, spotVersion]);

  // Source the spot-scenario dynamics regime from the Options workspace — the
  // aside now carries only the spot slider (ROADMAP Phase 10 follow-up). A
  // numeric SSR ("custom") flows straight through as the regime. Re-runs after
  // Options is applied (its onApplied calls reload(), bumping reloadNonce), so a
  // regime change there propagates without a manual refresh.
  useEffect(() => {
    if (source !== "live") return;
    const controller = new AbortController();
    api
      .get<{ dynamicsRegime: string; ssr: number; spotMode: "static" | "realtime"; fitMode: FitMode }>(
        "/settings/options",
        { signal: controller.signal },
      )
      .then((o) => {
        const regime: Regime | number =
          o.dynamicsRegime === "custom" ? o.ssr : (o.dynamicsRegime as Regime);
        setScenario((s) => (s.regime === regime ? s : { ...s, regime }));
        setSpotMode(o.spotMode);
        // Seed the live fit target from the persisted default ONCE on load (the
        // Options "Fit target" control drives it live thereafter — re-seeding on
        // every reload would clobber an in-session change).
        if (!fitModeSeeded.current && o.fitMode) {
          fitModeSeeded.current = true;
          setFitMode(o.fitMode);
        }
      })
      .catch(() => {
        /* keep the current regime if Options is unreachable */
      });
    return () => controller.abort();
  }, [source, reloadNonce]);

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

  // Var-swap quote edits: same instant-refit contract as quote edits, but the
  // /varswap endpoints (shared with the Local Vol workspace). The returned
  // refit (now carrying the var-swap penalty) replaces the current smile.
  const postVarSwap = useCallback(
    async (suffix: "varswap" | "varswap/undo" | "varswap/redo", body?: unknown): Promise<void> => {
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

  const applyVarSwap = useCallback(
    (action: VarSwapAction, level?: number) => postVarSwap("varswap", { action, level }),
    [postVarSwap],
  );
  const undoVarSwap = useCallback(() => postVarSwap("varswap/undo"), [postVarSwap]);
  const redoVarSwap = useCallback(() => postVarSwap("varswap/redo"), [postVarSwap]);

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

  /** Re-fetch the universe (after the Universe tab edits it) and keep the
   *  selection valid: hold the current ticker/expiry when they survive, else
   *  fall back to the first ticker / mid-ladder expiry.
   *
   *  Rapid expiry toggles fire several refreshes whose GET /universe responses
   *  can resolve OUT OF ORDER (a slower earlier fetch landing after a newer
   *  one), which would clobber the shared universe with stale selections — the
   *  "left panel still says 9 selected while the picker shows 2" bug. A
   *  monotonic sequence guard drops every response but the most recent so only
   *  the latest backend state is ever applied. */
  const refreshUniverse = useCallback(async (): Promise<void> => {
    const seq = ++universeRefreshSeq.current;
    const u = await api.get<UniverseResponse>("/universe");
    if (seq !== universeRefreshSeq.current) return; // a newer refresh superseded this
    if (u.tickers.length === 0) return;
    // Keep the current ticker only if it still has a ladder; otherwise jump to
    // the first populated name (not blindly tickers[0], which may be empty).
    const keepTicker =
      ticker !== "" && (u.expiries[ticker]?.length ?? 0) > 0
        ? ticker
        : (firstPopulatedTicker(u) ?? u.tickers[0]);
    const ladder = u.expiries[keepTicker] ?? [];
    const keepExpiry = ladder.some((r) => r.expiry === expiry)
      ? expiry
      : midLadderExpiry(ladder);
    setUniverse(u);
    setSource("live");
    setTickerState(keepTicker);
    setExpiryState(keepExpiry);
  }, [ticker, expiry]);

  // Derived side-channels: SSR scenario overlay + lazy distribution views.
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
    applyVarSwap,
    undoVarSwap,
    redoVarSwap,
    savePrior,
    reload,
    refreshUniverse,
    scenario,
    setScenario,
    scenarioCurve,
    scenarioSsr,
    distribution,
    distributionLoading,
    loadDistribution,
    spotReturn,
    spotState,
    spotVersion,
    refreshViews,
    spotMode,
    setSpotReturn,
    recalibrate,
  };
}
