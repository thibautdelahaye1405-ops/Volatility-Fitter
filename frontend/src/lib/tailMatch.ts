// Tail matching in the Compare view (pure helpers, no React): the three
// toggles that refit SVI-JW and MCS with their tails pulled onto LQD's —
// var-swap level, Lee (asymptotic) slopes, the quoted-edge value + slope —
// so the comparison isolates belly expressiveness. The backend reports what
// applied (CompareTailInfo); the chips read their state from it.
import type { CompareModelFit, CompareTailFlag, CompareTailInfo } from "./mockData";

/** Wire order of the toggles (the order the backend applies and reports). */
export const TAIL_FLAG_ORDER: readonly CompareTailFlag[] = ["varswap", "lee", "edge"];

export const TAIL_FLAG_LABELS: Record<CompareTailFlag, string> = {
  varswap: "= Var-swap",
  lee: "= Lee wings",
  edge: "= Edge",
};

/** Short names for the table pill ("= var-swap · Lee · edge"). */
export const TAIL_FLAG_SHORT: Record<CompareTailFlag, string> = {
  varswap: "var-swap",
  lee: "Lee",
  edge: "edge",
};

export const TAIL_FLAG_TITLES: Record<CompareTailFlag, string> = {
  varswap:
    "Match var-swap — refit SVI-JW and MCS with their fair var-swap pinned to LQD's closed-form level. " +
    "Fits to the same quotes differ in var-swap only through the extrapolated region (1/K²-weighted), so this pins the tail LEVEL.",
  lee:
    "Match Lee wings — pin both asymptotic total-variance slopes to LQD's (the wing DIRECTION). " +
    "Needs LQD's exponential tails (α = 0); clamped just under the Lee cap.",
  edge:
    "Match edge — pin the value AND slope of total variance at the last quoted strike on each side to LQD's: " +
    "a C¹ match of where extrapolation starts, the closest to what a trader sees.",
};

export interface TailChipState {
  on: boolean;
  /** Lit but the backend could not apply it (the note says why). */
  dropped: boolean;
  /** Lee target pulled under the family cap. */
  clamped: boolean;
  title: string;
}

/** The chip's state from the selection and the last report. */
export function tailChipState(
  flag: CompareTailFlag,
  tails: ReadonlySet<CompareTailFlag>,
  info: CompareTailInfo | null | undefined,
): TailChipState {
  const on = tails.has(flag);
  const reported = info != null && info.requested.includes(flag);
  const dropped = on && reported && !info.applied.includes(flag);
  const clamped = on && flag === "lee" && reported && info.leeClamped === true;
  let title = TAIL_FLAG_TITLES[flag];
  if (dropped) title += `\nNot applied${info?.note ? `: ${info.note}` : ""}`;
  else if (clamped && info?.note) title += `\n${info.note}`;
  return { on, dropped, clamped, title };
}

/** The table pill text of a constrained row, or null when the fit was plain. */
export function tailMatchedLabel(row: Pick<CompareModelFit, "tailMatched">): string | null {
  const flags = (row.tailMatched ?? []).filter((f): f is CompareTailFlag => f in TAIL_FLAG_SHORT);
  if (flags.length === 0) return null;
  return `= ${TAIL_FLAG_ORDER.filter((f) => flags.includes(f)).map((f) => TAIL_FLAG_SHORT[f]).join(" · ")}`;
}
