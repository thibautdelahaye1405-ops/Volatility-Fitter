// As-of rows — the timestamp picker (Live / Previous Close / historical day →
// moment) rendered INSIDE the Fetch ▾ menu (it used to be the lower half of
// the market pill's dropdown). The market pill is now a passive readout, so
// `asofLabel` is exported for it and for the status bar.
import { useState } from "react";
import type { AsOfState, UseAsOfResult } from "../../state/useAsOf";
import { MenuSection } from "./Menu";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-06-12" -> "Fri 12 Jun" (a day row); today gets a "Today · " prefix. */
export function fmtDay(ymd: string, isToday: boolean): string {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!y || !m || !d) return ymd;
  const wd = WEEKDAYS[new Date(y, m - 1, d).getDay()];
  return `${isToday ? "Today · " : ""}${wd} ${d} ${MONTHS[m - 1]}`;
}

/** "2026-08-28T19:32:00" -> "19:32" (the viewer's local time): a captured
 *  instant's row label. The backend stamps captures as naive UTC, so a
 *  zone-less ISO string is read as UTC. */
export function fmtCaptureTime(iso: string): string {
  const zoned = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const t = new Date(zoned ? iso : `${iso}Z`);
  if (Number.isNaN(t.getTime())) return iso;
  return t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Short label for the current as-of selection (the pill face / status bar). */
export function asofLabel(a: AsOfState): string {
  if (a.mode === "live") return "Live";
  if (a.mode === "prev_close") return "Prev close";
  if (a.day && a.moment) {
    const [, m, d] = a.day.split("-");
    const tag =
      a.moment === "close" ? "Close" : a.moment === "latest" ? "latest" : `−${a.offset}m`;
    return `${m}-${d} ${tag}`;
  }
  if (a.mode === "captured" && a.ts) {
    // An explicit captured replay (no day/moment resolution): its day + time.
    const [, m, d] = a.ts.slice(0, 10).split("-");
    return `${m}-${d} ${fmtCaptureTime(a.ts)}`;
  }
  return "Historical";
}

/** Row styling for the as-of section (highlight the active selection). */
const asofRowClass = (active: boolean): string =>
  [
    "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
    active ? "bg-accent-500/10 text-accent-300" : "text-slate-300 hover:bg-slate-700/40",
  ].join(" ");

/** One within-day moment row. */
function AsofMomentRow({ label, active, onClick, disabled = false, reason, testId }: {
  label: string; active: boolean; onClick: () => void; disabled?: boolean; reason?: string;
  testId?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      title={disabled ? reason : undefined}
      data-testid={testId}
      className={[
        "flex w-full items-center gap-2 px-6 py-1.5 text-left text-xs transition-colors",
        disabled
          ? "cursor-not-allowed text-slate-600"
          : active
            ? "bg-accent-500/10 text-accent-300"
            : "text-slate-300 hover:bg-slate-700/40",
      ].join(" ")}
    >
      <span className="flex-1">{label}</span>
      {disabled && reason && <span className="truncate text-[10px] text-slate-600">{reason}</span>}
      {active && !disabled && <span className="text-accent-400">✓</span>}
    </button>
  );
}

/** The "As of" section: renders nothing until GET /asof has answered.
 *  `onDone` is called BEFORE every selection (the host menu closes itself). */
export function AsOfRows({
  asof: hook,
  onDone,
}: {
  asof: UseAsOfResult;
  onDone?: () => void;
}) {
  const { asof, setLive, setPrevClose, setMoment, setCaptured } = hook;
  // Which day is expanded into its moments (null = derive: the selected day,
  // else the most recent day).
  const [expandedDay, setExpandedDay] = useState<string | null>(null);
  const close = () => onDone?.();

  if (asof === null) return null;
  const openDay =
    expandedDay && asof.days.some((d) => d.date === expandedDay)
      ? expandedDay
      : (asof.day ?? asof.days[0]?.date ?? null);

  return (
    <>
      <MenuSection label="As of" />
      <button
        onClick={() => { close(); void setLive(); }}
        className={asofRowClass(asof.mode === "live")}
      >
        <span className="flex-1 font-medium">Live · Real-time</span>
        {asof.mode === "live" && <span className="text-accent-400">✓</span>}
      </button>

      {/* Previous Close — the provider's prior-session settle, when the
          source supports it (Bloomberg / Massive; Yahoo is live-only). */}
      {asof.supportedModes.includes("prev_close") && (
        <button
          onClick={() => { close(); void setPrevClose(); }}
          className={asofRowClass(asof.mode === "prev_close")}
        >
          <span className="flex-1 font-medium">Previous Close</span>
          {asof.mode === "prev_close" && <span className="text-accent-400">✓</span>}
        </button>
      )}

      {/* Day -> moment. Pick a day to expand its moments. */}
      {asof.days.length > 0 && <MenuSection label="Historical · pick a day" />}
      {asof.days.length === 0 && !asof.supportedModes.includes("prev_close") && (
        <div className="px-3 py-2 text-[10px] leading-snug text-slate-500">
          This source serves <span className="text-slate-300">live data only</span>.
          Switch to Bloomberg or Massive for closes, or capture intraday
          snapshots to replay them here.
        </div>
      )}
      {asof.days.map((d) => {
        const isOpen = d.date === openDay;
        const isSelDay =
          asof.mode !== "live" &&
          (asof.day === d.date || (asof.mode === "captured" && (asof.ts ?? "").startsWith(d.date)));
        const hasIntra = d.hasCaptures || d.intraday;
        const nothing = !d.hasClose && !hasIntra;
        // Every moment is listed; one the active source cannot serve is DIMMED
        // and disabled with the reason, never offered as a live pick and never
        // silently degraded to something else. A FETCH at an arbitrary instant
        // ("n min before close") needs an intraday-capable source; a REPLAY of
        // a capture this source made is offered as exactly that (its time).
        const marks = d.spread === "marks";
        const captures = d.captures ?? [];
        const closeWhy = d.hasClose ? undefined : d.isToday ? "today has no close yet" : "no close for this day on this source";
        const intraWhy = hasIntra ? undefined : d.isToday
          ? "today's latest is Live — pick Live"
          : "this source cannot fetch an intraday moment for this day";
        const latestLabel = captures.length > 0 ? `Latest capture · ${fmtCaptureTime(captures[0])}` : "Latest snapshot";
        const offsetWhy = d.intraday
          ? undefined
          : d.hasCaptures
            ? "this source cannot fetch an arbitrary instant — pick a captured snapshot"
            : intraWhy;
        return (
          <div key={`day-${d.date}`} data-testid={`asof-day-${d.date}`} data-empty={nothing}>
            <button
              onClick={() => setExpandedDay(d.date)}
              className={[
                "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
                isSelDay
                  ? "bg-accent-500/10 text-accent-300"
                  : nothing
                    ? "text-slate-500 hover:bg-slate-700/40"
                    : "text-slate-300 hover:bg-slate-700/40",
              ].join(" ")}
              title={d.reason ?? undefined}
            >
              <span className="flex-1 font-medium">{fmtDay(d.date, d.isToday)}</span>
              {marks && !nothing && (
                <span className="rounded border border-slate-700 px-1 text-[9px] uppercase tracking-wider text-slate-500" title="Historical chains from this source are bid = ask closes (marks), not a two-sided market">
                  marks
                </span>
              )}
              <span className="text-[10px] text-slate-500">{isOpen ? "▾" : "▸"}</span>
            </button>
            {isOpen && (
              <div className="bg-surface-900/60 py-0.5">
                <AsofMomentRow
                  label="Close (official)"
                  active={isSelDay && asof.moment === "close"}
                  disabled={!d.hasClose}
                  reason={closeWhy}
                  onClick={() => { close(); void setMoment(d.date, "close"); }}
                />
                <AsofMomentRow
                  label={latestLabel}
                  active={isSelDay && asof.moment === "latest"}
                  disabled={!hasIntra}
                  reason={intraWhy}
                  onClick={() => { close(); void setMoment(d.date, "latest"); }}
                />
                {asof.closeOffsets.map((n) => (
                  <AsofMomentRow
                    key={`off-${d.date}-${n}`}
                    label={`${n} min before close`}
                    active={isSelDay && asof.moment === "before_close" && asof.offset === n}
                    disabled={!d.intraday}
                    reason={offsetWhy}
                    onClick={() => { close(); void setMoment(d.date, "before_close", n); }}
                  />
                ))}
                {/* The day's other captured instants (the newest is "Latest
                    capture" above): explicit replays of what THIS source captured. */}
                {captures.slice(1, 8).map((iso) => (
                  <AsofMomentRow
                    key={`cap-${iso}`}
                    label={`Captured · ${fmtCaptureTime(iso)}`}
                    active={asof.mode === "captured" && asof.ts === iso}
                    testId="asof-capture-row"
                    onClick={() => { close(); void setCaptured(iso); }}
                  />
                ))}
                {nothing && (
                  <div className="px-6 py-1.5 text-[10px] text-slate-600">{d.reason ?? "No data"}</div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}
