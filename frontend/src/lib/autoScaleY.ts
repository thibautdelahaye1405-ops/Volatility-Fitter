// Smile-chart y-axis auto-scale — the policy behind the "Y center" / "Y fit"
// toolbar chips, plus their persisted preference (localStorage, like the
// Calibrate scope: a UI preference, not a backend setting).
//
// The chart's y BASE domain already auto-fits the data visible in the x-window
// (SmileChart's scale memo); the useZoom y FRACTIONS ride on top of it. The
// policy therefore acts purely on those fractions after an x-view change:
//   fit    -> identity {0, 1}: the base auto-fit shows through, so every curve
//             and quote inside the x-window is exactly in frame;
//   center -> keep the user's y zoom (same fraction span) but recenter the
//             window on 0.5, the middle of the auto-fitted base;
//   none   -> leave the fractions alone (legacy free-zoom behavior).
// Manual y-only interactions (alt+wheel) bypass the policy by design.

export interface YWindow {
  yLo: number;
  yHi: number;
}

/** The two toolbar toggles. `fit` wins when both are on (it implies centering). */
export interface AutoScaleToggles {
  center: boolean;
  fit: boolean;
}

export const AUTOSCALE_STORAGE_KEY = "volfit.smileAutoScale";

/** Requested default: an always-fitted y-axis (both chips lit). */
export const DEFAULT_AUTOSCALE: AutoScaleToggles = { center: true, fit: true };

/** The y-fraction window to apply after an x-view change, or null for a no-op
 *  (policy off, or the current window already satisfies it — callers can then
 *  skip the state write entirely). */
export function autoScaleYWindow(current: YWindow, toggles: AutoScaleToggles): YWindow | null {
  if (toggles.fit) {
    return current.yLo === 0 && current.yHi === 1 ? null : { yLo: 0, yHi: 1 };
  }
  if (toggles.center) {
    const span = Math.abs(current.yHi - current.yLo);
    const yLo = 0.5 - span / 2;
    const yHi = 0.5 + span / 2;
    return yLo === current.yLo && yHi === current.yHi ? null : { yLo, yHi };
  }
  return null;
}

export function isAutoScaleToggles(v: unknown): v is AutoScaleToggles {
  return (
    typeof v === "object" &&
    v !== null &&
    typeof (v as AutoScaleToggles).center === "boolean" &&
    typeof (v as AutoScaleToggles).fit === "boolean"
  );
}

/** Stored toggles, or the default (both ON) on nothing / garbage / no storage. */
export function readSmileAutoScale(
  storage: Pick<Storage, "getItem"> | null = safeStorage(),
): AutoScaleToggles {
  try {
    const raw = storage?.getItem(AUTOSCALE_STORAGE_KEY);
    if (raw == null) return DEFAULT_AUTOSCALE;
    const v: unknown = JSON.parse(raw);
    return isAutoScaleToggles(v) ? { center: v.center, fit: v.fit } : DEFAULT_AUTOSCALE;
  } catch {
    return DEFAULT_AUTOSCALE;
  }
}

export function writeSmileAutoScale(
  toggles: AutoScaleToggles,
  storage: Pick<Storage, "setItem"> | null = safeStorage(),
): void {
  try {
    storage?.setItem(
      AUTOSCALE_STORAGE_KEY,
      JSON.stringify({ center: toggles.center, fit: toggles.fit }),
    );
  } catch {
    /* storage unavailable (privacy mode): the choice just does not persist */
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
