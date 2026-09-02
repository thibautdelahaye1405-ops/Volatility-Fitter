// Spot-move control for the shared smile session (the Spot move card).
//
// A ticker's spot FOLLOWS either the MARKET (the prevailing spot: streamed off
// the live book, else the last probe / fetched chain — the backend keeps the
// shift synced to it) or the SCENARIO (the dial: a hypothetical move the whole
// app, the node's live tick stream included, lives at). Neither recalibrates:
// the backend transports the calibrated smile / term / LV grid under the
// Options dynamics regime. This hook owns the selector, the dial (debounced
// PUT; a dial move selects the scenario), the live-spot readout (polled ~1 Hz
// while the provider streams — the book read is free), Recalibrate (the
// top-bar Calibrate verb for this ticker, same scope, same snapshot rule) and
// signals the session to refresh every workspace's views via `refreshViews`.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { SCOPE_SHORT } from "../lib/calibScope";
import type { CalibScope } from "../lib/calibScope";

export type SpotFollow = "market" | "scenario";

/** Response of GET/PUT /spot/{ticker} and PUT /spot/{ticker}/follow. */
export interface SpotState {
  ticker: string;
  /** The CALIBRATION spot — what the dial and the transport are relative to. */
  anchorSpot: number;
  /** Active proportional shift (0 = anchored). */
  spotReturn: number;
  /** anchorSpot × (1 + spotReturn): the spot every lens lives at right now. */
  shiftedSpot: number;
  regime: string;
  regimeSsr: number;
  /** What the spot follows: the market (synced) or the scenario (the dial). */
  follow: SpotFollow;
  /** Real-time spot mode pins "market" (the scheduler owns the shift). */
  followForced: boolean;
  /** The prevailing market spot: off the streaming book ("stream", ~1 Hz), the
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
  /** What a Recalibrate covers: the ticker's lit nodes (+ its LV surface). */
  litNodes: number;
  lvEnabled: boolean;
}

/** Response of POST /spot/{ticker}/calibrate (Recalibrate). */
export interface RecalibrateResult extends SpotState {
  calibrationStarted: boolean;
  /** A job was already running: nothing started (the dial is still cleared). */
  busy: boolean;
  /** A fresh synchronous quotes + spot snapshot was taken off the streaming
   *  book (false = the last fetched chain, no request). */
  snapshotted: boolean;
  scope: CalibScope;
}

/** Outcome line shown under the Recalibrate button. */
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
  /** Last spot state from the backend (anchor / market / scenario, follow, regime). */
  spotState: SpotState | null;
  /** The dial: set the hypothetical shift (debounced PUT; selects the scenario). */
  setSpotReturn: (r: number) => void;
  /** The selector: follow the market spot or the scenario. */
  setFollow: (follow: SpotFollow) => Promise<void>;
  /** Recalibrate this ticker with the top bar's scope (background job). */
  recalibrate: (scope: CalibScope) => Promise<void>;
  /** Probe the provider spot once (one request) and refresh the readout. */
  probeLive: () => Promise<void>;
  /** Outcome of the last Recalibrate / selector action, null when none. */
  spotNote: SpotNote | null;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** The status line for a Recalibrate outcome. */
export function recalibrateNote(r: RecalibrateResult): SpotNote {
  if (r.busy) {
    return { ok: false, text: "A calibration job is already running — the dial was reset; press again when idle." };
  }
  if (!r.calibrationStarted) {
    return { ok: false, text: `Nothing to calibrate: ${r.ticker} has no lit node.` };
  }
  const data = r.snapshotted ? "Book snapshot taken (quotes + spot)" : "Last fetched chain";
  return { ok: true, text: `${data} · calibrating ${r.ticker} — ${SCOPE_SHORT[r.scope]} at ${r.anchorSpot.toFixed(2)}…` };
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
  // the market sync / real-time spot polling and transports the surface,
  // bumping `spotVersion` via useWorkflow; without `refreshKey` here the readout
  // would stay frozen at mount. Mock mode shows no spot controls.
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
  // counter: the actions bump it themselves right after setting the note).
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
      // A dial move IS the scenario: reflect the selector at once too.
      setSpotState((s) => (s && s.follow !== "scenario" && !s.followForced ? { ...s, follow: "scenario" } : s));
      window.clearTimeout(putTimer.current);
      putTimer.current = window.setTimeout(() => applyShift(r), PUT_DEBOUNCE_MS);
    },
    [applyShift],
  );

  const setFollow = useCallback(async (follow: SpotFollow) => {
    if (!live || ticker === "") return;
    window.clearTimeout(putTimer.current); // a pending dial PUT must not undo the selection
    try {
      const s = await api.put<SpotState>(`/spot/${ticker}/follow`, { body: { follow } });
      setSpotState(s);
      setSpotReturnState(s.spotReturn); // market: the synced shift; scenario: the starting point
      setSpotNote(null);
      refreshViews();
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Selector failed: ${messageOf(err)}` });
    }
  }, [live, ticker, refreshViews]);

  const recalibrate = useCallback(async (scope: CalibScope) => {
    if (!live || ticker === "") return;
    try {
      // The snapshot is synchronous server-side (a book read, or nothing when
      // not streaming); the calibration itself is the background job.
      const r = await api.post<RecalibrateResult>(`/spot/${ticker}/calibrate`, {
        params: { fit_mode: fitMode, scope },
        timeoutMs: 120_000,
      });
      setSpotState(r);
      setSpotReturnState(0);
      setSpotNote(recalibrateNote(r));
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Recalibrate failed: ${messageOf(err)}` });
    }
    refreshViews(); // the shift is cleared: every view back to the anchor frame
  }, [live, ticker, fitMode, refreshViews]);

  const probeLive = useCallback(async () => {
    if (!live || ticker === "") return;
    try {
      // One probe for this ticker; a market follower's shift syncs to it server-side.
      await api.post(`/fetch/spots`, { body: { tickers: [ticker] }, timeoutMs: 60_000 });
      const s = await api.get<SpotState>(`/spot/${ticker}`);
      setSpotState(s);
      if (s.follow === "market") { setSpotReturnState(s.spotReturn); refreshViews(); } // a fresher market moves the surface
    } catch (err: unknown) {
      setSpotNote({ ok: false, text: `Spot probe failed: ${messageOf(err)}` });
    }
  }, [live, ticker, refreshViews]);

  return { spotReturn, spotState, setSpotReturn, setFollow, recalibrate, probeLive, spotNote };
}
