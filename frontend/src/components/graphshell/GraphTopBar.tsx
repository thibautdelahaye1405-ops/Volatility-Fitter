// Graph shell top bar (P5b U0; live preflight U5): the workflow spine's
// Configure→Run controls.
//
// LEFT: observation source (calibrations vs manual what-if — unified by the
// U3 mode-aware what-if), propagation operator (Smooth field | Messages;
// hybrid stays config-only), the config chip (structural stub until the U6
// lifecycle) and the LIVE preflight chip (dry-run findings; Run gates only
// on blockers). RIGHT: post-run summary badges, last error, Clear field, and
// RUN — the workspace's single primary action.
import { Eraser } from "lucide-react";
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
  /** The live dry-run report (U5) — drives the chip; blockers gate Run. */
  preflight: UsePreflightResult;
  /** The U6 config-lifecycle chip bundle. */
  config: ConfigChipBundle;
  summary: RunSummary | null;
  /** Last run failure (production or sandbox), or null. */
  error: string | null;
  canRun: boolean;
  busy: boolean;
  onRun: () => void;
  hasResults: boolean;
  onClear: () => void;
}

const chipClass =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px]";

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
  error,
  canRun,
  busy,
  onRun,
  hasResults,
  onClear,
}: GraphTopBarProps) {
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

      {/* Propagation operator — mode-aware for BOTH sources since the U3
          unification (the what-if rides the production solve). */}
      <label
        className="flex items-center gap-2 text-xs text-slate-500"
        title="Propagation operator — applies to calibrations AND the what-if; seeded from Options ▸ Graph"
      >
        Propagation
        <SegmentedControl
          options={[
            { id: "smooth_field" as PropagationMode, label: "Smooth field" },
            { id: "precision_messages" as PropagationMode, label: "Messages" },
          ]}
          value={mode}
          onChange={setMode}
          size="xs"
        />
      </label>

      {/* Live config lifecycle (U6): draft/active, diff, Activate/Revert. */}
      <ConfigChip bundle={config} />

      {/* Live preflight (U5): dry-run findings; blockers gate Run. */}
      <PreflightChip preflight={preflight} litCount={litCount} darkCount={darkCount} />

      <div className="ml-auto flex items-center gap-2">
        {summary !== null && (
          <span className={chipClass + " text-slate-400"}>
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
          title={
            !canRun
              ? "Light at least one node first"
              : "Propagate the observations through the graph"
          }
          className="flex items-center justify-center gap-2 rounded-md bg-accent-600 px-4 py-1.5 text-xs font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
          )}
          {busy ? "Running…" : "Run"}
        </button>
      </div>
    </div>
  );
}
