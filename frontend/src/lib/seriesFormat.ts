// Display formatting shared by the Series lens pieces (SERIES ARC S4):
// instants, durations, numbers and the tone of a job status. PURE — no
// React, vitest-friendly.
import type { SeriesStatus } from "./seriesTypes";

/** "2026-09-08 15:45" in the browser's zone from an ISO instant; the raw
 *  string trimmed to minutes when it does not parse. */
export function fmtInstant(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.replace("T", " ").slice(0, 16);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** "14 s" · "2 min 05 s" · "1 h 12 min". */
export function fmtSeconds(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(Math.round(s - m * 60)).padStart(2, "0")} s`;
  const h = Math.floor(m / 60);
  return `${h} h ${String(m - h * 60).padStart(2, "0")} min`;
}

/** Fixed-point number, "—" for null / non-finite. */
export function fmtNum(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

/** Badge tone of a job status (lib/ui badgeClass). */
export function statusTone(status: SeriesStatus | null | undefined): "accent" | "amber" | "emerald" | "rose" {
  switch (status) {
    case "done":
      return "emerald";
    case "failed":
      return "rose";
    case "paused":
    case "cancelled":
    case "draft":
      return "amber";
    default:
      return "accent";
  }
}
