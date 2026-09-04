// Right-hand column sizing (the Parametric and Local Vol asides). The three
// stacked cards — Spot move · Variance swap · Fit diagnostics — must all stay
// on screen without scrolling the column, so each card has three sizes,
//   S  compact   one row: the title and a one-line readout (click to expand)
//   M  standard  the working controls and headline readouts (the default)
//   L  expanded  everything the card knows — secondary readouts, extra rows
// under one rule, "one card gets the room": expanding a card makes it L and
// compresses the other two to S; folding it back returns all three to M.
// The focus is a UI preference shared by both lenses and kept across reloads
// (localStorage + a window event, like the Calibrate scope) — never a backend
// setting. Pure logic here; the live subscription is state/useAsideFocus.

export type AsidePanelId = "spot" | "varswap" | "diag";
export type AsideSize = "S" | "M" | "L";
/** The expanded card, or null when all three sit at the standard size. */
export type AsideFocus = AsidePanelId | null;

export const ASIDE_PANELS: readonly AsidePanelId[] = ["spot", "varswap", "diag"] as const;

export const ASIDE_FOCUS_STORAGE_KEY = "volfit.asideFocus";
/** Window event dispatched after a write, so both lenses' asides follow. */
export const ASIDE_FOCUS_EVENT = "volfit:asideFocus";

export function isAsidePanelId(v: unknown): v is AsidePanelId {
  return v === "spot" || v === "varswap" || v === "diag";
}

/** Size of `panel` under `focus`: the focused card is expanded, the others
 *  compact; with no focus every card is standard. */
export function asideSizeOf(focus: AsideFocus, panel: AsidePanelId): AsideSize {
  if (focus === null) return "M";
  return focus === panel ? "L" : "S";
}

/** The focus after a click on `panel`'s expander: expand it (compressing the
 *  others), or fold the expanded card back so all three return to standard. */
export function toggleAsideFocus(focus: AsideFocus, panel: AsidePanelId): AsideFocus {
  return focus === panel ? null : panel;
}

/** A focus on a card that is not rendered (the var-swap card is Options-gated)
 *  must not leave the column with two compact cards and no expanded one. */
export function effectiveAsideFocus(focus: AsideFocus, present: readonly AsidePanelId[]): AsideFocus {
  return focus !== null && present.includes(focus) ? focus : null;
}

/** Whether a card may give up height (its body scrolls) when the column is
 *  short: the expanded card always, and the standard-size diagnostics card
 *  (the last one) so the two cards above it never get pushed off screen. */
export function asideCardShrinks(size: AsideSize, panel: AsidePanelId): boolean {
  return size === "L" || (size === "M" && panel === "diag");
}

/** Stored focus, or null when nothing / garbage / no storage. */
export function readAsideFocus(storage: Pick<Storage, "getItem"> | null = safeStorage()): AsideFocus {
  try {
    const v = storage?.getItem(ASIDE_FOCUS_STORAGE_KEY);
    return isAsidePanelId(v) ? v : null;
  } catch {
    return null;
  }
}

export function writeAsideFocus(
  focus: AsideFocus,
  storage: Pick<Storage, "setItem" | "removeItem"> | null = safeStorage(),
): void {
  try {
    if (focus === null) storage?.removeItem(ASIDE_FOCUS_STORAGE_KEY);
    else storage?.setItem(ASIDE_FOCUS_STORAGE_KEY, focus);
  } catch {
    /* storage unavailable (privacy mode): the choice just does not persist */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(ASIDE_FOCUS_EVENT));
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
