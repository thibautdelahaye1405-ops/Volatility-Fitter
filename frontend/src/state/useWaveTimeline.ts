// Reveal timeline for the graph solve cinematics: each time a new result set
// lands (the epoch increments), the posterior field is revealed one BFS hop
// ring at a time, hopMs per ring. Honest staging only — the hop numbers come
// from lib/graphWave (real graph distance); this hook merely paces the reveal.
// Respects prefers-reduced-motion (instant full reveal, no timer).
import { useCallback, useEffect, useRef, useState } from "react";

/** Dwell per hop ring (ms). */
const DEFAULT_HOP_MS = 160;

export interface WaveTimeline {
  /** Largest BFS hop currently revealed (Infinity = nothing gated). */
  revealedHop: number;
  /** True while the reveal is advancing hop by hop. */
  animating: boolean;
  /** Fast-forward to the fully revealed state (stops the timer). */
  skip: () => void;
}

export function useWaveTimeline(
  epoch: number,
  maxHop: number,
  hopMs: number = DEFAULT_HOP_MS,
): WaveTimeline {
  // Epoch 0 = no results yet: gate nothing.
  const [revealedHop, setRevealedHop] = useState(Number.POSITIVE_INFINITY);
  const [animating, setAnimating] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  /** Current hop of a running reveal (interval callbacks read/advance it). */
  const hopRef = useRef(0);
  // Read via a ref so a lit-set edit (which can change maxHop without a new
  // solve landing) neither restarts nor stalls a timeline mid-flight.
  const maxHopRef = useRef(maxHop);
  maxHopRef.current = maxHop;

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    stop();
    if (epoch === 0) {
      setRevealedHop(Number.POSITIVE_INFINITY);
      setAnimating(false);
      return;
    }
    // Accessibility: reduced motion reveals the whole field at once.
    const reduced =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || maxHopRef.current <= 0) {
      setRevealedHop(Number.POSITIVE_INFINITY);
      setAnimating(false);
      return;
    }
    hopRef.current = 0;
    setRevealedHop(0);
    setAnimating(true);
    timerRef.current = setInterval(() => {
      hopRef.current += 1;
      if (hopRef.current >= maxHopRef.current) {
        // Terminal state is Infinity, not maxHop: a later lit-set edit can
        // grow the BFS distances without a new solve, and a finished timeline
        // must never re-gate the posterior field.
        setRevealedHop(Number.POSITIVE_INFINITY);
        stop();
        setAnimating(false);
      } else {
        setRevealedHop(hopRef.current);
      }
    }, hopMs);
    return stop;
  }, [epoch, hopMs, stop]);

  const skip = useCallback(() => {
    stop();
    setRevealedHop(Number.POSITIVE_INFINITY);
    setAnimating(false);
  }, [stop]);

  return { revealedHop, animating, skip };
}
