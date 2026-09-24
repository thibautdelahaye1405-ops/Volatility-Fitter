// Live node ticks: ONE Server-Sent Events connection per viewed node
// (GET /smiles/{t}/{e}/table/stream, hosted by SmileViewer) pushing the node's
// LIVE market off the backend's streaming book (Massive WS / Bloomberg
// //blp/mktdata) at ~1 Hz. Frames are DELTAS keyed by STRIKE (4 dp, the
// table's precision): the Quote Table overlays them onto its calibrated rows
// and the Smile Chart draws them as live bid/ask beams at log(strike / its own
// forward) — no positional coupling, and robust to a spot move re-expressing
// moneyness. The reducer (`applyFrame`) is pure and unit-tested; the hook only
// owns the EventSource lifecycle (open when enabled and the tab is visible,
// close when hidden / unmounted — EventSource reconnects by itself) and the
// short-lived per-row flash set.
import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "./api";

/** One live OTM quote row (same conventions as the table rows). */
export interface LiveTickRow {
  key: string;
  strike: number;
  type: "C" | "P";
  k: number;
  bidIv: number;
  midIv: number;
  askIv: number;
  bidPrice: number;
  midPrice: number;
  askPrice: number;
  /** Fit-target band of the stream's fit mode (absent/null in "mid"), pure market. */
  targetLo?: number | null;
  targetHi?: number | null;
  /** The calibration quote at the same strike (click-through), -1 when none. */
  index?: number;
  /** The fit ROLLED to the live spot at this row's live moneyness (the table's
   *  market "Model IV"); null/absent when the node has no fit. */
  modelIv?: number | null;
}

/** How the node is served (backend AppState.stream_tier): its whole planned
 *  rung on the socket ("live"), the belly live with the wings from the
 *  provider's per-minute REST memory ("rest"), or not streaming ("none"). */
export type LiveTier = "live" | "rest" | "none";

/** One SSE event of the tick stream (backend LiveTableFrame). */
export interface LiveTableFrame {
  type: "ticks" | "status";
  streaming: boolean;
  ready: boolean;
  /** The node's tier (absent on an older backend = live). */
  tier?: LiveTier;
  /** The REST cadence (s) behind a "rest" node. */
  restSeconds?: number | null;
  full?: boolean;
  ts?: string | null;
  /** The FRAME's spot (a manual dial move's when one is set) and forward. */
  spot?: number | null;
  forward?: number | null;
  /** The book's actual underlying spot, independent of the dial. */
  liveSpot?: number | null;
  rows?: LiveTickRow[];
  gone?: string[];
  nLive?: number;
  /** The fit ROLLED to the live spot (k relative to `forward`); sent when the
   *  forward moved / the calibration changed; absent = unchanged. */
  model?: { k: number; vol: number }[] | null;
  /** The graph-inferred smile rolled to the live spot (same occasions, and
   *  after a new Run); absent = unchanged. */
  inferred?: { k: number; vol: number }[] | null;
}

export interface LiveTicksState {
  /** Live rows by key — the overlay the table reads. Empty when not streaming. */
  rows: Map<string, LiveTickRow>;
  /** The active source has a live book (badge shown). */
  streaming: boolean;
  /** The book served this node (false = "warming"). */
  ready: boolean;
  /** How the node is served — the badge says LIVE vs "1-min REST". */
  tier: LiveTier;
  restSeconds: number | null;
  /** Newest provider stamp of the live chain (ISO UTC), its spot and the live
   *  forward (the k reference of `rows` and `model`). */
  ts: string | null;
  spot: number | null;
  forward: number | null;
  /** The book's own spot (the Spot move card's streamed readout). */
  liveSpot: number | null;
  /** The fit rolled to the live spot (last received); null before the first. */
  model: { k: number; vol: number }[] | null;
  /** The graph-inferred smile rolled to the live spot (last received). */
  inferred: { k: number; vol: number }[] | null;
  /** Keys whose band moved in the LAST frame (cell flash); cleared shortly after. */
  flash: Set<string>;
  /** Frame counter — alternates the flash class so consecutive ticks re-animate. */
  seq: number;
  /** The stream connection is open (false while EventSource reconnects). */
  connected: boolean;
}

export const EMPTY_LIVE: LiveTicksState = {
  rows: new Map(),
  streaming: false,
  ready: false,
  tier: "none",
  restSeconds: null,
  ts: null,
  spot: null,
  forward: null,
  liveSpot: null,
  model: null,
  inferred: null,
  flash: new Set(),
  seq: 0,
  connected: false,
};

/** The overlay join key of a quote: its strike at 4 dp (mirrors the backend
 *  ``row_key``) — one OTM row per strike, so the side never has to match. */
export const liveKey = (strike: number): string => strike.toFixed(4);

/** Smallest band move (vol units, 0.5 bp) that counts as a visible tick. */
export const FLASH_EPS = 5e-5;

/** The badge text of a served node: "LIVE" on the socket, "1-min REST" (the
 *  cadence spelt in minutes when whole, else seconds) when the wings come
 *  from the REST memory; an older backend without a tier reads LIVE. */
