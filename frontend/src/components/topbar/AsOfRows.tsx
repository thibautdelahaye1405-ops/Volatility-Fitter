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
  return "Historical";
}

/** Row styling for the as-of section (highlight the active selection). */
const asofRowClass = (active: boolean): string =>
  [
    "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
    active ? "bg-accent-500/10 text-accent-300" : "text-slate-300 hover:bg-slate-700/40",
  ].join(" ");

/** One within-day moment row. */
function AsofMomentRow({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "flex w-full items-center gap-2 py-1 pl-6 pr-3 text-left text-[11px] transition-colors",
        active ? "text-accent-300" : "text-slate-400 hover:bg-slate-700/40 hover:text-slate-200",
      ].join(" ")}
    >
      <span className="flex-1">{label}</span>
      {active && <span className="text-accent-400">✓</span>}
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
  const { asof, setLive, setPrevClose, setMoment } = hook;
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
        const isSelDay = asof.mode !== "live" && asof.day === d.date;
        const hasIntra = d.hasCaptures || d.intraday;
        return (
          <div key={`day-${d.date}`}>
            <button
              onClick={() => setExpandedDay(d.date)}
              className={[
                "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
                isSelDay
                  ? "bg-accent-500/10 text-accent-300"
                  : "text-slate-300 hover:bg-slate-700/40",
              ].join(" ")}
            >
              <span className="flex-1 font-medium">{fmtDay(d.date, d.isToday)}</span>
              <span className="text-[10px] text-slate-500">{isOpen ? "▾" : "▸"}</span>
            </button>
            {isOpen && (
              <div className="bg-surface-900/60 py-0.5">
                {d.hasClose && (
                  <AsofMomentRow
                    label="Close (official)"
                    active={isSelDay && asof.moment === "close"}
                    onClick={() => { close(); void setMoment(d.date, "close"); }}
                  />
                )}
                {hasIntra && (
                  <AsofMomentRow
                    label="Latest snapshot"
                    active={isSelDay && asof.moment === "latest"}
                    onClick={() => { close(); void setMoment(d.date, "latest"); }}
                  />
                )}
                {hasIntra &&
                  asof.closeOffsets.map((n) => (
                    <AsofMomentRow
                      key={`off-${d.date}-${n}`}
                      label={`${n} min before close`}
                      active={
                        isSelDay && asof.moment === "before_close" && asof.offset === n
                      }
                      onClick={() => { close(); void setMoment(d.date, "before_close", n); }}
                    />
                  ))}
                {!d.hasClose && !hasIntra && (
                  <div className="px-6 py-1.5 text-[10px] text-slate-600">No data</div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}
