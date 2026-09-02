// Spot-move control for the shared smile session (the Spot move card).
//
// The dial drives a hypothetical spot move (no recalibration): dragging it PUTs
// a per-ticker spot shift that the backend transports the calibrated smile /
// term / LV-grid by (volfit.dynamics.transport) — the node's live tick stream
// follows a dial move too. Real-time spot polling and timed options fetches
// are owned by the BACKEND scheduler (Options spotMode / optionsFetchMode);
// this hook handles the manual dial, the live-spot readout (polled ~1 Hz while
// the provider streams — the book read is free), **Sync to market** (the dial
// jumps to the live spot), **Re-anchor** (clear the shift, refetch the ticker's
// chain and calibrate its lit nodes in the background) and signals the session
// to refresh every workspace's views via `refreshViews`.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Response of GET/PUT /spot/{ticker}. */
export interface SpotState {
  ticker: string;
  /** The CALIBRATION spot — what the dial and the transport are relative to. */
  anchorSpot: number;
  /** Active proportional shift (0 = anchored). */
  spotReturn: number;
  /** anchorSpot × (1 + spotReturn): the scenario spot every lens lives at. */
  shiftedSpot: number;
  regime: string;
  regimeSsr: number;
  /** Who set the shift: the dial ("manual") or the live spot poll ("live"); null at 0. */
  shiftSource: "manual" | "live" | null;
  /** Latest known market spot: off the streaming book ("stream", ~1 Hz), the
   *  last probe ("probe") or the fetched chain's own spot ("chain"). */
  liveSpot: number | null;
  liveReturn: number | null;
  /** ISO UTC stamp of that reading. */
  liveAt: string | null;
  liveSource: "stream" | "probe" | "chain" | null;
  /** The active provider has a live book right now. */
  streaming: boolean;
  /** Human label of the active data source ("Bloomberg", "Yahoo Finance"…). */
  sourceLabel: string;
  /** What a Re-anchor calibrates: the ticker's lit nodes (+ its LV surface). */
  litNodes: number;
  lvEnabled: boolean;
}

/** Response of POST /spot/{ticker}/calibrate (Re-anchor). */
export interface ReanchorResult extends SpotState {
  calibrationStarted: boolean;
  /** A job was already running: nothing started (the shift is still cleared). */
  busy: boolean;
  /** The chain was refetched (false = feed miss, calibrating on the cached chain). */
  refetched: boolean;
}

/** Outcome line shown under the Re-anchor button. */
export interface SpotNote {
  text: string;
  ok: boolean;
}

/** Slider-drag PUT debounce (ms). */
const PUT_DEBOUNCE_MS = 120;
/** Live-readout poll cadence while the provider streams (the book read is free). */
export const STREAM_POLL_MS = 1000;

