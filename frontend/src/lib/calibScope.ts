// Calibrate scope — the THREE first-class choices of the TopBar Calibrate
// split control: "Parametric + LV" (POST /calibrate, the combined verb — LV
// still gated server-side by the Options toggle), "Parametric only"
// (POST /calibrate/parametric, the fast loop; LV surfaces go/stay stale) and
// "Local-Vol only" (POST /calibrate/lv, no parametric refit). The primary face
// runs the LAST CHOSEN scope and names it, so one click always does what the
// label says; the choice sticks across reloads (localStorage, like the expiry
// format and view settings — a UI preference, not a backend setting).

export type CalibScope = "both" | "parametric" | "lv";

export const CALIB_SCOPES: readonly CalibScope[] = ["both", "parametric", "lv"] as const;

/** Short face label after "Calibrate ·". */
export const SCOPE_SHORT: Record<CalibScope, string> = {
  both: "Param + LV",
  parametric: "Param only",
  lv: "LV only",
};

/** Menu row label. */
export const SCOPE_LABEL: Record<CalibScope, string> = {
  both: "Parametric + LV",
  parametric: "Parametric only",
  lv: "Local-Vol only",
};

export const SCOPE_STORAGE_KEY = "volfit.calibScope";
export const DEFAULT_SCOPE: CalibScope = "both";

export function isCalibScope(v: unknown): v is CalibScope {
  return v === "both" || v === "parametric" || v === "lv";
}

/** Stored scope, or the default when nothing / garbage / no storage. */
export function readCalibScope(storage: Pick<Storage, "getItem"> | null = safeStorage()): CalibScope {
  try {
    const v = storage?.getItem(SCOPE_STORAGE_KEY);
    return isCalibScope(v) ? v : DEFAULT_SCOPE;
  } catch {
    return DEFAULT_SCOPE;
  }
}

export function writeCalibScope(
  scope: CalibScope,
  storage: Pick<Storage, "setItem"> | null = safeStorage(),
): void {
  try {
    storage?.setItem(SCOPE_STORAGE_KEY, scope);
  } catch {
    /* storage unavailable (privacy mode): the choice just does not persist */
  }
}

/** The stale badge the face shows for a scope: parametric stale nodes for the
 *  parametric scopes, stale LV surfaces for LV-only (0 = no badge). */
export function scopeBadge(scope: CalibScope, staleNodes: number, lvStaleTickers: number): number {
  return scope === "lv" ? lvStaleTickers : staleNodes;
}

/** Menu-row detail text per scope (what the click will do), mirroring the
 *  server semantics: the combined verb runs parametric only when LV is gated
 *  off in Options; parametric-only leaves the LV surfaces stale. */
export function scopeDetail(
  scope: CalibScope,
  staleNodes: number,
  lvStaleTickers: number,
  lvEnabled: boolean,
): string {
  if (scope === "both") {
    if (!lvEnabled) return "LV gated off in Options — parametric only";
    return staleNodes > 0 ? `${staleNodes} stale node(s), then LV surfaces` : "all lit nodes, then LV surfaces";
  }
  if (scope === "parametric") {
    return staleNodes > 0 ? `${staleNodes} stale node(s) — LV left as is` : "all lit nodes — LV left as is";
  }
  return lvStaleTickers > 0
    ? `${lvStaleTickers} stale LV surface(s) — no parametric refit`
    : "LV surfaces only — no parametric refit";
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
