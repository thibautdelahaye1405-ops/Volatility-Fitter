// Top navigation bar: product branding, workspace tabs, and the Data Source
// selector (Yahoo / Bloomberg / Massive / Synthetic) with a status light each
// (green = real-time, amber = delayed, red = unavailable). Switching the source
// refetches the universe + smile on the new feed.
import { useCallback, useState } from "react";
import type { TabDef, TabId } from "../App";
import { useSmileSession } from "../state/smileSession";
import { useDataSources } from "../state/useDataSources";
import type { SourceStatus } from "../state/useDataSources";
import { useAsOf } from "../state/useAsOf";
import type { AsOfState } from "../state/useAsOf";
import { useWorkflow } from "../state/useWorkflow";
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

/** "2026-06-13T10:05:00" -> "06-13 10:05" (captured intraday label). */
function fmtTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Local date part "2026-06-13" of an ISO timestamp (for the date selector). */
function tsDate(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(0, 10);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Local time part "10:05" of an ISO timestamp (for the time selector). */
function fmtTime(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** True for Mon-Fri (markets are closed at the weekend, so weekend captures —
 *  e.g. "yesterday" on a Sunday — are never offered as as-of dates). */
function isWeekday(ymd: string): boolean {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!y || !m || !d) return true;
  const day = new Date(y, m - 1, d).getDay();
  return day !== 0 && day !== 6;
}

/** Row styling for the as-of dropdown (highlight the active selection). */
const asofRowClass = (active: boolean): string =>
  [
    "flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors",
    active ? "bg-accent-500/10 text-accent-300" : "text-slate-300 hover:bg-slate-700/40",
  ].join(" ");

/** Short label for the current as-of selection (the button face). */
function asofLabel(a: AsOfState): string {
  if (a.mode === "prev_close") return "Prev close";
  if (a.mode === "eod") return `${a.on} close`;
  if (a.mode === "captured" && a.ts) return fmtTs(a.ts);
  return "Live";
}

export default function TopBar({ tabs, activeTab, onSelect }: TopBarProps) {
  const { source, loading, refreshUniverse, reload, refreshViews } = useSmileSession();
  const live = source === "live";
  const workflow = useWorkflow(live, refreshViews);

  // After a source switch, refetch the universe (keeps the selection valid)
  // and reload the current smile so every workspace reflects the new feed.
  const onSwitched = useCallback(() => {
    void refreshUniverse().then(reload).catch(reload);
  }, [refreshUniverse, reload]);

  const { sources, active, switching, switchSource } = useDataSources(live, onSwitched);
  const { asof, busy: asofBusy, setAsOf } = useAsOf(live, active, onSwitched);
  const [open, setOpen] = useState(false);
  const [asofOpen, setAsofOpen] = useState(false);
  // Which captured *date* is expanded in the as-of picker (null = derive a default).
  const [capturedDate, setCapturedDate] = useState<string | null>(null);

  const activeSource = sources.find((s) => s.id === active);

  // Captured intraday snapshots split into date -> times, so a prior day's
  // snapshot is reachable (item 4). asof.captured is newest-first.
  const capturedDates = asof
    ? Array.from(new Set(asof.captured.map(tsDate))).filter(isWeekday)
    : [];
  const selectedCapDate =
    capturedDate && capturedDates.includes(capturedDate)
      ? capturedDate
      : asof?.mode === "captured" && asof.ts
        ? tsDate(asof.ts)
        : (capturedDates[0] ?? null);
  const capturedTimes = asof
    ? asof.captured.filter((ts) => tsDate(ts) === selectedCapDate)
    : [];

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
          return (
            <button
              key={tab.id}
              onClick={() => onSelect(tab.id)}
              aria-current={isActive ? "page" : undefined}
              className={[
                "relative px-4 text-sm font-medium transition-colors",
                isActive
                  ? "text-accent-400"
                  : "text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {tab.label}
              {isActive && (
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
                  <div className="absolute right-0 z-20 mt-1 max-h-80 w-56 overflow-auto rounded-lg border border-slate-700 bg-surface-800 shadow-xl shadow-black/40">
                    <button
                      onClick={() => { setAsofOpen(false); void setAsOf({ mode: "live" }); }}
                      className={asofRowClass(asof.mode === "live")}
                    >
                      <span className="flex-1 font-medium">Live · Real-time</span>
                    </button>
                    {asof.prevCloseAvailable && (
                      <button
                        onClick={() => { setAsofOpen(false); void setAsOf({ mode: "prev_close" }); }}
                        className={asofRowClass(asof.mode === "prev_close")}
                      >
                        <span className="flex-1 font-medium">Previous Close</span>
                      </button>
                    )}
                    {asof.captured.length > 0 && (
                      <>
                        <div className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
                          Captured · date
                        </div>
                        {/* Date selector (reach a prior day's snapshots). */}
                        <div className="flex flex-wrap gap-1 px-3 pb-1.5">
                          {capturedDates.map((d) => (
                            <button
                              key={`capd-${d}`}
                              onClick={() => setCapturedDate(d)}
                              className={[
                                "rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                                d === selectedCapDate
                                  ? "border-accent-600/60 bg-accent-600/15 text-accent-400"
                                  : "border-slate-700 text-slate-400 hover:text-slate-200",
                              ].join(" ")}
                            >
                              {d}
                            </button>
                          ))}
                        </div>
                        <div className="px-3 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
                          Time
                        </div>
                        {/* Times within the selected captured date. */}
                        {capturedTimes.map((ts) => (
                          <button
                            key={`cap-${ts}`}
                            onClick={() => { setAsofOpen(false); void setAsOf({ mode: "captured", ts }); }}
                            className={asofRowClass(asof.mode === "captured" && asof.ts === ts)}
                          >
                            <span className="flex-1 font-mono">{fmtTime(ts)}</span>
                            <span className="text-[10px] text-slate-500">captured</span>
                          </button>
                        ))}
                      </>
                    )}
                    {asof.historyDates.length > 0 && (
                      <div className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
                        End of day
                      </div>
                    )}
                    {asof.historyDates.map((d) => (
                      <button
                        key={`eod-${d}`}
                        onClick={() => { setAsofOpen(false); void setAsOf({ mode: "eod", on: d }); }}
                        className={asofRowClass(asof.mode === "eod" && asof.on === d)}
                      >
                        <span className="flex-1 font-mono">{d}</span>
                        <span className="text-[10px] text-slate-500">close</span>
                      </button>
                    ))}
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
