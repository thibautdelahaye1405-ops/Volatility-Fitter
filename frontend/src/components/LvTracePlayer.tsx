// LV calibration replay (V3.5 item 13): scrub / auto-play the accepted solver
// steps of the last traced affine fit.
//
// Post-hoc replay with honest numbers only — every frame is an iterate the
// solver actually accepted (nothing is repriced per frame). Drives:
//   (a) the nodal surface heatmap with the frame's sqrt-variance grid, and
//   (b) per-expiry rms bars (descending as prices converge) + a cost sparkline.
// Pacing per the useWaveTimeline doctrine: epoch-keyed auto-play once per fresh
// fit, prefers-reduced-motion short-circuits to the final frame, the terminal
// frame is absorbing (lib/lvTrace holds the pure logic, vitest-locked).
import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
import LocalVolHeatmap from "./LocalVolHeatmap";
import { useLvTrace } from "../state/useLvTrace";
import {
  FRAME_MS,
  clampFrame,
  costSparkPoints,
  initialPlayback,
  rmsBarHeights,
  scrubTo,
  tickPlayback,
  togglePlay,
  traceMaxRms,
} from "../lib/lvTrace";
import type { LvPlayback } from "../lib/lvTrace";

/** Matches the useWaveTimeline accessibility short-circuit. */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const BARS_W = 220;
const BARS_H = 42;
const SPARK_H = 30;

export default function LvTracePlayer({ ticker, epoch }: { ticker: string; epoch: number }) {
  const { trace, loading } = useLvTrace(ticker, epoch, true);
  const nFrames = trace?.frames.length ?? 0;
  const [playback, setPlayback] = useState<LvPlayback>({ index: 0, playing: false });

  // Epoch re-key: a freshly fetched trace restarts (and auto-plays) the replay.
  useEffect(() => {
    setPlayback(initialPlayback(nFrames, prefersReducedMotion()));
  }, [trace, nFrames]);

  // The pacer: one frame per FRAME_MS while playing (pure logic in lib/lvTrace).
  useEffect(() => {
    if (!playback.playing || nFrames < 2) return;
    const timer = window.setInterval(
      () => setPlayback((p) => tickPlayback(p, nFrames)),
      FRAME_MS,
    );
    return () => window.clearInterval(timer);
  }, [playback.playing, nFrames]);

  if (loading) {
    return <p className="text-[10px] text-slate-600">Loading fit replay…</p>;
  }
  if (!trace || nFrames === 0) {
    return (
      <p className="text-[10px] text-slate-600">
        No fit replay yet — run an LV calibration (Calibrate ▾).
      </p>
    );
  }

  const idx = clampFrame(playback.index, nFrames);
  const frame = trace.frames[idx];
  const costs = trace.frames.map((f) => f.cost);
  const maxRms = traceMaxRms(trace.frames);
  const heights = rmsBarHeights(frame.expiryRms, maxRms);
  const barW = heights.length > 0 ? BARS_W / heights.length : BARS_W;

  return (
    <div className="rounded-lg border border-slate-800 bg-surface-800/40 p-2">
      {/* Transport: play/pause + scrubber + honest frame readout */}
      <div className="mb-1 flex items-center gap-2">
        <button
          onClick={() => setPlayback((p) => togglePlay(p, nFrames))}
          title={playback.playing ? "Pause the replay" : "Play the replay"}
          className="rounded border border-slate-700 bg-surface-800 p-0.5 text-slate-300 hover:border-slate-600 hover:text-slate-100"
        >
          {playback.playing ? (
            <Pause size={11} strokeWidth={1.75} />
          ) : (
            <Play size={11} strokeWidth={1.75} />
          )}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, nFrames - 1)}
          value={idx}
          onChange={(e) => setPlayback(scrubTo(Number(e.target.value), nFrames))}
          className="h-1 min-w-0 flex-1 accent-violet-400"
          title="Scrub the accepted solver steps"
        />
        <span className="shrink-0 font-mono text-[9px] text-slate-500">
          {idx + 1}/{nFrames} · eval {frame.nEvals} · cost {frame.cost.toExponential(1)}
        </span>
      </div>

      {/* (a) The surface morphing: the frame's nodal sqrt-variance grid. */}
      <div className="h-36">
        <LocalVolHeatmap
          tNodes={trace.tNodes}
          xNodes={trace.xNodes}
          localVol={frame.localVol}
          legendLabel="σ_loc replay"
        />
      </div>

      {/* (b) Prices converging: per-expiry rms bars (stable scale over the
          whole replay, so they descend) + the cost curve tracing. */}
      <div className="mt-1 flex items-end gap-3">
        <svg
          width={BARS_W}
          height={BARS_H}
          className="shrink-0"
          role="img"
          aria-label="Per-expiry rms"
        >
          {heights.map((h, i) => (
            <rect
              key={i}
              x={i * barW + 1}
              y={BARS_H - h * BARS_H}
              width={Math.max(1, barW - 2)}
              height={Math.max(0.5, h * BARS_H)}
              className="fill-violet-400/70"
            >
              <title>{`τ ${trace.expiries[i]?.toFixed(2)} · rms ${frame.expiryRms[i]?.toExponential(1)}`}</title>
            </rect>
          ))}
        </svg>
        <div className="min-w-0 flex-1">
          <svg width="100%" height={SPARK_H} viewBox={`0 0 ${BARS_W} ${SPARK_H}`} preserveAspectRatio="none">
            <polyline
              points={costSparkPoints(costs, idx, BARS_W, SPARK_H)}
              fill="none"
              className="stroke-amber-400/80"
              strokeWidth={1.25}
            />
          </svg>
          <p className="text-right font-mono text-[9px] text-slate-600">cost (log)</p>
        </div>
      </div>
      <p className="mt-0.5 text-[9px] text-slate-600">
        per-expiry rms bars · accepted solver steps only
      </p>
    </div>
  );
}
