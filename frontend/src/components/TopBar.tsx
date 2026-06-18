// Top navigation bar: product branding, workspace tabs, and the Data Source
// selector (Yahoo / Bloomberg / Massive / Synthetic) with a status light each
// (green = real-time, amber = delayed, red = unavailable). Switching the source
// refetches the universe + smile on the new feed.
import { useEffect, useState } from "react";
import type { TabDef, TabId } from "../App";
import { useSmileSession } from "../state/smileSession";
import type { SourceStatus } from "../state/useDataSources";
import type { AsOfState } from "../state/useAsOf";
import { useWorkflowContext } from "../state/workflowContext";
import WorkflowControls from "./WorkflowControls";

interface TopBarProps {
  tabs: TabDef[];
  activeTab: TabId;
  onSelect: (tab: TabId) => void;
}

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

/** Row styling for the as-of dropdown (highlight the active selection). */
const asofRowClass = (active: boolean): string =>
  [
    "flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors",
    active ? "bg-accent-500/10 text-accent-300" : "text-slate-300 hover:bg-slate-700/40",
  ].join(" ");

/** One within-day moment row in the as-of dropdown. */
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

/** Short label for the current as-of selection (the button face). */
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

export default function TopBar({ tabs, activeTab, onSelect }: TopBarProps) {
  const { loading } = useSmileSession();
  // Shared workflow state (single poll loop feeds both the TopBar and the
  // bottom StatusBar). The detailed progress narration lives in the StatusBar.
  const { live, workflow, dataSources, asof: asofHook } = useWorkflowContext();
  // Local-Vol master switch (polled on the scheduler status). When off, the
  // Local Vol tab is disabled; bounce away if it's the active tab.
  const localVolEnabled = workflow.sched?.localVolEnabled ?? true;
  useEffect(() => {
    if (!localVolEnabled && activeTab === "localvol") onSelect("parametric");
  }, [localVolEnabled, activeTab, onSelect]);

  const { sources, active, switching, switchSource } = dataSources;
  const { asof, busy: asofBusy, setLive, setPrevClose, setMoment } = asofHook;
  const [open, setOpen] = useState(false);
  const [asofOpen, setAsofOpen] = useState(false);
  // Which day is expanded into its moments (null = derive: the selected day, else
  // the most recent day).
  const [expandedDay, setExpandedDay] = useState<string | null>(null);

  const activeSource = sources.find((s) => s.id === active);

  const openDay =
    expandedDay && asof?.days.some((d) => d.date === expandedDay)
      ? expandedDay
      : (asof?.day ?? asof?.days[0]?.date ?? null);

  return (
    <header className="flex h-14 shrink-0 items-center gap-8 border-b border-slate-800 bg-surface-900 px-6">
      {/* Brand mark */}
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent-600/20 font-mono text-sm font-bold text-accent-400">
          σ
        </span>
        <h1 className="text-sm font-semibold tracking-wide text-slate-100">
          Vol Fitter
        </h1>
      </div>

      {/* Workspace tabs */}
      <nav className="flex h-full items-stretch gap-1" aria-label="Workspaces">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;
          const disabled = tab.id === "localvol" && !localVolEnabled;
          return (
            <button
              key={tab.id}
              onClick={() => { if (!disabled) onSelect(tab.id); }}
              disabled={disabled}
              aria-current={isActive ? "page" : undefined}
              title={disabled ? "Local-Vol calibration is disabled (enable it in Options)" : undefined}
              className={[
                "relative px-4 text-sm font-medium transition-colors",
                disabled
                  ? "cursor-not-allowed text-slate-600"
                  : isActive
                    ? "text-accent-400"
                    : "text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {tab.label}
              {isActive && !disabled && (
                <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent-500" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Right side: Data Source selector (live) or connectivity badge */}
      <div className="ml-auto flex items-center gap-3 text-xs">
        {loading ? (
          <span className="flex items-center gap-2 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500 animate-pulse" />
            Connecting…
          </span>
        ) : !live ? (
          <span className="flex items-center gap-2 text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Mock data
          </span>
        ) : (
          <>
          {/* Calibration / data-fetch workflow controls */}
          <WorkflowControls workflow={workflow} />

          <div className="relative">
            <button
              onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-2 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-slate-200 hover:border-slate-600"
              title="Switch market-data source"
            >
              <span className="text-[10px] uppercase tracking-wider text-slate-500">
                Source
              </span>
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  STATUS_DOT[activeSource?.status ?? "green"]
                } ${switching ? "animate-pulse" : ""}`}
              />
              <span className="font-medium">{activeSource?.label ?? active}</span>
              <span className="text-slate-500">▾</span>
            </button>

            {open && (
              <>
                {/* Click-away backdrop */}
                <button
                  className="fixed inset-0 z-10 cursor-default"
                  aria-hidden
                  onClick={() => setOpen(false)}
                />
                <div className="absolute right-0 z-20 mt-1 w-60 overflow-hidden rounded-lg border border-slate-700 bg-surface-800 shadow-xl shadow-black/40">
                  {sources.map((s) => {
                    // Red sources are shown (so you know they exist + why) but
                    // can't be selected — switching to an unavailable feed would
                    // fail the universe fetch.
                    const unavailable = s.status === "red";
                    return (
                      <button
                        key={s.id}
                        disabled={unavailable}
                        onClick={() => {
                          setOpen(false);
                          void switchSource(s.id);
                        }}
                        title={unavailable ? `${s.label}: ${s.detail}` : undefined}
                        className={[
                          "flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors",
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
                </div>
              </>
            )}
          </div>

          {/* As-of (timestamp) selector: Live / Previous Close / past close /
              captured intraday. Amber face when the view is historical. */}
          {asof && (
            <div className="relative">
              <button
                onClick={() => setAsofOpen((v) => !v)}
                title="Choose the as-of timestamp"
                className={[
                  "flex items-center gap-2 rounded-md border px-2.5 py-1 hover:border-slate-600",
                  asof.mode === "live"
                    ? "border-slate-700 bg-surface-800 text-slate-200"
                    : "border-amber-500/40 bg-amber-500/10 text-amber-300",
                ].join(" ")}
              >
                <span className="text-[10px] uppercase tracking-wider text-slate-500">
                  As of
                </span>
                <span className={`font-medium ${asofBusy ? "animate-pulse" : ""}`}>
                  {asofLabel(asof)}
                </span>
                <span className="text-slate-500">▾</span>
              </button>

              {asofOpen && (
                <>
                  <button
                    className="fixed inset-0 z-10 cursor-default"
                    aria-hidden
                    onClick={() => setAsofOpen(false)}
                  />
                  <div className="absolute right-0 z-20 mt-1 max-h-96 w-64 overflow-auto rounded-lg border border-slate-700 bg-surface-800 shadow-xl shadow-black/40">
                    {/* Live (real-time) */}
                    <button
                      onClick={() => { setAsofOpen(false); void setLive(); }}
                      className={asofRowClass(asof.mode === "live")}
                    >
                      <span className="flex-1 font-medium">Live · Real-time</span>
                    </button>

                    {/* Previous Close — the provider's prior-session settle, when
                        the source supports it (Bloomberg / Massive; Yahoo is
                        live-only). */}
                    {asof.supportedModes.includes("prev_close") && (
                      <button
                        onClick={() => { setAsofOpen(false); void setPrevClose(); }}
                        className={asofRowClass(asof.mode === "prev_close")}
                      >
                        <span className="flex-1 font-medium">Previous Close</span>
                      </button>
                    )}

                    {/* Day -> moment. Pick a day to expand its moments. */}
                    {asof.days.length > 0 && (
                      <div className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
                        Historical · pick a day
                      </div>
                    )}
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
                                  onClick={() => { setAsofOpen(false); void setMoment(d.date, "close"); }}
                                />
                              )}
                              {hasIntra && (
                                <AsofMomentRow
                                  label="Latest snapshot"
                                  active={isSelDay && asof.moment === "latest"}
                                  onClick={() => { setAsofOpen(false); void setMoment(d.date, "latest"); }}
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
                                    onClick={() => { setAsofOpen(false); void setMoment(d.date, "before_close", n); }}
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
                  </div>
                </>
              )}
            </div>
          )}
          </>
        )}
      </div>
    </header>
  );
}