export interface UseSpotResult {
  /** Active proportional spot shift of the current ticker (0 = anchored). */
  spotReturn: number;
  /** Last spot state from the backend (anchor / market / scenario, regime, SSR). */
  spotState: SpotState | null;
  /** Set the hypothetical shift (debounced PUT; transports every view). */
  setSpotReturn: (r: number) => void;
  /** Re-anchor this ticker: clear the shift, refetch its chain and calibrate its
   *  lit nodes (+ LV surface) as the background job at the market spot. */
  recalibrate: () => Promise<void>;
  /** Move the dial to the live spot (a "live" shift: the tick stream keeps its own spot). */
  syncLive: () => Promise<void>;
  /** Probe the provider spot once (one request) and refresh the readout. */
  probeLive: () => Promise<void>;
  /** Outcome of the last Re-anchor / Sync, null when none. */
  spotNote: SpotNote | null;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** The status line for a Re-anchor outcome. */
export function reanchorNote(r: ReanchorResult): SpotNote {
  const scope = `${r.litNodes} node${r.litNodes === 1 ? "" : "s"}${r.lvEnabled ? " + LV" : ""}`;
  if (r.busy) {
    return { ok: false, text: "A calibration job is already running — dial reset and quotes refetched; press again when idle." };
  }
  if (!r.calibrationStarted) {
    return { ok: false, text: `Nothing to calibrate: ${r.ticker} has no lit node.` };
  }
  const feed = r.refetched ? "Quotes refetched" : "Feed miss — using the cached chain";
  return { ok: true, text: `${feed} · calibrating ${scope} at ${r.anchorSpot.toFixed(2)}…` };
}

export function useSpot(
  live: boolean,
  ticker: string,
  fitMode: string,
  refreshViews: () => void,
  refreshKey: number,
): UseSpotResult {
  const [spotReturn, setSpotReturnState] = useState(0);
  const [spotState, setSpotState] = useState<SpotState | null>(null);
  const [spotNote, setSpotNote] = useState<SpotNote | null>(null);
  const putTimer = useRef<number | undefined>(undefined);

  // Re-read the backend spot state whenever the ticker changes (each ticker holds
  // its own shift) OR the shared view counter bumps — the BACKEND scheduler owns
  // real-time spot polling and transports the surface, bumping `spotVersion` via
  // useWorkflow; without `refreshKey` here the readout would stay frozen at
  // mount and only refresh on a manual action / options fetch. Mock mode shows
  // no spot controls.
  useEffect(() => {
    if (!live || ticker === "") {
      setSpotState(null);
      setSpotReturnState(0);
      return;
    }
    const controller = new AbortController();
    api
      .get<SpotState>(`/spot/${ticker}`, { signal: controller.signal })
      .then((s) => {
        setSpotState(s);
        setSpotReturnState(s.spotReturn);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [live, ticker, refreshKey]);

  // The outcome line belongs to the ticker it was produced for (NOT to the view
  // counter: recalibrate/sync bump it themselves right after setting the note).
  useEffect(() => { setSpotNote(null); }, [ticker]);

  // Live readout: while the provider streams, re-read the state ~1 Hz (a free
  // book read server-side). Only the readout updates — the dial keeps the
  // user's value so a poll landing mid-drag never snaps the slider back.
  const streaming = spotState?.streaming ?? false;
  useEffect(() => {
    if (!live || ticker === "" || !streaming) return;
    const controller = new AbortController();
    const tick = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      api
        .get<SpotState>(`/spot/${ticker}`, { signal: controller.signal })
        .then((s) => setSpotState(s))
        .catch(() => {});
    };
    const timer = window.setInterval(tick, STREAM_POLL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [live, ticker, streaming]);

  const applyShift = useCallback(
    (r: number) => {
      if (!live || ticker === "") return;
      api
        .put<SpotState>(`/spot/${ticker}`, { body: { spotReturn: r } })
        .then((s) => {
          setSpotState(s);
          refreshViews();
        })
        .catch(() => {});
    },
    [live, ticker, refreshViews],
  );

  const setSpotReturn = useCallback(
    (r: number) => {
      setSpotReturnState(r); // immediate slider feedback
      window.clearTimeout(putTimer.current);
      putTimer.current = window.setTimeout(() => applyShift(r), PUT_DEBOUNCE_MS);
    },
    [applyShift],
  );

  const recalibrate = useCallback(async () => {
    if (!live || ticker === "") return;
    try {
      // The chain refetch is synchronous server-side (a feed round trip); the
      // calibration itself is the background job (progress via the status stream).
      const r = await api.post<ReanchorResult>(`/spot/${ticker}/calibrate`, {
        params: { fit_mode: fitMode },
        timeoutMs: 120_000,
      });
      setSpotState(r);
      setSpotReturnState(0);
      setSpotNote(reanchorNote(r));
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Re-anchor failed: ${messageOf(err)}` });
    }
    refreshViews(); // the shift is cleared: every view back to the anchor frame
  }, [live, ticker, fitMode, refreshViews]);

  const syncLive = useCallback(async () => {
    if (!live || ticker === "") return;
    try {
      await api.post(`/fetch/spots`, { body: { tickers: [ticker] }, timeoutMs: 60_000 });
      const s = await api.get<SpotState>(`/spot/${ticker}`);
      setSpotState(s);
      setSpotReturnState(s.spotReturn);
      setSpotNote(null);
      refreshViews();
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Sync failed: ${messageOf(err)}` });
    }
  }, [live, ticker, refreshViews]);

  const probeLive = useCallback(async () => {
    if (!live || ticker === "") return;
    try {
      await api.get(`/spot/${ticker}/live`, { timeoutMs: 60_000 });
      setSpotState(await api.get<SpotState>(`/spot/${ticker}`));
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Spot probe failed: ${messageOf(err)}` });
    }
  }, [live, ticker]);

  return { spotReturn, spotState, setSpotReturn, recalibrate, syncLive, probeLive, spotNote };
}
