// Compact per-family metrics table under the Compare chart (V3.2 item 12):
// one row per compared model — precision (rms / max bp), ATM handles, Lee
// wing slopes, var-swap and the analytic validity chip (certified green /
// breach rose, with the family's minimum value). Formatting + chip logic
// live in lib/modelCompare.ts (unit-tested); this stays presentation only.
import type { CompareResponse } from "../lib/mockData";
import { MODEL_COLORS } from "../lib/modelColor";
import {
  formatFitMs,
  formatMetric,
  formatVolPct,
  validityChip,
} from "../lib/modelCompare";

const HEADERS = [
  "Model",
  "RMS bp",
  "Max bp",
  "ATM",
  "Skew",
  "Lee L/R",
  "Var-swap",
  "Validity",
  "Params",
  "Fit",
] as const;

/** Hover help for the precision columns — both score the CHOSEN fit target
 *  (mid distance, or the bid-ask / haircut band violation, zero inside). */
const HEADER_TITLES: Partial<Record<(typeof HEADERS)[number], string>> = {
  "RMS bp": "Weighted RMS vol error vs the fit target (mid, or the bid-ask / haircut band — zero inside)",
  "Max bp": "Worst per-quote vol error vs the same fit target",
};

/** Chip classes per validity state (certified / breach / no signal). */
function chipClass(certified: boolean | null): string {
  const base = "inline-block rounded border px-1.5 py-px text-[10px] font-medium";
  if (certified === true) return `${base} border-emerald-500/40 bg-emerald-500/10 text-emerald-300`;
  if (certified === false) return `${base} border-rose-500/40 bg-rose-500/10 text-rose-300`;
  return `${base} border-slate-700 bg-surface-800 text-slate-500`;
}

export default function ModelCompareTable({ data }: { data: CompareResponse }) {
  return (
    <div className="shrink-0 overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-slate-800 text-left text-[10px] uppercase tracking-wider text-slate-500">
            {HEADERS.map((h) => (
              <th key={h} className="px-2 py-1 font-medium" title={HEADER_TITLES[h]}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.models.map((m) => {
            const chip = validityChip(m);
            return (
              <tr key={m.model} className="border-b border-slate-800/60 text-slate-300">
                <td className="px-2 py-1">
                  <span className="flex items-center gap-1.5 font-medium text-slate-200">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: MODEL_COLORS[m.model] }}
                    />
                    {m.label}
                  </span>
                </td>
                {m.ok ? (
                  <>
                    <td className="px-2 py-1 font-mono">{formatMetric(m.rmsBp)}</td>
                    <td className="px-2 py-1 font-mono">{formatMetric(m.maxIvBp)}</td>
                    <td className="px-2 py-1 font-mono">{formatVolPct(m.atmVol)}</td>
                    <td className="px-2 py-1 font-mono">{formatMetric(m.skew, 3)}</td>
                    <td className="px-2 py-1 font-mono">
                      {formatMetric(m.leeLeft, 2)} / {formatMetric(m.leeRight, 2)}
                    </td>
                    <td className="px-2 py-1 font-mono">{formatVolPct(m.varSwapVol)}</td>
                  </>
                ) : (
                  <td colSpan={6} className="truncate px-2 py-1 text-rose-400/90" title={m.error ?? undefined}>
                    {m.error ?? "fit failed"}
                  </td>
                )}
                <td className="px-2 py-1">
                  <span className={chipClass(chip.certified)} title={chip.title}>
                    {chip.label}
                  </span>
                </td>
                <td className="px-2 py-1 font-mono">{m.nParams ?? "—"}</td>
                <td
                  className="px-2 py-1 font-mono text-slate-400"
                  title={m.reused ? "Read from the committed calibration (no refit)" : "Ad-hoc comparison fit"}
                >
                  {formatFitMs(m)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
