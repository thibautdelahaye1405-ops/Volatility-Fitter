// Labelled slider with a live readout (GRAPH ERGONOMICS ARC, E4): the one
// control the graph's dials and relation parameters share. Linear or LOG
// scale (the range input then moves in log10 space, so a σ from 0.25 to 10
// vol points or a β from 0.2 to 5 feels multiplicative), an optional tick
// mark at a reference value (e.g. β = 1), and a reset affordance when the
// caller passes `onReset`. Pure presentation — state lives with the caller.
import type { ReactNode } from "react";

interface SliderProps {
  label: ReactNode;
  title?: string;
  value: number;
  min: number;
  max: number;
  /** Step in VALUE units (linear) or in log10 units (log; default 0.01). */
  step?: number;
  log?: boolean;
  /** Readout formatter (default: 2 decimals). */
  format?: (v: number) => string;
  onChange: (v: number) => void;
  /** Optional reference mark (value units) drawn under the track. */
  mark?: number;
  /** When set, a ↺ button next to the readout calls it. */
  onReset?: () => void;
  resetTitle?: string;
  disabled?: boolean;
  /** Dims the whole row (e.g. an inherited value). */
  muted?: boolean;
  /** Extra readout chip (e.g. "auto"). */
  badge?: ReactNode;
  className?: string;
  /** Test hook. */
  testId?: string;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** Value → slider position (log10 under `log`). */
export function toPosition(value: number, log: boolean): number {
  return log ? Math.log10(Math.max(value, 1e-12)) : value;
}
/** Slider position → value. */
export function fromPosition(pos: number, log: boolean): number {
  return log ? 10 ** pos : pos;
}

export default function Slider({
  label,
  title,
  value,
  min,
  max,
  step,
  log = false,
  format = (v) => v.toFixed(2),
  onChange,
  mark,
  onReset,
  resetTitle = "Reset",
  disabled = false,
  muted = false,
  badge,
  className = "",
  testId,
}: SliderProps) {
  const lo = toPosition(min, log);
  const hi = toPosition(max, log);
  const pos = clamp(toPosition(value, log), lo, hi);
  const stepPos = step ?? (log ? 0.01 : (max - min) / 200);
  const markPct =
    mark !== undefined && hi > lo
      ? clamp(((toPosition(mark, log) - lo) / (hi - lo)) * 100, 0, 100)
      : null;

  return (
    <label
      className={["block", muted ? "opacity-60" : "", className].join(" ")}
      title={title}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-xs text-slate-400">{label}</span>
        <span className="flex shrink-0 items-center gap-1">
          {badge}
          <span className="font-mono text-xs font-medium text-slate-100" data-testid={testId ? `${testId}-readout` : undefined}>
            {format(value)}
          </span>
          {onReset !== undefined && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onReset();
              }}
              title={resetTitle}
              disabled={disabled}
              className="px-0.5 text-xs leading-none text-slate-600 transition-colors hover:text-slate-300 disabled:cursor-not-allowed"
            >
              ↺
            </button>
          )}
        </span>
      </span>
      <span className="relative mt-1 block">
        <input
          type="range"
          min={lo}
          max={hi}
          step={stepPos}
          value={pos}
          disabled={disabled}
          data-testid={testId}
          onChange={(e) => onChange(fromPosition(Number(e.target.value), log))}
          className="w-full cursor-pointer disabled:cursor-not-allowed"
          style={{ accentColor: "var(--color-accent-500)" }}
        />
        {markPct !== null && (
          <span
            className="pointer-events-none absolute -bottom-0.5 h-1.5 w-px bg-slate-500"
            style={{ left: `calc(${markPct}% + ${8 - markPct * 0.16}px)` }}
            aria-hidden
          />
        )}
      </span>
    </label>
  );
}
