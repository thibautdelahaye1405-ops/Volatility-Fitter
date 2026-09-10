// The Series lens's pacer (roadmap §3.4), on the useWaveTimeline doctrine
// lib/lvTrace.ts already follows: a setInterval advances the playhead one
// frame per dwell while `playing`; the terminal frame is absorbing unless
// loop; the state is re-keyed on `epoch` (a new series → frame 0, paused —
// a series NEVER autoplays); the index is re-clamped whenever the frame
// count changes (a live series still harvesting grows under the playhead).
//
// prefers-reduced-motion: nothing autoplays anyway, so the short-circuit the
// other timelines apply has nothing to skip; while the user has explicitly
// pressed play the dwell is CAPPED at 1× (speeds above 1× read as 1×), never
// faster — the speed menu itself keeps its value.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  applyAction,
  clampIndex,
  frameDwellMs,
  initialPlayback,
  tickPlayback,
} from "../lib/seriesPlayback";
import type { PlaybackAction, SeriesPlayback } from "../lib/seriesPlayback";

/** Matches the useWaveTimeline / LvTracePlayer accessibility check. */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export interface SeriesPlaybackHandle {
  playback: SeriesPlayback;
  /** Merge a patch (speed, loop, a scrub — the transport's onChange). */
  update: (patch: Partial<SeriesPlayback>) => void;
  /** Apply a transport / keyboard action (lib/seriesPlayback.applyAction). */
  act: (action: PlaybackAction) => void;
}

export function useSeriesPlayback(nFrames: number, epoch: string): SeriesPlaybackHandle {
  const [playback, setPlayback] = useState<SeriesPlayback>(initialPlayback);

  // Epoch re-key during render (the derived-state idiom): a new series
  // starts at frame 0, paused, before anything paints under the old index.
  // Re-clamp when the frame count moves (a series growing / a lane set that
  // changes the ready count) — without touching play / speed / loop. The
  // two render-time updates are exclusive: the re-key's reset must never be
  // overwritten by a clamp of the OLD index in the same render.
  const [prevEpoch, setPrevEpoch] = useState(epoch);
  const clamped = clampIndex(playback.index, nFrames);
  if (epoch !== prevEpoch) {
    setPrevEpoch(epoch);
    setPlayback(initialPlayback());
  } else if (clamped !== playback.index) {
    setPlayback({ ...playback, index: clamped });
  }

  // The interval callbacks read the LIVE frame count through a ref, so a
  // growing series neither restarts nor stalls the pacer mid-play.
  const nRef = useRef(nFrames);
  nRef.current = nFrames;

  const canPlay = nFrames >= 2;
  useEffect(() => {
    if (!playback.playing || !canPlay) return;
    const speed = prefersReducedMotion() ? Math.min(playback.speed, 1) : playback.speed;
    const timer = window.setInterval(
      () => setPlayback((p) => tickPlayback(p, nRef.current)),
      frameDwellMs(speed),
    );
    return () => window.clearInterval(timer);
  }, [playback.playing, playback.speed, canPlay]);

  const update = useCallback((patch: Partial<SeriesPlayback>) => {
    setPlayback((p) => {
      const next = { ...p, ...patch };
      return { ...next, index: clampIndex(next.index, nRef.current) };
    });
  }, []);

  const act = useCallback((action: PlaybackAction) => {
    setPlayback((p) => applyAction(p, action, nRef.current));
  }, []);

  return { playback: clamped !== playback.index ? { ...playback, index: clamped } : playback, update, act };
}
