// Pure playback logic of the Series lens (SERIES ARC S4, roadmap §3.4).
//
// A series is one ticker's ORDERED set of instants (frames); replay walks
// them one at a time — no interpolation between frames, the playhead always
// names a real instant. The pacing doctrine is the one lib/lvTrace.ts and
// state/useWaveTimeline.ts follow: a setInterval pacer, the terminal frame
// absorbing (playing stops there unless loop), scrubbing / stepping pauses,
// and a series NEVER autoplays — the user presses play. Everything here is
// pure so vitest locks the behaviour without a DOM; state/useSeriesPlayback
// owns the timer.

export interface SeriesPlayback {
  /** Current frame index, clamped into [0, nFrames-1] (0 when empty). */
  index: number;
  /** True while the pacer is auto-advancing. */
  playing: boolean;
  /** Playback speed multiplier (one of SPEEDS; 1× = BASE_FRAME_MS per frame). */
  speed: number;
  /** Wrap to frame 0 at the end instead of stopping. */
  loop: boolean;
}

/** The speed menu, slowest → fastest. */
export const SPEEDS = [0.25, 0.5, 1, 2, 4, 8] as const;
export type Speed = (typeof SPEEDS)[number];

/** Dwell per frame at 1× (ms). */
export const BASE_FRAME_MS = 500;

/** Dwell per frame at `speed` (a non-positive / non-finite speed reads as 1×). */
export function frameDwellMs(speed: number): number {
  const s = Number.isFinite(speed) && speed > 0 ? speed : 1;
  return BASE_FRAME_MS / s;
}

export type PlaybackAction =
  | "toggle"
  | "next"
  | "prev"
  | "next10"
  | "prev10"
  | "first"
  | "last"
  | "loop";

/** A fresh series: frame 0, PAUSED (never autoplays), 1×, no loop. */
export function initialPlayback(): SeriesPlayback {
  return { index: 0, playing: false, speed: 1, loop: false };
}

/** Clamp a frame index into [0, nFrames-1] (0 for an empty series / NaN). */
export function clampIndex(index: number, nFrames: number): number {
  if (!(nFrames > 0)) return 0;
  const i = Number.isFinite(index) ? Math.round(index) : 0;
  return Math.min(nFrames - 1, Math.max(0, i));
}

/** One pacer tick: advance a playing series by one frame. At the last frame
 *  a looping series wraps to 0; otherwise playing stops and the index stays
 *  (the terminal frame is absorbing). A paused series is only re-clamped. */
export function tickPlayback(p: SeriesPlayback, nFrames: number): SeriesPlayback {
  const index = clampIndex(p.index, nFrames);
  if (!p.playing) return { ...p, index };
  if (nFrames <= 1) return { ...p, index, playing: false };
  if (index >= nFrames - 1) {
    return p.loop ? { ...p, index: 0 } : { ...p, index, playing: false };
  }
  return { ...p, index: index + 1 };
}

/** Scrub to a frame: pauses, index clamped. */
export function scrubTo(p: SeriesPlayback, index: number, nFrames: number): SeriesPlayback {
  return { ...p, index: clampIndex(index, nFrames), playing: false };
}

/** Apply a transport action. Stepping pauses; toggling play at the last
 *  frame without loop restarts from 0 (the ⏵ button doubles as "replay"). */
export function applyAction(p: SeriesPlayback, action: PlaybackAction, nFrames: number): SeriesPlayback {
  const index = clampIndex(p.index, nFrames);
  switch (action) {
    case "toggle": {
      if (p.playing) return { ...p, index, playing: false };
      if (nFrames <= 1) return { ...p, index, playing: false };
      const atEnd = index >= nFrames - 1;
      return { ...p, index: atEnd && !p.loop ? 0 : index, playing: true };
    }
    case "next":
      return scrubTo(p, index + 1, nFrames);
    case "prev":
      return scrubTo(p, index - 1, nFrames);
    case "next10":
      return scrubTo(p, index + 10, nFrames);
    case "prev10":
      return scrubTo(p, index - 10, nFrames);
    case "first":
      return scrubTo(p, 0, nFrames);
    case "last":
      return scrubTo(p, nFrames - 1, nFrames);
    case "loop":
      return { ...p, index, loop: !p.loop };
  }
}

/** Keyboard vocabulary of the transport (roadmap §3.4): Space play/pause,
 *  ←/→ step (Shift = ×10), Home/End, L loop. Null for any other key. */
export function keyAction(e: { key: string; shiftKey: boolean }): PlaybackAction | null {
  switch (e.key) {
    case " ":
    case "Spacebar":
      return "toggle";
    case "ArrowRight":
      return e.shiftKey ? "next10" : "next";
    case "ArrowLeft":
      return e.shiftKey ? "prev10" : "prev";
    case "Home":
      return "first";
    case "End":
      return "last";
    case "l":
    case "L":
      return "loop";
    default:
      return null;
  }
}

/** Frame indices to prefetch around `index`: the `radius` frames AHEAD in
 *  the play direction (nearest first), then the `radius` frames behind
 *  (nearest first), within bounds, never `index` itself. */
export function prefetchWindow(
  index: number,
  nFrames: number,
  direction: 1 | -1,
  radius = 24,
): number[] {
  const out: number[] = [];
  if (!(nFrames > 0)) return out;
  const i0 = clampIndex(index, nFrames);
  for (const dir of [direction, -direction] as const) {
    for (let d = 1; d <= radius; d++) {
      const i = i0 + dir * d;
      if (i >= 0 && i < nFrames) out.push(i);
    }
  }
  return out;
}

/** Epoch ms of a wire instant — naive ISO stamps are UTC (the backend's
 *  convention), so a missing zone suffix reads as "Z". NaN when unparsable. */
export function parseInstantMs(ts: string): number {
  const zoned = /(?:[zZ]|[+-]\d\d:?\d\d)$/.test(ts);
  return Date.parse(zoned ? ts : `${ts}Z`);
}

/** Session-gap markers for the scrubber: indices i whose gap to frame i−1
 *  exceeds twice the median inter-frame gap (an overnight / weekend hole in
 *  an intraday series). Fewer than three instants ⇒ no gaps. */
export function sessionGaps(ts: string[]): number[] {
  if (ts.length < 3) return [];
  const ms = ts.map(parseInstantMs);
  const gaps: number[] = [];
  for (let i = 1; i < ms.length; i++) gaps.push(ms[i] - ms[i - 1]);
  const finite = gaps.filter((g) => Number.isFinite(g)).sort((a, b) => a - b);
  if (finite.length === 0) return [];
  const mid = finite.length >> 1;
  const median = finite.length % 2 === 1 ? finite[mid] : (finite[mid - 1] + finite[mid]) / 2;
  if (!(median > 0)) return [];
  const out: number[] = [];
  for (let i = 0; i < gaps.length; i++) if (gaps[i] > 2 * median) out.push(i + 1);
  return out;
}

/** The transport readout's instant: "YYYY-MM-DD HH:MM UTC" straight off the
 *  wire stamp (no timezone arithmetic — the stamp IS UTC). "—" when empty. */
export function formatFrameInstant(ts: string | null | undefined): string {
  if (!ts || ts.length < 16) return "—";
  return `${ts.slice(0, 10)} ${ts.slice(11, 16)} UTC`;
}
