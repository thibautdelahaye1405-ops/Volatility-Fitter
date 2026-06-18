// Bottom status bar: what the engine is actually doing, plus an idle summary.
//
// Replaces the progress hints that used to crowd the TopBar buttons. While the
// engine works it narrates the fine-grained activity reported by the backend
// (volfit.api.activity) — "Fetching SPY quotes from Yahoo", "De-americanizing …",
// "Calibrating SPY 2026-07-17 (LQD)", "Fitting QQQ term structure", "Computing
// densities", "Calibrating SPY local-vol surface" — with a gauge (determinate
// for the calibration job's node count, indeterminate otherwise). When idle it
// shows "Ready" plus an at-a-glance summary: lit / stale nodes, the active data
// source + status light, the as-of selection and the next auto-fetch countdown.
import { useWorkflowContext } from "../state/workflowContext";
import type { SourceStatus } from "../state/useDataSources";
import type { AsOfState } from "../state/useAsOf";
import type { WorkflowAction } from "../state/useWorkflow";

/** Tailwind dot colour per source-status level (mirrors the TopBar selector). */
const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-rose-500",
};

/** Per-stage accent colour for the activity dot + bar. */
const STAGE_COLOR: Record<string, string> = {
  fetch: "bg-sky-400",
  calibrate: "bg-accent-400",
  localvol: "bg-violet-400",
  term: "bg-teal-400",
  density: "bg-amber-400",
  surface: "bg-fuchsia-400",
};

/** "75" -> "1:15" (seconds -> m:ss for the auto-fetch countdown). */
function fmtCountdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Short label for the current as-of selection (matches the TopBar face). */
function asofLabel(a: AsOfState): string {
  if (a.mode === "live") return "Live";
  if (a.mode === "prev_close") return "Prev close";
  if (a.day && a.moment) {
    const [, m, d] = a.day.split("-");
    const tag = a.moment === "close" ? "Close" : a.moment === "latest" ? "latest" : `−${a.offset}m`;
    return `${m}-${d} ${tag}`;
  }
  return "Historical";
}

/** Optimistic label for a just-clicked action, shown until the poll catches up. */
const PENDING_LABEL: Record<WorkflowAction, string> = {
  spots: "Fetching spots…",
  options: "Fetching option quotes…",
  calibrate: "Calibrating…",
  savePriors: "Saving priors…",
  fetchPriors: "Fetching priors…",
};

/** Indeterminate "working" gauge (no known done/total). */
function IndeterminateBar({ color }: { color: string }) {
  return (
    <span className="relative inline-block h-1 w-28 overflow-hidden rounded-full bg-surface-700">
      <span className={`volfit-indeterminate-fill ${color}`} />
    </span>
  );
}

/** Determinate progress gauge (done / total). */
function ProgressBar({ done, total, color }: { done: number; total: number; color: string }) {
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
  return (
    <span className="inline-block h-1 w-28 overflow-hidden rounded-full bg-surface-700">
      <span
        className={`block h-full rounded-full ${color} transition-all`}
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

/** One muted summary chip in the idle bar's right cluster. */
function Chip({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-slate-600">{label}</span>
      <span className={tone ?? "text-slate-300"}>{value}</span>
    </span>
  );
}

export default function StatusBar() {
  const { live, workflow, dataSources, asof } = useWorkflowContext();
  const { calib, sched, pending } = workflow;
  const act = calib?.activity;
  const running = calib?.running ?? false;

  // ---- Decide the primary line + gauge ---------------------------------
  // Priority: the backend's fine-grained activity (most specific) -> the job
  // running flag -> an optimistic label for a just-clicked button -> idle.
  let message = "";
  let detail = "";
  let stage = "calibrate";
  let gauge: "progress" | "indeterminate" | null = null;

  if (act?.active) {
    message = act.message;
    detail = act.detail;
    stage = act.stage || "calibrate";
    // A running calibration job has a real node count; show it determinate.
    // Otherwise fall back to the activity's own done/total, else indeterminate.
    if (running && (calib?.total ?? 0) > 0) gauge = "progress";
    else if (act.total > 0) gauge = "progress";
    else gauge = "indeterminate";
  } else if (running) {
    message = `Calibrating ${calib?.phase || "…"}`;
    stage = "calibrate";
    gauge = (calib?.total ?? 0) > 0 ? "progress" : "indeterminate";
  } else if (pending) {
    message = PENDING_LABEL[pending];
    stage = pending === "calibrate" ? "calibrate" : "fetch";
    gauge = "indeterminate";
  }

  const busy = message !== "";
  const color = STAGE_COLOR[stage] ?? "bg-accent-400";

  // Node-count gauge values: prefer the job (done/total nodes), else the
  // activity's own done/total.
  const gaugeDone = running ? (calib?.done ?? 0) : (act?.done ?? 0);
  const gaugeTotal = running ? (calib?.total ?? 0) : (act?.total ?? 0);

  // ---- Idle summary ----------------------------------------------------
  const lit = calib?.litNodes ?? 0;
  const stale = calib?.staleNodes ?? 0;
  const activeSource = dataSources.sources.find((s) => s.id === dataSources.active);
  const autoOptions = sched?.optionsFetchMode === "auto";
  const lastError = calib?.error ?? "";

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-slate-800 bg-surface-900 px-4 text-xs">
      {/* Left: live activity narration, or Ready */}
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {!live ? (
          <span className="flex items-center gap-2 text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Mock data — backend offline
          </span>
        ) : busy ? (
          <>
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color} animate-pulse`} />
            <span className="shrink-0 font-medium text-slate-200">{message}</span>
            {detail && (
              <span className="truncate font-mono text-[11px] text-slate-500">· {detail}</span>
            )}
            {gauge === "progress" && (
              <span className="flex shrink-0 items-center gap-2">
                <ProgressBar done={gaugeDone} total={gaugeTotal} color={color} />
                {gaugeTotal > 0 && (
                  <span className="font-mono text-[10px] text-slate-500">
                    {gaugeDone}/{gaugeTotal}
                  </span>
                )}
              </span>
            )}
            {gauge === "indeterminate" && <IndeterminateBar color={color} />}
          </>
        ) : (
          <>
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
            <span className="font-medium text-slate-300">Ready</span>
            {lastError && (
              <span className="truncate text-[11px] text-rose-400/80" title={lastError}>
                · last error: {lastError}
              </span>
            )}
          </>
        )}
      </div>

      {/* Right: at-a-glance summary (live only) */}
      {live && (
        <div className="flex shrink-0 items-center gap-4">
          <Chip
            label="Nodes"
            value={stale > 0 ? `${lit} lit · ${stale} stale` : `${lit} lit`}
            tone={stale > 0 ? "text-amber-300" : "text-slate-300"}
          />
          {autoOptions && (
            <Chip label="Next fetch" value={fmtCountdown(sched?.secondsToNextOptions ?? 0)} />
          )}
          {asof.asof && (
            <Chip
              label="As of"
              value={asofLabel(asof.asof)}
              tone={asof.asof.mode === "live" ? "text-slate-300" : "text-amber-300"}
            />
          )}
          {activeSource && (
            <span className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-slate-600">Source</span>
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[activeSource.status]}`} />
              <span className="text-slate-300">{activeSource.label}</span>
            </span>
          )}
        </div>
      )}
    </footer>
  );
}
