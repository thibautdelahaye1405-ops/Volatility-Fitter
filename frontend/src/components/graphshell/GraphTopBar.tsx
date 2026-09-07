// Graph shell top bar (P5b U0 → GRAPH ERGONOMICS ARC, E4): the workflow
// spine's Configure → Run controls, at Level 0 only.
//
// LEFT: observation source (calibrations vs what-if), the operator in the
// ruled order — Layered (default) | Precision — with Smooth field shown only
// while it is the selected legacy operator (the door to it lives under the
// pane's Advanced section), the config pill (active version · staged edits ·
// Apply / Discard) and the LIVE preflight chip (Run gates on blockers only).
// RIGHT: the Live toggle (re-solve on every edit, non-persisting preview),
// the post-run summary, the last error, Clear field, and RUN — the single
// primary action (it records; a live preview never does).
import { Eraser, Zap } from "lucide-react";
import ConfigChip, { type ConfigChipBundle } from "./ConfigChip";
import PreflightChip from "./PreflightChip";
import SegmentedControl from "../SegmentedControl";
import type { PropagationMode } from "../../state/useGraph";
import type { UsePreflightResult } from "../../state/usePreflight";

/** Where the propagated observations come from. */
export type ObservationSource = "calibrations" | "manual";

/** Post-run summary strip (observed/extrapolated counts + max |shift|). */
export interface RunSummary {
  observed: number;
  extrapolated: number;
  maxAbs: number;
}

interface GraphTopBarProps {
  source: ObservationSource;
  setSource: (s: ObservationSource) => void;
  mode: PropagationMode;
  setMode: (m: PropagationMode) => void;
  /** Lit/dark composition of the displayed universe. */
  litCount: number;
  darkCount: number;
  preflight: UsePreflightResult;
  config: ConfigChipBundle;
  summary: RunSummary | null;
  /** The field on screen came from a live preview (nothing recorded). */
  previewField: boolean;
  live: boolean;
  setLive: (v: boolean) => void;
  error: string | null;
  canRun: boolean;
  busy: boolean;
  onRun: () => void;
  hasResults: boolean;
  onClear: () => void;
}

const chipClass = "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px]";

const MODES: { id: PropagationMode; label: string }[] = [
  { id: "layered_dynamic_harmonic", label: "Layered" },
  { id: "precision_messages", label: "Precision" },
];

export default function GraphTopBar({
  source,
  setSource,
  mode,
  setMode,
  litCount,
  darkCount,
  preflight,
  config,
  summary,
  previewField,
  live,
  setLive,
  error,
  canRun,
  busy,
  onRun,
  hasResults,
  onClear,
}: GraphTopBarProps) {
  const modeOptions =
    mode === "smooth_field" ? [...MODES, { id: "smooth_field" as PropagationMode, label: "Smooth field" }] : MODES;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-xs text-slate-500">
        Observations
        <SegmentedControl
          options={[
            { id: "calibrations" as ObservationSource, label: "From calibrations" },
            { id: "manual" as ObservationSource, label: "Manual what-if" },
          ]}
          value={source}
          onChange={setSource}
          size="xs"
        />
      </label>

      <label
        className="flex items-center gap-2 text-xs text-slate-500"
        title="Propagation operator — Layered (default): directed parents + remembered dislocations + harmonic completion; Precision: every relation a contract z_i ≈ β z_j at a stated confidence. The legacy Smooth field lives under the pane's Advanced section."
      >
        Operator
        <SegmentedControl options={modeOptions} value={mode} onChange={setMode} size="xs" />
      </label>

      <ConfigChip bundle={config} />
      <PreflightChip preflight={preflight} litCount={litCount} darkCount={darkCount} />

      <div className="ml-auto flex items-center gap-2">
        {summary !== null && (
          <span className={chipClass + " text-slate-400"} data-testid="run-summary">
            {previewField && (
              <span className="mr-1 rounded bg-accent-600/25 px-1 text-[9px] text-accent-300" title="This field is a live preview — nothing was recorded; press Run to commit">
                preview
              </span>
            )}
            <span className="text-amber-400">{summary.observed} observed</span>
            {" · "}
            {summary.extrapolated} extrapolated
            {" · "}
            max |shift| {summary.maxAbs.toFixed(1)} bp
          </span>
        )}
        {error !== null && (
          <span className="max-w-56 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </span>
        )}
        <button
          onClick={() => setLive(!live)}
          aria-pressed={live}
          data-testid="live-toggle"
          title={
            live
              ? "Live ON — every dial / relation edit re-solves as a non-persisting preview (nothing recorded). Click to stop."
              : "Live — re-solve on every dial / relation edit as a non-persisting preview; Run still commits."
          }
          className={[
            "flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
            live
              ? "border-accent-500/60 bg-accent-600/20 text-accent-300"
              : "border-slate-700 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-200",
          ].join(" ")}
        >
          <Zap size={12} strokeWidth={1.75} />
          Live
        </button>
        <button
          disabled={!hasResults}
          onClick={onClear}
          title="Reset the posterior field (observations are kept)"
          className="flex items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Eraser size={12} strokeWidth={1.75} className="opacity-80" />
          Clear field
        </button>
        <button
          disabled={!canRun || busy}
          onClick={onRun}
          title={!canRun ? "Light at least one node first" : "Propagate the observations through the graph (records the run)"}
          className="flex items-center justify-center gap-2 rounded-md bg-accent-600 px-4 py-1.5 text-xs font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />}
          {busy ? "Running…" : "Run"}
        </button>
      </div>
    </div>
  );
}
