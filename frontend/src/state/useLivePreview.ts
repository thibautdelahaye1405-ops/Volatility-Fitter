// Live preview of the Graph lens (GRAPH ERGONOMICS ARC, E6): while the Live
// toggle is on, every change of the run body (a dial, a relation edit, the
// pulse set) re-solves after a short debounce with `preview: true` — the
// backend returns the same numbers as a Run but records NOTHING (no
// innovation history, no residual-store write, no inferred last run). The
// explicit Run button still commits. Switching Live on solves once at once.
import { useEffect, useRef } from "react";
import type { ExtrapolateBody } from "./useGraphExtrapolation";

export const LIVE_PREVIEW_DEBOUNCE_MS = 600;

interface LivePreviewOptions {
  live: boolean;
  /** The shell's run gate (source has observations, no preflight blocker). */
  enabled: boolean;
  body: ExtrapolateBody;
  run: (body: ExtrapolateBody) => Promise<void>;
}

export function useLivePreview({ live, enabled, body, run }: LivePreviewOptions): void {
  const bodyKey = JSON.stringify(body);
  const bodyRef = useRef(body);
  bodyRef.current = body;
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (!live || !enabled) return;
    const timer = setTimeout(() => {
      void runRef.current({ ...bodyRef.current, preview: true });
    }, LIVE_PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // bodyKey is the change signal (the body object is rebuilt every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, enabled, bodyKey]);
}
