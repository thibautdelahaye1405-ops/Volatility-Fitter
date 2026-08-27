// Per-node EFFECTIVE as-of cell of the Nodes pane (backend follow-on
// 2026-08-27: UniverseExpiry.effectiveAsOf / dataSource / asOfExact).
//
// The chain serving a node is not always the moment the as-of selector asked
// for — a live-only source ignores a close request, a feed stamps a
// prev-close chain at fetch time — and the backend flags that with
// asOfExact=false. The pane shows the stamp's HH:MM (UTC, the backend's
// UTC-naive convention, like the quote table's tick time) in amber when
// inexact, with a group-level "≠ as-of" pill; the tooltip carries the full
// stamp · source · a client-side age. No fetch, no clock subscription: the
// age is computed at render from Date.now().
import type { UniverseExpiry } from "../../state/useSmile";

/** The three as-of fields of a universe rung (or a graph node). */
export type NodeAsOf = Pick<UniverseExpiry, "effectiveAsOf" | "dataSource" | "asOfExact">;

/** "HH:MM" (UTC) of a backend stamp; "—" when the node has no chain yet. */
export function asOfClock(iso: string | null | undefined): string {
  return iso && iso.length >= 16 ? iso.slice(11, 16) : "—";
}

/** Short age of a UTC-naive stamp, mirroring the backend's format_age
 *  ("4m" / "13.5h" / "3.2d"); "" when unknown or unparseable. */
export function asOfAge(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return "";
  const stamped = Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`);
  if (!Number.isFinite(stamped)) return "";
  const minutes = Math.max(0, (nowMs - stamped) / 60_000);
  if (minutes < 90) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  return hours < 48 ? `${hours.toFixed(1)}h` : `${(hours / 24).toFixed(1)}d`;
}

/** Tooltip: full stamp · source · age, plus the mismatch note when inexact. */
export function asOfTitle(row: NodeAsOf, nowMs: number): string {
  if (!row.effectiveAsOf) return "no chain loaded yet — press Fetch";
  const parts = [`${row.effectiveAsOf} UTC`, row.dataSource ?? "", asOfAge(row.effectiveAsOf, nowMs)];
  const head = `effective as-of · ${parts.filter(Boolean).join(" · ")}`;
  return row.asOfExact === false
    ? `${head}\n≠ as-of — the source served another moment than the one selected`
    : head;
}

/** The compact mono column between tenor and RMS: HH:MM of the serving chain. */
export function NodeAsOfCell({ row }: { row: NodeAsOf }) {
  const inexact = row.asOfExact === false;
  return (
    <span
      className={`w-9 shrink-0 text-right font-mono text-[10px] ${inexact ? "text-amber-400" : "text-slate-600"}`}
      title={asOfTitle(row, Date.now())}
    >
      {asOfClock(row.effectiveAsOf)}
    </span>
  );
}

/** Ticker-group pill: at least one expiry is served off the requested as-of. */
export function AsOfMismatchPill() {
  return (
    <span
      className="ml-1 shrink-0 rounded border border-amber-500/40 px-1 font-mono text-[9px] font-normal text-amber-400"
      title="Some expiries are served from another moment than the selected as-of"
    >
      ≠ as-of
    </span>
  );
}
