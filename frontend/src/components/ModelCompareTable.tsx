// Compact per-family metrics table under the Compare chart (V3.2 item 12):
// one row per compared model — precision (rms / max bp), ATM handles, Lee
// wing slopes, var-swap, the anchoring Pull and the analytic validity chip
// (certified green / breach rose, with the family's minimum value).
// Reference families (eSSVI, compare-only yardsticks) sit last, under a
// divider, with a "reference" pill and muted text so they never read as a
// fourth product model. Anchoring SHADOW rows (lib/anchoring — the displayed
// family refit with the prior / filter removed or added) sit under their
// family's plain row with a sky pill naming the cell; the plain row is
// tagged "prod" for the cell production coincides with. Formatting + chip
// logic live in lib/modelCompare.ts and lib/anchoring.ts (unit-tested);
// this stays presentation only.
import type { CompareResponse } from "../lib/mockData";
import { MODEL_COLORS, REFERENCE_NOTE, isReferenceModel } from "../lib/modelColor";
import { tailMatchedLabel } from "../lib/tailMatch";
import { anchoringPill, compareRowKey, formatPull, isShadowRow } from "../lib/anchoring";
import {
  formatFitMs,
  formatMetric,
  formatTailPair,
  formatVolPct,
  orderCompareRows,
  validityChip,
} from "../lib/modelCompare";

const HEADERS = [
  "Model",
  "RMS bp",
  "Max bp",
  "ATM",
  "Skew",
  "Lee L/R",
  "Tails L/R",
  "Var-swap",
  "Pull",
  "Validity",
  "Params",
  "Fit",
] as const;

/** Hover help for the precision columns — both score the CHOSEN fit target
 *  (mid distance, or the bid-ask / haircut band violation, zero inside). */
const HEADER_TITLES: Partial<Record<(typeof HEADERS)[number], string>> = {
  "RMS bp": "Weighted RMS vol error vs the fit target (mid, or the bid-ask / haircut band — zero inside)",
  "Max bp": "Worst per-quote vol error vs the same fit target",
  "Tails L/R":
    "Structural tail contract per side: exp = straight variance wing (SVI/MCS/eSSVI always; LQD α=0), int/gauss = LQD generalized tails",
  Pull: "Distance to the free fit — no prior, no filter — in ATM vol bp; hover a value for skew and curve RMS",
};

/** Chip classes per validity state (certified / breach / no signal). */
function chipClass(certified: boolean | null): string {
  const base = "inline-block rounded border px-1.5 py-px text-[10px] font-medium";
  if (certified === true) return `${base} border-emerald-500/40 bg-emerald-500/10 text-emerald-300`;
  if (certified === false) return `${base} border-rose-500/40 bg-rose-500/10 text-rose-300`;
  return `${base} border-slate-700 bg-surface-800 text-slate-500`;
}

const PILL_BASE = "rounded border px-1 py-px text-[9px] font-medium tracking-wider";

export default function ModelCompareTable({ data }: { data: CompareResponse }) {
  const axis = data.anchoring ?? null;
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
          {orderCompareRows(data.models).map((m, i, rows) => {
            const chip = validityChip(m);
            const isRef = isReferenceModel(m.model);
            const shadow = isShadowRow(m, axis);
            const pill = anchoringPill(m, axis);
            const pull = formatPull(m);
            // Divider above the FIRST reference row (models above, yardsticks below).
            const firstRef = isRef && (i === 0 || !isReferenceModel(rows[i - 1].model));
            return (
              <tr
                key={compareRowKey(m)}
                data-reference={isRef ? "true" : undefined}
                data-shadow={shadow ? m.anchoring ?? undefined : undefined}
                className={[
                  "border-b border-slate-800/60",
                  isRef || shadow ? "text-slate-400" : "text-slate-300",
                  firstRef ? "border-t border-t-slate-700" : "",
                ].join(" ")}
              >
                <td className="px-2 py-1">
                  <span className={`flex items-center gap-1.5 font-medium ${isRef || shadow ? "text-slate-300" : "text-slate-200"}`}>
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${isRef || shadow ? "opacity-70" : ""}`}
                      style={{ backgroundColor: MODEL_COLORS[m.model] }}
                    />
                    {m.label}
                    {isRef && (
                      <span
                        className={`${PILL_BASE} border-amber-500/30 bg-amber-500/10 uppercase text-amber-400/90`}
                        title={REFERENCE_NOTE[m.model] ?? "Reference family — compare-only yardstick, never a displayed model"}
                      >
                        reference
                      </span>
                    )}
                    {tailMatchedLabel(m) !== null && (
                      <span
                        className={`${PILL_BASE} border-teal-500/30 bg-teal-500/10 text-teal-300/90`}
                        title={`Tails matched to LQD's (${tailMatchedLabel(m)}): this fit carried the stiff tail-matching rows — equality to solver tolerance, the belly pays for it`}
                      >
                        {tailMatchedLabel(m)}
                      </span>
                    )}
                    {pill !== null && (
                      <span className={`${PILL_BASE} border-sky-500/30 bg-sky-500/10 text-sky-300`} title={pill.title}>
                        {pill.label}
                      </span>
                    )}
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
                    <td className="px-2 py-1 font-mono">{formatTailPair(m)}</td>
                    <td className="px-2 py-1 font-mono">{formatVolPct(m.varSwapVol)}</td>
                    <td className="px-2 py-1 font-mono" title={pull.title}>{pull.text}</td>
                  </>
                ) : (
                  <td colSpan={8} className="truncate px-2 py-1 text-rose-400/90" title={m.error ?? undefined}>
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
