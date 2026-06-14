// Shared maturity-axis helper: plot time either linearly (T) or on a √T axis
// (the natural scale for diffusive vol term structure — total variance is ~linear
// in T, so ATM vol is ~linear in √T). Charts toggle between the two.
import { niceTicks } from "./chartScale";

export type TimeAxisMode = "linear" | "sqrt";

/** Position of a maturity on the chosen axis. */
export function timeAxisValue(t: number, mode: TimeAxisMode): number {
  return mode === "sqrt" ? Math.sqrt(Math.max(0, t)) : t;
}

/** Compact year-fraction label, e.g. 0.0192 -> "7d", 0.25 -> "0.25y". */
export function formatYears(t: number): string {
  if (t <= 0) return "0";
  if (t < 1 / 52) return `${Math.round(t * 365)}d`;
  if (t < 1) return `${t.toFixed(2)}y`;
  return `${t.toFixed(t < 3 ? 2 : 1)}y`;
}

/** Ticks for a maturity axis: nice T values placed at their (possibly √) pos. */
export function timeAxisTicks(
  tLo: number,
  tHi: number,
  mode: TimeAxisMode,
  target = 6,
): { pos: number; label: string }[] {
  return niceTicks(Math.max(0, tLo), tHi, target)
    .filter((t) => t >= 0)
    .map((t) => ({ pos: timeAxisValue(t, mode), label: formatYears(t) }));
}
