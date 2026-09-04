// Model chips of the Compare view (UI SHELL v2 wave 2): the prevailing
// calibrated family (read from the smile's modelInfo) is shown at once and
// cannot be removed; the other families are chips that FIT LAZILY when
// clicked (the compare endpoint is called with exactly the selected models,
// server-side cached), and toggle off without a refit. A chip in flight
// shows a spinner; a failed fit shows its error in the tooltip.
//
// REFERENCE families (eSSVI — compare-only yardsticks, never a displayed
// model) are NOT in the default chip set: a "+ reference" affordance at the
// end of the strip reveals their chips (dashed, tagged "ref"); hiding the
// group again also deselects them, so a hidden reference is never fitted.
//
// TAIL MATCHING (lib/tailMatch): a third group of three toggles — = Var-swap,
// = Lee wings, = Edge — refits SVI-JW and MCS with their tails pulled onto
// LQD's. LQD is then pinned in the comparison (its chip is disabled while a
// toggle is lit); a toggle the backend could not apply shows an amber "!"
// with the reason in its tooltip, a clamped Lee target a "cap" tag.
import { useState } from "react";
import {
  CHIP_MODELS,
  MODEL_COLORS,
  MODEL_LABELS,
  REFERENCE_NOTE,
  REFERENCE_ORDER,
  isReferenceModel,
} from "../../lib/modelColor";
import { TAIL_FLAG_LABELS, TAIL_FLAG_ORDER, tailChipState } from "../../lib/tailMatch";
import type { CompareModelId, CompareResponse, CompareTailFlag, CompareTailInfo } from "../../lib/mockData";

const NO_TAILS: ReadonlySet<CompareTailFlag> = new Set();

export interface CompareChipsProps {
  prevailing: CompareModelId;
  selected: ReadonlySet<CompareModelId>;
  onToggle: (id: CompareModelId) => void;
  data: CompareResponse | null;
  loading: boolean;
  /** Tail-matching toggles (lit set + toggler); the group shows only with a
   *  toggler. `tailInfo` is the last response's report (chip warnings). */
  tails?: ReadonlySet<CompareTailFlag>;
  onToggleTail?: (flag: CompareTailFlag) => void;
  tailInfo?: CompareTailInfo | null;
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

/** Hover text of one model chip, by state. */
function chipTitle(
  id: CompareModelId, isPrev: boolean, pinnedRef: boolean, on: boolean, failed: boolean, error: string | null,
): string {
  const name = MODEL_LABELS[id];
  if (isPrev) return `${name} — the prevailing calibrated model (always shown)`;
  if (pinnedRef) return `${name} — the tail-matching reference (shown while a match toggle is lit)`;
  if (failed) return `${name} — fit failed: ${error ?? "unknown"}`;
  const ref = isReferenceModel(id) ? `\n${REFERENCE_NOTE[id] ?? "Reference family"}` : "";
  return on ? `${name} — click to hide${ref}` : `${name} — click to fit on the same quotes${ref}`;
}

const CHIP_BASE = "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium transition-colors";
const CHIP_OFF = "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-200";

export default function CompareChips({
  prevailing, selected, onToggle, data, loading, tails = NO_TAILS, onToggleTail, tailInfo,
}: CompareChipsProps) {
  // Reference chips show while revealed OR selected (a selection remembered
  // by the tab survives a remount with the group collapsed).
  const [revealed, setRevealed] = useState(false);
  const selectedRefs = REFERENCE_ORDER.filter((id) => selected.has(id));
  const showRefs = revealed || selectedRefs.length > 0;
  const toggleReveal = () => {
    if (showRefs) selectedRefs.forEach((id) => onToggle(id)); // hiding = dropping them from the comparison
    setRevealed(!showRefs);
  };
  const tailsOn = onToggleTail !== undefined && tails.size > 0;

  const chip = (id: CompareModelId) => {
    const on = selected.has(id);
    const isPrev = id === prevailing;
    const isRef = isReferenceModel(id);
    const pinnedRef = id === "lqd" && tailsOn && !isPrev; // the tail-matching reference
    const fit = data?.models.find((m) => m.model === id);
    const pending = on && loading && fit === undefined;
    const failed = on && fit !== undefined && !fit.ok;
    return (
      <button
        key={id}
        aria-pressed={on}
        disabled={isPrev || pinnedRef}
        onClick={() => onToggle(id)}
        title={chipTitle(id, isPrev, pinnedRef, on, failed, fit?.error ?? null)}
        className={[
          CHIP_BASE,
          isRef ? "border-dashed" : "",
          on ? "border-slate-600 bg-surface-800 text-slate-100" : CHIP_OFF,
          isPrev || pinnedRef ? "cursor-default" : "",
        ].join(" ")}
      >
        <span
          className={`inline-block h-2 w-2 rounded-full ${on ? "" : "opacity-40"}`}
          style={{ backgroundColor: MODEL_COLORS[id] }}
        />
        {MODEL_LABELS[id]}
        {isPrev && <span className="text-[9px] uppercase text-slate-500">calibrated</span>}
        {pinnedRef && <span className="text-[9px] uppercase text-slate-500">target</span>}
        {isRef && <span className="text-[9px] uppercase text-amber-500/80">ref</span>}
        {pending && (
          <span className="h-2.5 w-2.5 animate-spin rounded-full border border-slate-500 border-t-transparent" />
        )}
        {failed && <span className="text-rose-400">!</span>}
      </button>
    );
  };

  const tailChip = (flag: CompareTailFlag) => {
    const s = tailChipState(flag, tails, tailInfo);
    return (
      <button
        key={flag}
        aria-pressed={s.on}
        onClick={() => onToggleTail?.(flag)}
        title={s.title}
        className={[
          CHIP_BASE,
          s.on ? "border-teal-500/50 bg-teal-500/10 text-teal-100" : CHIP_OFF,
        ].join(" ")}
      >
        {TAIL_FLAG_LABELS[flag]}
        {s.dropped && <span className="text-amber-400">!</span>}
        {s.clamped && <span className="text-[9px] uppercase text-amber-500/80">cap</span>}
      </button>
    );
  };

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
      <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-600">models</span>
      {CHIP_MODELS.map(chip)}
      {REFERENCE_ORDER.length > 0 && (
        <>
          <span className="mx-0.5 h-3 w-px bg-slate-800" aria-hidden />
          {showRefs && REFERENCE_ORDER.map(chip)}
          <button
            aria-expanded={showRefs}
            aria-label={showRefs ? "Hide reference families" : "Show reference families"}
            onClick={toggleReveal}
            title={
              showRefs
                ? "Hide the reference families (drops them from the comparison)"
                : "Reveal the reference families — compare-only yardsticks (eSSVI), never a displayed model"
            }
            className="rounded px-1.5 py-0.5 text-[10px] text-slate-500 transition-colors hover:text-slate-200"
          >
            {showRefs ? "− reference" : "+ reference"}
          </button>
        </>
      )}
      {onToggleTail !== undefined && (
        <>
          <span className="mx-0.5 h-3 w-px bg-slate-800" aria-hidden />
          <span
            className="text-[9px] font-semibold uppercase tracking-wider text-slate-600"
            title="Tail matching: refit SVI-JW and MCS so their tails follow LQD's — the comparison then isolates belly expressiveness"
          >
            match LQD tails
          </span>
          {TAIL_FLAG_ORDER.map(tailChip)}
        </>
      )}
    </div>
  );
}
