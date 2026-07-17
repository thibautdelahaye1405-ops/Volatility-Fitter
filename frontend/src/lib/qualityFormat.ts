// Pure helpers of the Quality workspace (extracted for testability).
import type { QualityNode } from "../state/useQuality";

export type SortMode = "exceptions" | "rms" | "node";

/** Format a bp figure: 1 decimal normally, 2 sig figs when sub-0.1 (a
 *  near-exact fit must not display as a fake hard zero). NaN metrics from a
 *  diverged fit arrive as null over JSON — render "—" instead of crashing. */
export function fmtBp(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value >= 0.1 || value === 0 ? value.toFixed(1) : value.toPrecision(2);
}

/** Order rows for the table: exceptions first (not-ready, worst RMS on top),
 *  by RMS, or in natural ticker/expiry order. */
export function sortNodes(nodes: QualityNode[], mode: SortMode): QualityNode[] {
  const rows = [...nodes];
  if (mode === "node") return rows; // backend order: ticker, ascending expiry
  if (mode === "rms") return rows.sort((a, b) => b.rmsBp - a.rmsBp);
  return rows.sort((a, b) => {
    if (a.ready !== b.ready) return a.ready ? 1 : -1;
    return b.rmsBp - a.rmsBp;
  });
}
