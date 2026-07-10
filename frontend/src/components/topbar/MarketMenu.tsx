// Market-context pill: ONE control for "what data am I looking at" — the
// active source (Yahoo / Bloomberg / Massive / Synthetic, with a status
// light) and the as-of timestamp (Live / Previous Close / historical day →
// moment). Face reads "● Massive · Live" and turns amber whenever the view
// is historical, exactly like the old standalone As-of pill.
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { SourceStatus, UseDataSourcesResult } from "../../state/useDataSources";
import type { AsOfState, UseAsOfResult } from "../../state/useAsOf";
import { MenuDivider, MenuPanel, MenuSection } from "./Menu";

/** Tailwind dot colour for each status level. */
const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-rose-500",
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-06-12" -> "Fri 12 Jun" (a day row); today gets a "Today · " prefix. */
function fmtDay(ymd: string, isToday: boolean): string {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!y || !m || !d) return ymd;
  const wd = WEEKDAYS[new Date(y, m - 1, d).getDay()];
  return `${isToday ? "Today · " : ""}${wd} ${d} ${MONTHS[m - 1]}`;
}

/** Short label for the current as-of selection (the pill face). */
function asofLabel(a: AsOfState): string {
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

export default function MarketMenu({
  dataSources,
  asofHook,
}: {
  dataSources: UseDataSourcesResult;
  asofHook: UseAsOfResult;
}) {
  const { sources, active, switching, dataAge, switchSource } = dataSources;
  const { asof, busy: asofBusy, setLive, setPrevClose, setMoment } = asofHook;
  const [open, setOpen] = useState(false);
  // Which day is expanded into its moments (null = derive: the selected day,
  // else the most recent day).
  const [expandedDay, setExpandedDay] = useState<string | null>(null);

  const activeSource = sources.find((s) => s.id === active);
  const historical = asof !== null && asof.mode !== "live";
  // Data-age staleness of the LIVE view (backend data_age; null off-live).
  // Red-stale live data means "live" is really the previous session — say so.
  const staleLive = !historical && dataAge !== null && dataAge.level !== "fresh";
  const redStale = staleLive && dataAge!.level === "red";
  const openDay =
    expandedDay && asof?.days.some((d) => d.date === expandedDay)
      ? expandedDay
      : (asof?.day ?? asof?.days[0]?.date ?? null);
  const close = () => setOpen(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title={
          staleLive
            ? `Live view is pricing quotes ${dataAge!.label} old (worst: ${dataAge!.worstTicker})`
            : "Market data source & as-of timestamp"
        }
        className={[
          "flex items-center gap-2 rounded-md border px-2.5 py-1 hover:border-slate-600",
          redStale
            ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
            : historical || staleLive
              ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
              : "border-slate-700 bg-surface-800 text-slate-200",
        ].join(" ")}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            STATUS_DOT[activeSource?.status ?? "green"]
          } ${switching ? "animate-pulse" : ""}`}
        />
        <span className="font-medium">{activeSource?.label ?? (active || "Source")}</span>
        {asof && (
          <span className={`text-slate-400 ${asofBusy ? "animate-pulse" : ""}`}>
            · {redStale ? "prev session" : asofLabel(asof)}
          </span>
        )}
        {staleLive && (
          <span className={redStale ? "text-rose-300" : "text-amber-300"}>
            · quotes {dataAge!.label}
          </span>
        )}
        <ChevronDown size={12} className="text-slate-500" />
      </button>

      <MenuPanel open={open} onClose={close} align="right" width="w-72">
        {/* ── Data source ─────────────────────────────────────────────── */}
        <MenuSection label="Data source" />
        {sources.length === 0 && (
          <div className="px-3 py-1.5 text-[10px] text-slate-600">Probing sources…</div>
        )}
        {sources.map((s) => {
          // Red sources are shown (so you know they exist + why) but can't be
          // selected — switching to an unavailable feed would fail the fetch.
          const unavailable = s.status === "red";
          return (
            <button
              key={s.id}
              disabled={unavailable}
              onClick={() => { close(); void switchSource(s.id); }}
              title={unavailable ? `${s.label}: ${s.detail}` : undefined}
              className={[
                "flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors",
                unavailable
                  ? "cursor-not-allowed text-slate-500"
                  : s.id === active
                    ? "bg-accent-500/10 text-accent-300"
                    : "text-slate-300 hover:bg-slate-700/40",
              ].join(" ")}
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} />
              <span className="flex-1 font-medium">{s.label}</span>
              <span className="truncate text-[10px] text-slate-500">{s.detail}</span>
            </button>
          );
        })}

        {/* ── As of ───────────────────────────────────────────────────── */}
        {asof && (
          <>
            <MenuDivider />
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
        )}
      </MenuPanel>
    </div>
  );
}
