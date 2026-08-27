// Model chips of the Compare view (UI SHELL v2 wave 2): the prevailing
// calibrated family (read from the smile's modelInfo) is shown at once and
// cannot be removed; the other families are chips that FIT LAZILY when
// clicked (the compare endpoint is called with exactly the selected models,
// server-side cached), and toggle off without a refit. A chip in flight
// shows a spinner; a failed fit shows its error in the tooltip.
import { MODEL_COLORS, MODEL_LABELS, MODEL_ORDER } from "../../lib/modelColor";
import type { CompareModelId, CompareResponse } from "../../lib/mockData";

export interface CompareChipsProps {
  prevailing: CompareModelId;
  selected: ReadonlySet<CompareModelId>;
  onToggle: (id: CompareModelId) => void;
  data: CompareResponse | null;
  loading: boolean;
}

/** Map a modelInfo id / label onto a comparable family (default LQD). */
export function prevailingModelId(id: string | undefined, label: string | undefined): CompareModelId {
  const key = `${id ?? ""} ${label ?? ""}`.toLowerCase();
  // "essvi" contains "svi": sniff the compare-only comparator FIRST so it is
  // never misrouted to SVI-JW (it cannot prevail today — defensive only).
  if (key.includes("essvi")) return "essvi";
  if (key.includes("svi")) return "svi";
  if (key.includes("sigmoid") || key.includes("mcs")) return "sigmoid";
  return "lqd";
}

export default function CompareChips({ prevailing, selected, onToggle, data, loading }: CompareChipsProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
      <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-600">models</span>
      {MODEL_ORDER.map((id) => {
        const on = selected.has(id);
        const isPrev = id === prevailing;
        const fit = data?.models.find((m) => m.model === id);
        const pending = on && loading && fit === undefined;
        const failed = on && fit !== undefined && !fit.ok;
        return (
          <button
            key={id}
            aria-pressed={on}
            disabled={isPrev}
            onClick={() => onToggle(id)}
            title={
              isPrev
                ? `${MODEL_LABELS[id]} — the prevailing calibrated model (always shown)`
                : failed
                  ? `${MODEL_LABELS[id]} — fit failed: ${fit?.error ?? "unknown"}`
                  : on
                    ? `${MODEL_LABELS[id]} — click to hide`
                    : `${MODEL_LABELS[id]} — click to fit on the same quotes`
            }
            className={[
              "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
              on
                ? "border-slate-600 bg-surface-800 text-slate-100"
                : "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-200",
              isPrev ? "cursor-default" : "",
            ].join(" ")}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${on ? "" : "opacity-40"}`}
              style={{ backgroundColor: MODEL_COLORS[id] }}
            />
            {MODEL_LABELS[id]}
            {isPrev && <span className="text-[9px] uppercase text-slate-500">calibrated</span>}
            {pending && (
              <span className="h-2.5 w-2.5 animate-spin rounded-full border border-slate-500 border-t-transparent" />
            )}
            {failed && <span className="text-rose-400">!</span>}
          </button>
        );
      })}
    </div>
  );
}
