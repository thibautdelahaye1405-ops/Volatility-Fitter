// The Series lens's transport bar (roadmap §3.4): ⏮ ◀ ▶/⏸ ▶ ⏭ · speed
// 0.25×…8× · loop · the frame-index-linear scrubber with session-gap and
// warm-up marks · the readout "YYYY-MM-DD HH:MM UTC · frame i/n · NBBO".
// Presentational: the pure playback logic lives in lib/seriesPlayback and
// the pacer in state/useSeriesPlayback — this bar reports actions
// (`onAction`) and direct state edits (`onChange`: a scrub, a speed, loop).
// The playhead always names a real instant: the readout reads the frame
// document under the index, never an interpolation.
import { useMemo } from "react";
import type { ReactNode } from "react";
import { ChevronFirst, ChevronLast, Pause, Play, Repeat, StepBack, StepForward } from "lucide-react";
import { SPEEDS, clampIndex, formatFrameInstant, scrubTo, sessionGaps } from "../../lib/seriesPlayback";
import type { PlaybackAction, SeriesPlayback } from "../../lib/seriesPlayback";
import { fracOf } from "../../lib/filmstrip";
import type { FrameDoc } from "../../lib/seriesTypes";

interface TransportBarProps {
  playback: SeriesPlayback;
  nFrames: number;
  /** The series' frame documents, in index order (the readout + the marks). */
  frames: FrameDoc[];
  onChange: (next: SeriesPlayback) => void;
  onAction: (action: PlaybackAction) => void;
}

const BTN =
  "rounded border border-slate-700 bg-surface-800 p-0.5 text-slate-300 hover:border-slate-600 hover:text-slate-100 disabled:cursor-default disabled:opacity-40 disabled:hover:border-slate-700 disabled:hover:text-slate-300";

/** The readout's quote-kind word: NBBO for real quotes, "marks" for closes. */
export function quoteKindLabel(kind: string | null | undefined): string {
  return kind === "marks" ? "marks" : "NBBO";
}

/** The readout text of frame `index` ("—" instant when the doc is missing). */
export function transportReadout(frames: readonly FrameDoc[], index: number, nFrames: number): string {
  const doc = frames[index] ?? null;
  const instant = formatFrameInstant(doc?.ts ?? null);
  const kind = quoteKindLabel(doc?.quoteKind);
  const warm = doc?.warmup ? " · warm-up" : "";
  return `${instant} · frame ${nFrames > 0 ? index + 1 : 0}/${nFrames} · ${kind}${warm}`;
}

export default function TransportBar({ playback, nFrames, frames, onChange, onAction }: TransportBarProps) {
  const index = clampIndex(playback.index, nFrames);
  const empty = nFrames <= 0;
  const gaps = useMemo(() => sessionGaps(frames.map((f) => f.ts)), [frames]);
  const warmups = useMemo(() => frames.filter((f) => f.warmup).map((f) => f.idx), [frames]);
  const readout = transportReadout(frames, index, nFrames);

  const iconBtn = (label: string, action: PlaybackAction, icon: ReactNode, pressed?: boolean) => (
    <button type="button" aria-label={label} title={label} className={BTN} disabled={empty} onClick={() => onAction(action)} aria-pressed={pressed}>
      {icon}
    </button>
  );

  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-surface-800/40 px-2 py-1" data-testid="series-transport">
      {/* Transport buttons */}
      <div className="flex shrink-0 items-center gap-1">
        {iconBtn("First frame", "first", <ChevronFirst size={12} strokeWidth={1.75} />)}
        {iconBtn("Step back", "prev", <StepBack size={12} strokeWidth={1.75} />)}
        {iconBtn(
          playback.playing ? "Pause" : "Play",
          "toggle",
          playback.playing ? <Pause size={12} strokeWidth={1.75} /> : <Play size={12} strokeWidth={1.75} />,
          playback.playing,
        )}
        {iconBtn("Step forward", "next", <StepForward size={12} strokeWidth={1.75} />)}
        {iconBtn("Last frame", "last", <ChevronLast size={12} strokeWidth={1.75} />)}
      </div>

      {/* Speed + loop */}
      <select
        aria-label="Speed"
        title="Playback speed (1× = 500 ms per frame)"
        value={String(playback.speed)}
        disabled={empty}
        onChange={(e) => onChange({ ...playback, speed: Number(e.target.value) })}
        className="shrink-0 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono text-[10px] text-slate-300"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={String(s)}>
            {s}×
          </option>
        ))}
      </select>
      <button
        type="button"
        aria-label="Loop"
        aria-pressed={playback.loop}
        title="Loop — wrap to the first frame at the end (L)"
        disabled={empty}
        onClick={() => onAction("loop")}
        className={[BTN, playback.loop ? "border-accent-500/60 bg-accent-500/15 text-accent-300" : ""].join(" ")}
      >
        <Repeat size={12} strokeWidth={1.75} />
      </button>

      {/* Scrubber (frame-index-linear) with gap / warm-up marks under it */}
      <div className="relative min-w-0 flex-1">
        <input
          type="range"
          aria-label="Frame"
          min={0}
          max={Math.max(0, nFrames - 1)}
          value={index}
          disabled={empty}
          onChange={(e) => onChange(scrubTo(playback, Number(e.target.value), nFrames))}
          className="h-1 w-full accent-violet-400"
          title="Scrub the frames (←/→ step, Shift ×10, Home/End)"
        />
        {(gaps.length > 0 || warmups.length > 0) && (
          <svg className="pointer-events-none absolute inset-x-0 bottom-0 h-1.5 w-full" aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 100 6">
            {warmups.map((i) => (
              <rect key={`w${i}`} data-mark="warmup" x={fracOf(i, nFrames) * 100 - 0.4} y={0} width={0.8} height={6} fill="rgb(148 163 184 / 0.55)" />
            ))}
            {gaps.map((i) => (
              <rect key={`g${i}`} data-mark="gap" x={fracOf(i, nFrames) * 100 - 0.35} y={0} width={0.7} height={6} fill="rgb(251 191 36 / 0.9)" />
            ))}
          </svg>
        )}
      </div>

      {/* Readout: the instant, the frame, the quote kind */}
      <span className="shrink-0 font-mono text-[10px] text-slate-400" data-testid="series-readout" title="The instant under the playhead — a real frame, never an interpolation">
        {readout}
      </span>
    </div>
  );
}
