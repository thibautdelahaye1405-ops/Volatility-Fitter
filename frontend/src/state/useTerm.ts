// Data + interaction state for the Term-Structure workspace.
//
// Talks to the FastAPI term endpoint:
//   POST /term/{ticker} — fits every expiry of the ticker (fit-to-mid) and
//     returns per-expiry ATM handles (vol, total variance w0, var-swap vol,
//     worst fit error) plus a dense interpolated curve in both real time t
//     and event-dilated time tau, with a calendar-violation count.
//
// The underlying selection is shared with the Smile workspace through the
// smile session (same universe + ticker), so switching the underlying here
// also moves the Smile tab and vice-versa. The event calendar is now SHARED,
// persisted per ticker on the backend (GET/PUT /events/{ticker}) so it survives
// tab switches and ticker changes; the clock mode stays view-local.
//
// Like the graph view there is NO mock fallback: the term fit only makes
// sense against the live backend, so a failed load surfaces an error and
// the view renders a retry card instead of synthetic data.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";
import type { VarSwapAction } from "./useSmile";

/** One editable event marker: adds `weight` years of diffusion at `time`. */
export interface TermEvent {
  /** Stable row identity (monotonic, never reused within a mount). */
  id: number;
  /** Real-time position of the event, in years. */
  time: number;
  /** Extra equivalent days the event adds to its day (day weight = 1 + weight). */
  weight: number;
  label: string;
}

/** Per-expiry term-structure handles (POST /term/{ticker}). */
export interface TermPoint {
  /** ISO date "YYYY-MM-DD". */
  expiry: string;
  /** Real year-fraction to expiry. */
  t: number;
  /** Event-dilated year-fraction to expiry. */
  tau: number;
  atmVol: number;
  /** ATM total variance, atmVol² · t. */
  w0: number;
  /** Model's own fair var-swap vol. */
  varSwapVol: number;
  /** User-quoted var-swap vol (null when no quote on this expiry). */
  varSwapQuote?: number | null;
  /** Quote present but excluded from the fit penalty. */
  varSwapExcluded?: boolean;
  /** Worst absolute IV fit error across the expiry's quotes, in bp. */
  maxIvErrorBp: number;
}

/** Dense interpolated curve: variance is linear in the dilated clock. */
export interface TermCurve {
  t: number[];
  tau: number[];
  w: number[];
  vol: number[];
}

/** One discrete dividend ex-date positioned on the maturity axis. */
export interface DividendMarker {
  exDate: string;
  /** Ex-date year fraction (real-time axis). */
  t: number;
  /** Event-dilated position (dilated-time axis). */
  tau: number;
  /** Cash amount or proportional fraction, per the active dividend mode. */
  amount: number;
}

/** Response of POST /term/{ticker}. */
export interface TermResponse {
  ticker: string;
  points: TermPoint[];
  curve: TermCurve;
  calendarViolations: number;
  /** Discrete ex-dates within the curve range (empty under continuous mode). */
  dividends: DividendMarker[];
}

/** Maturity-axis clock: real calendar time vs event-dilated time. */
export type ClockMode = "real" | "dilated";

/** Collapse rapid event edits into one refit per pause. */
const EVENT_DEBOUNCE_MS = 300;

/** Serialize an event list to the backend wire shape (id-free, finite-only). */
function serializeEvents(evts: TermEvent[]): string {
  return JSON.stringify(
    evts
      .filter((ev) => Number.isFinite(ev.time) && Number.isFinite(ev.weight))
      .map(({ time, weight, label }) => ({ time, weight, label })),
  );
}

/**
 * Human-readable message from an unknown thrown value. FastAPI 404/422
 * payloads carry a `detail` field; surface that verbatim when present.
 */
function messageOf(err: unknown): string {
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
  }
  return err instanceof Error ? err.message : String(err);
}

/** Everything `useTerm` exposes to the Term-Structure view. */
export interface UseTermResult {
  /** Latest term-structure payload, or null before the first success. */
  data: TermResponse | null;
  /** True until the first load resolves (success or failure). */
  loading: boolean;
  /** True while a refit is in flight and the stale payload still shows. */
  refreshing: boolean;
  /** Last load failure message, or null. */
  error: string | null;
  /** Re-attempt the load after a failure (Retry button). */
  reload: () => void;
  /** Shared underlying selection (delegates to the smile session). */
  ticker: string;
  setTicker: (ticker: string) => void;
  /** All selectable underlyings of the session universe. */
  tickers: string[];
  /** Editable event markers (view-local). */
  events: TermEvent[];
  /** Append a default event (t=0.25y, weight=0.02y). */
  addEvent: () => void;
  updateEvent: (id: number, patch: Partial<Omit<TermEvent, "id">>) => void;
  removeEvent: (id: number) => void;
  /** Master toggle: send the events to the backend or ignore them. */
  eventsEnabled: boolean;
  setEventsEnabled: (on: boolean) => void;
  /** Maturity-axis clock mode for the chart. */
  axisClock: ClockMode;
  setAxisClock: (mode: ClockMode) => void;
  /** Auto-calibrate the event calendar from the term structure: place events
   *  before each expiry up to ``maxExpiry`` so the weighted forward variance is
   *  flat / monotone with small, sparse events; then refit term + smile. */
  autocalibrate: (maxExpiry: string) => Promise<void>;
  /** Whether var-swap quoting is enabled (OptionsSettings.varSwapEnabled). */
  varSwapEnabled: boolean;
  /** Edit one expiry's var-swap quote (set/exclude/include/remove/reset), then
   *  refit the term ladder and the shared Parametric smile. */
  applyVarSwap: (expiry: string, action: VarSwapAction, level?: number) => Promise<void>;
  undoVarSwap: (expiry: string) => Promise<void>;
  redoVarSwap: (expiry: string) => Promise<void>;
}

