// Bottom status bar v2 (UI SHELL v2, S2): what the engine is doing, plus the
// idle summary and the workbench context.
//
//   LEFT   engine narration (fetch / calibrate / LV / term / density …) with a
//          gauge — determinate for a calibration job's node count — or
//          "Ready" · last error; then the active LENS · NODE.
//   RIGHT  workspace file name (+ unsaved) · nodes lit/stale · next auto-fetch ·
//          as-of · source light · quote age (when not fresh) · LAST ACTION with
//          its timestamp · wall clock.
// Offline (mock) keeps the lens/node + clock so the bar never goes blank.
import { useEffect, useState } from "react";
import { useWorkflowContext } from "../../state/workflowContext";
import { ACTIVITIES, useWorkbench } from "../../state/workbench";
import { useExpiryFormat } from "../../state/expiryFormat";
import { useOptionalWorkspaceFile } from "../../state/workspaceFile";
import { useSmileSession } from "../../state/smileSession";
import { formatExpiry } from "../../lib/expiryFormat";
import type { SourceStatus } from "../../state/useDataSources";
import type { AsOfState } from "../../state/useAsOf";
import type { WorkflowAction } from "../../state/useWorkflow";

/** Source status light — the "amber" level is drawn yellow (see MarketPill). */
const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-yellow-400",
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

const PENDING_LABEL: Record<WorkflowAction, string> = {
  spots: "Fetching spots…",
  options: "Fetching option quotes…",
  fetchSnapshot: "Fetching snapshot (quotes + spot)…",
  calibrate: "Calibrating…",
  calibrateParametric: "Calibrating parametric…",
  calibrateLv: "Calibrating local-vol…",
  savePriors: "Saving priors…",
  fetchPriors: "Fetching priors…",
};

/** "75" -> "1:15" (seconds -> m:ss for the auto-fetch countdown). */
function fmtCountdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Short label for the current as-of selection (matches the market pill). */
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

