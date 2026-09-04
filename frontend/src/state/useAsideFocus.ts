// The right-hand column's focus as a live subscription (lib/asideSizes): the
// Parametric and Local Vol asides both read which card is expanded here, so
// the column keeps its shape across lenses, editor groups and reloads
// (writeAsideFocus dispatches ASIDE_FOCUS_EVENT; the storage event follows a
// write from another tab).
import { useCallback, useSyncExternalStore } from "react";
import {
  ASIDE_FOCUS_EVENT,
  asideSizeOf,
  effectiveAsideFocus,
  readAsideFocus,
  toggleAsideFocus,
  writeAsideFocus,
} from "../lib/asideSizes";
import type { AsideFocus, AsidePanelId, AsideSize } from "../lib/asideSizes";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(ASIDE_FOCUS_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(ASIDE_FOCUS_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export interface AsideFocusApi {
  /** The expanded card (null: all three at the standard size). */
  focus: AsideFocus;
  /** Size of one card under the current focus. */
  sizeOf: (panel: AsidePanelId) => AsideSize;
  /** Expand `panel` (the others compress), or fold it back when expanded. */
  toggle: (panel: AsidePanelId) => void;
}

/** The column's focus, restricted to the cards actually rendered (`present`):
 *  a focus on a card that is gated off — the var-swap card without its
 *  Options toggle — reads as no focus, so the others stay standard. */
export function useAsideFocus(present: readonly AsidePanelId[]): AsideFocusApi {
  const stored = useSyncExternalStore(subscribe, () => readAsideFocus(), () => null);
  const focus = effectiveAsideFocus(stored, present);
  const sizeOf = useCallback((panel: AsidePanelId) => asideSizeOf(focus, panel), [focus]);
  const toggle = useCallback((panel: AsidePanelId) => writeAsideFocus(toggleAsideFocus(focus, panel)), [focus]);
  return { focus, sizeOf, toggle };
}
