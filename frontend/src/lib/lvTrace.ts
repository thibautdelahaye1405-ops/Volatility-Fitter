// Pure frames→display logic for the LV calibration replay (LvTracePlayer).
//
// The player follows the useWaveTimeline pacing doctrine: the timeline is
// keyed on the fit epoch (a fresh trace auto-plays once), prefers-reduced-
// motion short-circuits to the FINAL frame, and the terminal state is
// absorbing — a finished (or scrubbed-past) timeline clamps at the last frame
// and never wraps or re-gates. Everything here is pure so vitest can lock the
// pacer/scrubber behaviour without a DOM.

/** Dwell per replay frame (ms) — matches the graph wave's ring cadence. */
export const FRAME_MS = 160;

export interface LvPlayback {
  /** Current frame index, always clamped into [0, nFrames-1] (0 when empty). */
  index: number;
  /** True while the pacer is auto-advancing. */
  playing: boolean;
}

/** Clamp a frame index into the valid range (0 for an empty trace). */
export function clampFrame(index: number, nFrames: number): number {
  if (nFrames <= 0) return 0;
  return Math.min(nFrames - 1, Math.max(0, Math.round(index)));
}

/** Playback state for a freshly landed trace (the caller keys this on the fit
 *  epoch): reduced motion or a degenerate (≤1 frame) trace short-circuits to
 *  the final frame, paused; otherwise the replay auto-plays from frame 0. */
export function initialPlayback(nFrames: number, reducedMotion: boolean): LvPlayback {
  if (reducedMotion || nFrames <= 1) {
    return { index: clampFrame(nFrames - 1, nFrames), playing: false };
  }
  return { index: 0, playing: true };
}

/** One pacer tick: advance a playing timeline by one frame. The last frame is
 *  TERMINAL — playing stops there and the index stays clamped (never wraps). */
export function tickPlayback(p: LvPlayback, nFrames: number): LvPlayback {
  if (!p.playing || nFrames <= 1) return { index: clampFrame(p.index, nFrames), playing: false };
  const next = clampFrame(p.index + 1, nFrames);
  return { index: next, playing: next < nFrames - 1 };
}

/** Scrub to a frame: pauses playback, index clamped. */
export function scrubTo(index: number, nFrames: number): LvPlayback {
  return { index: clampFrame(index, nFrames), playing: false };
}

/** Toggle play/pause. Pressing play at the terminal frame RESTARTS the replay
 *  (the ⏵ button doubles as "replay"); playing an empty trace is a no-op. */
export function togglePlay(p: LvPlayback, nFrames: number): LvPlayback {
  if (p.playing) return { index: p.index, playing: false };
  if (nFrames <= 1) return { index: clampFrame(p.index, nFrames), playing: false };
  const atEnd = p.index >= nFrames - 1;
  return { index: atEnd ? 0 : p.index, playing: true };
}

/** Trace-wide max per-expiry rms — the STABLE bar scale for the whole replay,
 *  so the bars visibly descend as the fit converges (0 for an empty trace). */
export function traceMaxRms(frames: { expiryRms: number[] }[]): number {
  let max = 0;
  for (const f of frames) for (const v of f.expiryRms) if (v > max) max = v;
  return max;
}

/** Bar heights in [0, 1] for one frame's per-expiry rms vector, normalized to
 *  the trace-wide max (a zero max yields all-zero bars, never NaN). */
export function rmsBarHeights(expiryRms: number[], maxRms: number): number[] {
  if (!(maxRms > 0)) return expiryRms.map(() => 0);
  return expiryRms.map((v) => Math.min(1, Math.max(0, v / maxRms)));
}

/** Cost sparkline "x,y" polyline points up to AND including frame `index`,
 *  log-scaled y (costs span decades), x spread over the FULL frame count so
 *  the curve traces left→right as the replay advances. Empty when <2 points
 *  are drawable. */
export function costSparkPoints(
  costs: number[],
  index: number,
  width: number,
  height: number,
): string {
  const n = costs.length;
  const upTo = clampFrame(index, n);
  if (n < 2 || upTo < 1) return "";
  const logs = costs.map((c) => Math.log10(Math.max(c, 1e-300)));
  const lo = Math.min(...logs);
  const hi = Math.max(...logs);
  const span = hi - lo || 1;
  const pts: string[] = [];
  for (let i = 0; i <= upTo; i++) {
    const x = (i / (n - 1)) * width;
    const y = height - ((logs[i] - lo) / span) * height;
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}
