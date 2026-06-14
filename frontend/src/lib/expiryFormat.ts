// Expiry-label formatting (ROADMAP Phase 10 follow-up).
//
// One global format choice is applied wherever an expiry is shown (dropdowns,
// ladders, chips, tables, chart legends). Calendar formats render the date;
// tenor formats render the year-fraction t. The "compact" calendar format is
// SMART-DAY: the day is shown only when the expiry is NOT a standard monthly
// (3rd-Friday) listing, so monthlies read cleanly (Dec26) while weeklies keep
// their day (18Dec26).
export type ExpiryFormat = "dmy" | "compact" | "years" | "months" | "monthsdays";

/** Selector options, in cycle order; the label is a placeholder showing the
 *  shape of the rendered value (the menu/toggle text). */
export const EXPIRY_FORMATS: { id: ExpiryFormat; label: string }[] = [
  { id: "dmy", label: "dd-mmm-yy" },
  { id: "compact", label: "(dd)mmmyy" },
  { id: "years", label: "x.xxY" },
  { id: "months", label: "xx.xM" },
  { id: "monthsdays", label: "yyM zD" },
];

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Parse "YYYY-MM-DD" into UTC components (no timezone drift). */
function parseIso(iso: string): { y: number; m: number; d: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return null;
  return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
}

/** Standard monthly listing = the 3rd Friday of its month (also covers the
 *  quarterly third-Fridays); the day falls in 15..21 and is a Friday. */
function isThirdFriday(y: number, m: number, d: number): boolean {
  if (d < 15 || d > 21) return false;
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay() === 5;
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/** Format one expiry given its ISO date and year-fraction t to maturity. */
export function formatExpiry(iso: string, t: number, fmt: ExpiryFormat): string {
  if (fmt === "years") return `${t.toFixed(2)}Y`;
  if (fmt === "months") return `${(t * 12).toFixed(1)}M`;
  if (fmt === "monthsdays") {
    const totalM = t * 12;
    const m = Math.max(0, Math.floor(totalM));
    const days = Math.round((totalM - m) * 30.4375);
    // Smart: under a month, show days only (e.g. 12D); else "15M 0D".
    return m === 0 ? `${days}D` : `${m}M ${days}D`;
  }
  // Calendar formats need the date; fall back to the ISO string if unparseable.
  const p = parseIso(iso);
  if (p === null) return iso;
  const mon = MONTHS[p.m - 1] ?? "";
  const yy = pad2(p.y % 100);
  if (fmt === "dmy") return `${pad2(p.d)}-${mon}-${yy}`;
  // compact, smart-day: omit the day on standard monthly (3rd-Friday) listings.
  return isThirdFriday(p.y, p.m, p.d) ? `${mon}${yy}` : `${pad2(p.d)}${mon}${yy}`;
}
