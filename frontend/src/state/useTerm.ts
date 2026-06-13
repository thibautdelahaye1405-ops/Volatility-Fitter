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
// also moves the Smile tab and vice-versa. Events / clock mode are
// view-local: they reset when the user leaves the tab.
//
// Like the graph view there is NO mock fallback: the term fit only makes
// sense against the live backend, so a failed load surfaces an error and
// the view renders a retry card instead of synthetic data.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";

/** One editable event marker: adds `weight` years of diffusion at `time`. */
export interface TermEvent {
  /** Stable row identity (monotonic, never reused within a mount). */
  id: number;
  /** Real-time position of the event, in years. */
  time: number;
  /** Extra diffusion time added by the event, in years. */
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
  varSwapVol: number;
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
}

export function useTerm(): UseTermResult {
  // Underlying selection is shared with the Smile tab via the session.
  const { universe, ticker, setTicker } = useSmileSession();

  const [data, setData] = useState<TermResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumping this re-runs the load effect (the Retry button).
  const [attempt, setAttempt] = useState(0);

  const [events, setEvents] = useState<TermEvent[]>([]);
  const [eventsEnabled, setEventsEnabled] = useState(true);
  const [axisClock, setAxisClock] = useState<ClockMode>("real");

  // Whether any payload has been shown yet (read inside the load effect
  // without adding `data` to its dependency array).
  const hasDataRef = useRef(false);
  // Monotonic id source for event rows.
  const nextIdRef = useRef(1);

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

  const addEvent = useCallback(() => {
    setEvents((prev) => [
      ...prev,
      { id: nextIdRef.current++, time: 0.25, weight: 0.02, label: "event" },
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
  };
}
