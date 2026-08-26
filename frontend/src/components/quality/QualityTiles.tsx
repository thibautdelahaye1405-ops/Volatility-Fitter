// Quality lens headline tiles (UI SHELL v2, S3): the eight universe-level
// counters (publish-ready / fitted / stale / no-fit / arb flags / RMS / LV
// surfaces) read straight from the report summary. Extracted from
// QualityViewer so the lens can sit them beside the active node's
// certificate card (QualityNodeCard) on the top row.
import { fmtBp } from "../../lib/qualityFormat";
import type { QualitySummary } from "../../state/useQuality";

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-800 bg-surface-800 px-3 py-2">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={`font-mono text-lg leading-tight ${tone ?? "text-slate-200"}`}>
        {value}
      </span>
    </div>
  );
}

export interface QualityTilesProps {
  summary: QualitySummary;
  /** Publish RMS budget (bp) — the worst-RMS tile turns amber above it. */
  rmsBudgetBp: number;
}

export default function QualityTiles({ summary: s, rmsBudgetBp }: QualityTilesProps) {
  // 4 columns (two rows) beside the node card; 8 across only on wide screens.
  return (
    <div className="grid grid-cols-4 gap-2 2xl:grid-cols-8">
      <Tile
        label="Publish ready"
        value={`${s.readyNodes}/${s.litNodes}`}
        tone={s.readyNodes === s.litNodes && s.litNodes > 0 ? "text-emerald-400" : "text-slate-200"}
      />
      <Tile label="Fitted" value={`${s.fitted}`} />
      <Tile label="Stale" value={`${s.stale}`} tone={s.stale > 0 ? "text-amber-300" : undefined} />
      <Tile label="No fit" value={`${s.noFit}`} tone={s.noFit > 0 ? "text-slate-400" : undefined} />
      <Tile label="Arb flags" value={`${s.arbFlags}`} tone={s.arbFlags > 0 ? "text-rose-400" : undefined} />
      <Tile label="Median RMS" value={`${fmtBp(s.medianRmsBp)} bp`} />
      <Tile
        label="Worst RMS"
        value={`${fmtBp(s.worstRmsBp)} bp`}
        tone={s.worstRmsBp > rmsBudgetBp ? "text-amber-300" : undefined}
      />
      <Tile
        label="LV surfaces"
        value={s.lvTickers > 0 ? `${s.lvArbFree}/${s.lvTickers} arb-free` : "—"}
        tone={s.lvTickers > 0 && s.lvArbFree < s.lvTickers ? "text-rose-400" : undefined}
      />
    </div>
  );
}