/** "14:32:05" local time. */
function fmtTime(ms: number): string {
  const d = new Date(ms);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

/** Wall clock, ticking once a second (mirrors a trading desk's clock). */
function useClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

function IndeterminateBar({ color }: { color: string }) {
  return (
    <span className="relative inline-block h-1 w-28 overflow-hidden rounded-full bg-surface-700">
      <span className={`volfit-indeterminate-fill ${color}`} />
    </span>
  );
}

function ProgressBar({ done, total, color }: { done: number; total: number; color: string }) {
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
  return (
    <span className="inline-block h-1 w-28 overflow-hidden rounded-full bg-surface-700">
      <span className={`block h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </span>
  );
}

/** "12 s" / "2m 05s" — the elapsed-time caption of the gauge. */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m}m ${String(s % 60).padStart(2, "0")}s`;
}

/** Elapsed vs the client timeout of the in-flight action: the gauge when no
 *  measured progress exists. Turns yellow past half the budget, rose near it. */
function TimeBar({ elapsedMs, timeoutMs }: { elapsedMs: number; timeoutMs: number }) {
  const frac = timeoutMs > 0 ? Math.min(1, elapsedMs / timeoutMs) : 0;
  const color = frac > 0.9 ? "bg-rose-400" : frac > 0.5 ? "bg-yellow-400" : "bg-sky-400";
  return (
    <span
      className="flex shrink-0 items-center gap-2"
      title={`Elapsed ${formatElapsed(elapsedMs)} of a ${formatElapsed(timeoutMs)} client timeout`}
      data-testid="time-bar"
    >
      <span className="inline-block h-1 w-28 overflow-hidden rounded-full bg-surface-700">
        <span className={`block h-full rounded-full ${color}`} style={{ width: `${frac * 100}%` }} />
      </span>
      <span className="font-mono text-[10px] text-slate-500">
        {formatElapsed(elapsedMs)} / {formatElapsed(timeoutMs)}
      </span>
    </span>
  );
}

/** One muted summary chip in the right cluster. */
function Chip({ label, value, tone, title, testId }: {
  label: string; value: string; tone?: string; title?: string; testId?: string;
}) {
  return (
    <span className="flex items-center gap-1.5" title={title} data-testid={testId}>
      <span className="text-[10px] uppercase tracking-wider text-slate-600">{label}</span>
      <span className={tone ?? "text-slate-300"}>{value}</span>
    </span>
  );
}

export default function StatusBar() {
  const { live, workflow, dataSources, asof } = useWorkflowContext();
  const { activity, activeTab } = useWorkbench();
  const { universe } = useSmileSession();
  const { format } = useExpiryFormat();
  const ws = useOptionalWorkspaceFile();
  const now = useClock();
  const { calib, sched, pending, pendingSince, pendingTimeoutMs, lastAction } = workflow;
  const act = calib?.activity;
  const running = calib?.running ?? false;
  // Elapsed of the in-flight client action (Fetch / Calibrate), from its send.
  const actionElapsed = pendingSince !== null ? Math.max(0, now - pendingSince) : null;

  // ---- Primary line + gauge (backend activity > job flag > optimistic label) --
  let message = "";
  let detail = "";
  let stage = "calibrate";
  let gauge: "progress" | "indeterminate" | null = null;
  if (act?.active) {
    message = act.message;
    detail = act.detail;
    stage = act.stage || "calibrate";
    if (running && (calib?.total ?? 0) > 0) gauge = "progress";
    else if (act.total > 0) gauge = "progress";
    else gauge = "indeterminate";
  } else if (running) {
    message = `Calibrating ${calib?.phase || "…"}`;
    gauge = (calib?.total ?? 0) > 0 ? "progress" : "indeterminate";
  } else if (pending) {
    message = PENDING_LABEL[pending];
    stage = pending === "calibrateLv" ? "localvol"
      : pending === "calibrate" || pending === "calibrateParametric" ? "calibrate" : "fetch";
    gauge = "indeterminate";
  }
  const busy = message !== "";
  const color = STAGE_COLOR[stage] ?? "bg-accent-400";
  const gaugeDone = running ? (calib?.done ?? 0) : (act?.done ?? 0);
  const gaugeTotal = running ? (calib?.total ?? 0) : (act?.total ?? 0);
  // Caption next to a determinate bar: the activity's own label ("3.2 / 13.0
  // MB" of a download) when it has one, else plain counts.
  const gaugeLabel = !running && act?.label ? act.label : `${gaugeDone}/${gaugeTotal}`;
  // Elapsed of the narrated step (backend) — "· 12 s" after the message.
  const stepElapsed = act?.active ? (act.elapsedMs ?? 0) : null;

  // ---- Idle summary -------------------------------------------------------
  const lit = calib?.litNodes ?? 0;
  const stale = calib?.staleNodes ?? 0;
  const activeSource = dataSources.sources.find((s) => s.id === dataSources.active);
  // The scheduler chip: a streaming book (live / frozen / refit countdown) or
  // the Auto-update countdown without a stream; nothing when off.
  const streaming = sched?.streaming ?? false;
  const autoUpdate = !streaming && (sched?.autoUpdate ?? "off") !== "off";
  const lastError = calib?.error ?? "";
  const dataAge = dataSources.dataAge;
  const lens = ACTIVITIES.find((a) => a.id === activity)?.label ?? activity;
  const nodeLabel = activeTab
    ? `${activeTab.ticker} ${formatExpiry(
        activeTab.expiry,
        universe?.expiries[activeTab.ticker]?.find((r) => r.expiry === activeTab.expiry)?.t ?? 0,
        format,
      )}`
    : "no node";

  return (
    <footer data-tour="status" className="flex h-7 shrink-0 items-center gap-4 border-t border-slate-800 bg-surface-950 px-3 text-xs">
      {/* Left: narration / Ready, then lens · node */}
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {!live ? (
          <span className="flex shrink-0 items-center gap-2 text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Mock data — backend offline
          </span>
        ) : busy ? (
          <>
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color} animate-pulse`} />
            <span className="shrink-0 font-medium text-slate-200">{message}</span>
            {detail && <span className="truncate font-mono text-[11px] text-slate-500">· {detail}</span>}
            {stepElapsed !== null && stepElapsed >= 1000 && (
              <span className="shrink-0 font-mono text-[10px] text-slate-500" title="Elapsed on this step" data-testid="step-elapsed">
                · {formatElapsed(stepElapsed)}
              </span>
            )}
            {gauge === "progress" && (
              <span className="flex shrink-0 items-center gap-2">
                <ProgressBar done={gaugeDone} total={gaugeTotal} color={color} />
                {gaugeTotal > 0 && (
                  <span className="font-mono text-[10px] text-slate-500">{gaugeLabel}</span>
                )}
              </span>
            )}
            {/* No measured progress: elapsed vs the action's client timeout when
                one is in flight, else the indeterminate strip. */}
            {gauge === "indeterminate" && actionElapsed !== null && pendingTimeoutMs !== null ? (
              <TimeBar elapsedMs={actionElapsed} timeoutMs={pendingTimeoutMs} />
            ) : gauge === "indeterminate" ? (
              <IndeterminateBar color={color} />
            ) : null}
          </>
        ) : (
          <>
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
            <span className="shrink-0 font-medium text-slate-300">Ready</span>
            {lastError && (
              <span className="truncate text-[11px] text-rose-400/80" title={lastError}>
                · last error: {lastError}
              </span>
            )}
          </>
        )}
        <span className="hidden shrink-0 text-slate-700 md:inline">│</span>
        <span className="hidden min-w-0 items-center gap-1.5 text-[11px] text-slate-500 md:flex">
          <span className="uppercase tracking-wider text-slate-600">{lens}</span>
          <span className="truncate font-mono text-slate-400">{nodeLabel}</span>
        </span>
      </div>

      {/* Right: at-a-glance summary */}
      <div className="flex shrink-0 items-center gap-4">
        {live && (
          <>
            {ws !== null && (
              <Chip
                label="Workspace"
                value={ws.dirty ? `${ws.name} · unsaved` : ws.name}
                tone={ws.dirty ? "text-amber-300" : "text-slate-300"}
                title={ws.target ? `Saved to ${ws.target.kind === "server" ? "the server" : "a file"} as "${ws.name}" (Ctrl+S saves)` : "No workspace file yet (Ctrl+Shift+S saves as…)"}
              />
            )}
            <Chip
              label="Nodes"
              value={stale > 0 ? `${lit} lit · ${stale} stale` : `${lit} lit`}
              tone={stale > 0 ? "text-amber-300" : "text-slate-300"}
            />
            {streaming && sched && (
              <Chip
                label="Stream"
                value={sched.streamFreezeFit
                  ? "frozen"
                  : sched.autoCalibrate
                    ? `refit ${fmtCountdown(sched.secondsToNextRefit)}`
                    : "live"}
                tone={sched.streamFreezeFit ? "text-amber-300" : "text-emerald-300"}
                title={sched.streamFreezeFit
                  ? "The live book streams but the fit is held at its calibration spot (Options ▸ Freeze fit while streaming)"
                  : sched.autoCalibrate
                    ? `Spot and quotes flow from the live book; lit nodes refit every ${Math.round(sched.streamRefitSeconds)} s`
                    : "Spot and quotes flow from the live book; the surface transports live, nodes refit on Calibrate"}
                testId="sched-stream-chip"
              />
            )}
            {autoUpdate && sched && (
              <Chip
                label="Next update"
                value={fmtCountdown(sched.secondsToNextUpdate)}
                title={sched.autoUpdate === "snapshot"
                  ? `Auto-update: quotes + spot (the Snapshot sequence) every ${Math.round(sched.autoUpdateSeconds)} s, then auto-calibrate if it is on`
                  : `Auto-update: spot only every ${Math.round(sched.autoUpdateSeconds)} s — transport, never a refit`}
                testId="sched-update-chip"
              />
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
            {dataAge !== null && dataAge.level !== "fresh" && (
              <Chip
                label="Quotes"
                value={dataAge.label}
                tone={dataAge.level === "red" ? "text-rose-300" : "text-yellow-300"}
                title={`Worst live-chain age (${dataAge.worstTicker})`}
              />
            )}
            {lastAction !== null && (
              <span
                className="hidden items-center gap-1.5 xl:flex"
                title={`${lastAction.label} at ${fmtTime(lastAction.at)}`}
              >
                <span className="text-[10px] uppercase tracking-wider text-slate-600">Last</span>
                <span className={`max-w-64 truncate ${lastAction.ok ? "text-slate-300" : "text-rose-300"}`}>
                  {lastAction.label}
                </span>
                <span className="font-mono text-[10px] text-slate-500">{fmtTime(lastAction.at)}</span>
              </span>
            )}
          </>
        )}
        <span className="font-mono text-[11px] text-slate-500" title="Local wall clock">
          {fmtTime(now)}
        </span>
      </div>
    </footer>
  );
}