/**
 * Read-only view of a ticker's shared event calendar (GET /events/{ticker}),
 * for consumers that only need to DISPLAY events (e.g. the Local Vol Term),
 * not edit them. Editing stays in the Parametric Term via useTerm.
 */
export function useEvents(ticker: string): TermEvent[] {
  const [events, setEvents] = useState<TermEvent[]>([]);
  useEffect(() => {
    if (ticker === "") {
      setEvents([]);
      return;
    }
    const controller = new AbortController();
    api
      .get<{ events: { time: number; weight: number; label: string }[] }>(
        `/events/${ticker}`,
        { signal: controller.signal },
      )
      .then((r) => setEvents(r.events.map((e, i) => ({ id: i + 1, ...e }))))
      .catch(() => setEvents([]));
    return () => controller.abort();
  }, [ticker]);
  return events;
}

export function useTerm(): UseTermResult {
  // Underlying selection is shared with the Smile tab via the session.
  const { universe, ticker, setTicker, reload: reloadSmile } = useSmileSession();

  const [data, setData] = useState<TermResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumping this re-runs the load effect (the Retry button).
  const [attempt, setAttempt] = useState(0);

  const [events, setEvents] = useState<TermEvent[]>([]);
  const [eventsEnabled, setEventsEnabled] = useState(true);
  const [varSwapEnabled, setVarSwapEnabled] = useState(true);
  const [axisClock, setAxisClock] = useState<ClockMode>("real");

  // Seed the events-enabled default from the Options settings once (Phase 10).
  const eventsSeededRef = useRef(false);
  useEffect(() => {
    if (eventsSeededRef.current) return;
    const controller = new AbortController();
    api
      .get<{ eventsEnabled: boolean; varSwapEnabled: boolean }>("/settings/options", {
        signal: controller.signal,
      })
      .then((o) => {
        eventsSeededRef.current = true;
        setEventsEnabled(o.eventsEnabled);
        setVarSwapEnabled(o.varSwapEnabled);
      })
      .catch(() => {
        eventsSeededRef.current = true; // offline / mock: keep the default
      });
    return () => controller.abort();
  }, []);

  // Whether any payload has been shown yet (read inside the load effect
  // without adding `data` to its dependency array).
  const hasDataRef = useRef(false);
  // Monotonic id source for event rows.
  const nextIdRef = useRef(1);
  // Ticker whose persisted events are currently loaded, and the serialized
  // snapshot of what the backend holds — so the save effect (a) never writes
  // the old ticker's events to a freshly-selected one and (b) skips the echo
  // PUT right after a load.
  const loadedTickerRef = useRef<string>("");
  const savedRef = useRef<string>("");

  // Load the ticker's persisted event calendar whenever the underlying changes.
  useEffect(() => {
    if (ticker === "") return;
    const controller = new AbortController();
    api
      .get<{ events: { time: number; weight: number; label: string }[] }>(
        `/events/${ticker}`,
        { signal: controller.signal },
      )
      .then((r) => {
        const loaded = r.events.map((e) => ({ id: nextIdRef.current++, ...e }));
        savedRef.current = serializeEvents(loaded);
        loadedTickerRef.current = ticker;
        setEvents(loaded);
      })
      .catch(() => {
        // Offline / mock: treat as an empty calendar for this ticker.
        savedRef.current = serializeEvents([]);
        loadedTickerRef.current = ticker;
        setEvents([]);
      });
    return () => controller.abort();
  }, [ticker]);

  // Debounced snapshot of the events list: rapid keystrokes in the event
  // inputs collapse into a single refit ~300 ms after the last edit. The
  // initial state shares the `events` reference, so the first timer tick
  // is an Object.is bail-out and the mount fetch is not delayed.
  const [debouncedEvents, setDebouncedEvents] = useState<TermEvent[]>(events);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedEvents(events),
      EVENT_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [events]);

  // Persist the (debounced) event calendar per ticker. Guarded so it never
  // writes the previous ticker's events to a freshly-selected one (waits for
  // that ticker's load) and skips the echo PUT right after a load.
  useEffect(() => {
    if (ticker === "" || loadedTickerRef.current !== ticker) return;
    const payload = serializeEvents(debouncedEvents);
    if (payload === savedRef.current) return;
    savedRef.current = payload;
    api
      .put(`/events/${ticker}`, { body: { events: JSON.parse(payload) } })
      .catch(() => {
        /* offline / mock: keep the local edits, retry on the next change */
      });
  }, [debouncedEvents, ticker]);

  // (Re)fit the term structure whenever the underlying, the (debounced)
  // events, or the master toggle change. Stale in-flight requests are
  // aborted; the previous payload keeps showing behind `refreshing`.
  useEffect(() => {
    if (ticker === "") return; // session universe still loading
    const controller = new AbortController();
    if (hasDataRef.current) setRefreshing(true);
    else setLoading(true);
    setError(null);
    api
      .post<TermResponse>(`/term/${ticker}`, {
        body: {
          fitMode: "mid",
          // Drop half-typed rows (NaN from an emptied input) client-side
          // rather than tripping the backend's 422 validation.
          events: debouncedEvents
            .filter((ev) => Number.isFinite(ev.time) && Number.isFinite(ev.weight))
            .map(({ time, weight, label }) => ({ time, weight, label })),
          eventsEnabled,
        },
        signal: controller.signal,
      })
      .then((res) => {
        setData(res);
        hasDataRef.current = true;
        setLoading(false);
        setRefreshing(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setError(messageOf(err));
        setLoading(false);
        setRefreshing(false);
      });
    return () => controller.abort();
  }, [ticker, debouncedEvents, eventsEnabled, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // Var-swap quote edits, addressed to a specific expiry (the Term view edits
  // any rung). After the POST, refit the term ladder and the shared Parametric
  // smile so both reflect the new penalty.
  const postVarSwap = useCallback(
    async (expiry: string, suffix: string, body?: unknown): Promise<void> => {
      if (ticker === "" || expiry === "") return;
      try {
        await api.post(`/smiles/${ticker}/${expiry}/${suffix}`, { body });
      } catch {
        /* surfaced indirectly via the next load; keep the UI responsive */
      }
      reload();
      reloadSmile();
    },
    [ticker, reload, reloadSmile],
  );

  const applyVarSwap = useCallback(
    (expiry: string, action: VarSwapAction, level?: number) =>
      postVarSwap(expiry, "varswap", { action, level }),
    [postVarSwap],
  );
  const undoVarSwap = useCallback(
    (expiry: string) => postVarSwap(expiry, "varswap/undo"),
    [postVarSwap],
  );
  const redoVarSwap = useCallback(
    (expiry: string) => postVarSwap(expiry, "varswap/redo"),
    [postVarSwap],
  );

  const autocalibrate = useCallback(
    async (maxExpiry: string): Promise<void> => {
      if (ticker === "" || maxExpiry === "") return;
      try {
        const res = await api.post<{ events: { time: number; weight: number; label: string }[] }>(
          `/events/${ticker}/autocalibrate`,
          { body: { maxExpiry, fitMode: "mid" } },
        );
        const loaded = res.events.map((e) => ({ id: nextIdRef.current++, ...e }));
        savedRef.current = serializeEvents(loaded); // backend already saved; skip echo PUT
        loadedTickerRef.current = ticker;
        setEvents(loaded);
      } catch {
        /* offline / 404: leave the current calendar */
      }
      reload();
      reloadSmile();
    },
    [ticker, reload, reloadSmile],
  );

  const addEvent = useCallback(() => {
    // weight = EXTRA equivalent days the event adds to its day (day weight 1+N).
    setEvents((prev) => [
      ...prev,
      { id: nextIdRef.current++, time: 0.25, weight: 5, label: "event" },
    ]);
  }, []);

  const updateEvent = useCallback(
    (id: number, patch: Partial<Omit<TermEvent, "id">>) => {
      setEvents((prev) =>
        prev.map((ev) => (ev.id === id ? { ...ev, ...patch } : ev)),
      );
    },
    [],
  );

  const removeEvent = useCallback((id: number) => {
    setEvents((prev) => prev.filter((ev) => ev.id !== id));
  }, []);

  return {
    data,
    loading,
    refreshing,
    error,
    reload,
    ticker,
    setTicker,
    tickers: universe?.tickers ?? [],
    events,
    addEvent,
    updateEvent,
    removeEvent,
    eventsEnabled,
    setEventsEnabled,
    axisClock,
    setAxisClock,
    autocalibrate,
    varSwapEnabled,
    applyVarSwap,
    undoVarSwap,
    redoVarSwap,
  };
}
