// The top-bar Calibrate scope as a live subscription: any surface that must
// mirror the split control's current choice (the Spot move card's per-ticker
// Recalibrate names the same scope) reads it here and re-renders when the top
// bar changes it (writeCalibScope dispatches CALIB_SCOPE_EVENT) or when
// another tab writes the stored preference (the storage event).
import { useSyncExternalStore } from "react";
import { CALIB_SCOPE_EVENT, DEFAULT_SCOPE, readCalibScope } from "../lib/calibScope";
import type { CalibScope } from "../lib/calibScope";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(CALIB_SCOPE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CALIB_SCOPE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** The current Calibrate scope (Param + LV / Param only / LV only), live. */
export function useCalibScope(): CalibScope {
  return useSyncExternalStore(subscribe, () => readCalibScope(), () => DEFAULT_SCOPE);
}