export function liveTierLabel(tier: LiveTier, restSeconds: number | null): string {
  if (tier !== "rest") return "LIVE";
  const s = restSeconds ?? 60;
  const cadence = s % 60 === 0 ? `${s / 60}-min` : `${s}-s`;
  return `${cadence} REST`;
}

/** The tier a frame carries, folded onto the previous state: a frame that
 *  names its tier is authoritative (its restSeconds too — null once live);
 *  a frame without one keeps what we had. */
function tierOf(prev: LiveTicksState, frame: LiveTableFrame): Pick<LiveTicksState, "tier" | "restSeconds"> {
  if (frame.tier === undefined) return { tier: prev.tier === "none" ? "live" : prev.tier, restSeconds: prev.restSeconds };
  return { tier: frame.tier, restSeconds: frame.restSeconds ?? null };
}

/** Fold one frame into the state (pure). A `status` frame with streaming=false
 *  drops the overlay (the table falls back to its calibrated rows); a `ticks`
 *  frame merges (or, when `full`, replaces) rows and removes the `gone` keys. */
export function applyFrame(prev: LiveTicksState, frame: LiveTableFrame): LiveTicksState {
  if (frame.type === "status") {
    if (!frame.streaming) {
      return {
        ...prev, rows: new Map(), streaming: false, ready: false, tier: "none", restSeconds: null,
        flash: new Set(), ts: null, spot: null, forward: null, liveSpot: null, model: null, inferred: null,
      };
    }
    return { ...prev, ...tierOf(prev, frame), streaming: true, ready: frame.ready, rows: frame.ready ? prev.rows : new Map() };
  }
  const rows = frame.full ? new Map<string, LiveTickRow>() : new Map(prev.rows);
  const flash = new Set<string>();
  for (const r of frame.rows ?? []) {
    // Flash only MATERIAL moves: a spot tick re-inverts every strike at the live
    // forward (sub-bp drift on the whole smile), which would light the entire
    // table each second and drown the real quote changes.
    const before = prev.rows.get(r.key);
    if (!frame.full && (before === undefined || Math.abs(r.midIv - before.midIv) > FLASH_EPS
      || Math.abs(r.bidIv - before.bidIv) > FLASH_EPS || Math.abs(r.askIv - before.askIv) > FLASH_EPS)) {
      flash.add(r.key);
    }
    rows.set(r.key, r);
  }
  for (const key of frame.gone ?? []) rows.delete(key);
  return {
    ...prev,
    ...tierOf(prev, frame),
    rows,
    streaming: true,
    ready: true,
    ts: frame.ts ?? prev.ts,
    spot: frame.spot ?? prev.spot,
    forward: frame.forward ?? prev.forward,
    liveSpot: frame.liveSpot ?? prev.liveSpot,
    model: frame.model ?? prev.model,
    inferred: frame.inferred ?? prev.inferred,
    flash,
    seq: prev.seq + 1,
  };
}

/** How long a ticked cell stays highlighted (matches the CSS animation). */
const FLASH_MS = 900;

/** Subscribe to the node's live ticks while `enabled` (live backend + a node).
 *  `fitMode` selects the target band the rows carry (the stream reopens on change). */
export function useLiveTicks(ticker: string, expiry: string, enabled: boolean, fitMode = "mid"): LiveTicksState {
  const [state, setState] = useState<LiveTicksState>(EMPTY_LIVE);
  const flashTimer = useRef<number>(0);

  useEffect(() => {
    setState(EMPTY_LIVE);
    if (!enabled || ticker === "" || expiry === "" || typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    let stopped = false;
    const hidden = () => typeof document !== "undefined" && document.hidden;

    const close = () => {
      if (es) es.close();
      es = null;
      setState((s) => ({ ...s, connected: false }));
    };
    const open = () => {
      if (es || stopped) return;
      const url = new URL(
        `/smiles/${encodeURIComponent(ticker)}/${encodeURIComponent(expiry)}/table/stream`,
        API_BASE_URL,
      );
      url.searchParams.set("fit_mode", fitMode);
      const src = new EventSource(url);
      src.onopen = () => setState((s) => ({ ...s, connected: true }));
      src.onmessage = (e) => {
        let frame: LiveTableFrame;
        try {
          frame = JSON.parse(e.data) as LiveTableFrame;
        } catch {
          return; // malformed frame: the next one recovers
        }
        setState((s) => applyFrame(s, frame));
        // Clear the flash set after the animation so a quiet cell does not
        // re-flash when an unrelated re-render swaps its class.
        window.clearTimeout(flashTimer.current);
        flashTimer.current = window.setTimeout(
          () => setState((s) => (s.flash.size ? { ...s, flash: new Set() } : s)),
          FLASH_MS,
        );
      };
      src.onerror = () => setState((s) => ({ ...s, connected: false }));
      es = src;
    };
    // Hidden tab: drop the stream (no ticks for a table nobody sees); visible
    // again: reopen (the first frame is a `full` repaint).
    const onVisible = () => {
      if (stopped) return;
      if (hidden()) close();
      else open();
    };

    if (!hidden()) open();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      close();
      window.clearTimeout(flashTimer.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [ticker, expiry, enabled, fitMode]);

  return state;
}
