// TopBar workflow controls, consolidated: Fetch ▾ (snapshot / spots / options
// quotes + the As-of picker) · Calibrate·scope ▾ · Priors ▾ (PriorsMenu).
//
// These are action triggers. The detailed progress narration (what the engine
// is fetching / calibrating, with gauges and node counts) lives in the bottom
// StatusBar; the buttons keep only a MINIMAL CUE — a subtle indeterminate bar
// + disabled state on the action that is currently in flight — so the click
// target still shows it is working. Mode-dependent disabled states (Real-time
// spots, auto options) are kept because they explain why an item is inert.
//
// Fetch ▾ also hosts the As-of rows (topbar/AsOfRows): Live / Previous Close /
// historical day → moment — "what timestamp am I pulling" sits next to the
// pull verbs, and the market pill is a passive readout. The Priors ▾ block
// (per-tab / all-tabs / all-calibrated saves + fetch) lives in topbar/PriorsMenu.
import { useState } from "react";
import { ChevronDown, Download, Play, TriangleAlert } from "lucide-react";
import type { DataAgeInfo } from "../state/useDataSources";
import type { UseAsOfResult } from "../state/useAsOf";
import type { UseWorkflowResult } from "../state/useWorkflow";
import {
  CALIB_SCOPES,
  SCOPE_LABEL,
  SCOPE_SHORT,
  readCalibScope,
  scopeBadge,
  scopeDetail,
  writeCalibScope,
  type CalibScope,
} from "../lib/calibScope";
import { MenuDivider, MenuItem, MenuPanel } from "./topbar/Menu";
import { AsOfRows } from "./topbar/AsOfRows";
import PriorsMenu from "./topbar/PriorsMenu";

const BTN =
  "relative flex items-center gap-1.5 overflow-hidden rounded-md border px-2.5 py-1 " +
  "font-medium transition-colors disabled:cursor-not-allowed";
const ACTIVE = "border-slate-700 bg-surface-800 text-slate-200 hover:border-slate-600";
const WORKING = "border-accent-500/50 bg-accent-500/10 text-accent-300";

/** Subtle indeterminate "working" cue overlaid on the in-flight button. */
function WorkingBar() {
  return (
    <span className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-accent-500/15">
      <span className="volfit-indeterminate-fill bg-accent-400" />
    </span>
  );
}

export default function WorkflowControls({
  workflow,
  asof,
  dataAge = null,
  live = true,
}: {
  workflow: UseWorkflowResult;
  /** As-of selector state (rendered at the bottom of Fetch ▾). */
  asof: UseAsOfResult;
  /** Worst live-chain age (useDataSources): red = warn on Calibrate. */
  dataAge?: DataAgeInfo | null;
  /** Live backend (per-node prior saves need a fit session). */
  live?: boolean;
}) {
  const { calib, sched, pending, busy, fetchSpots, fetchOptions, fetchSnapshot,
    calibrate, calibrateParametric, calibrateLv } = workflow;
  const redStale = dataAge !== null && dataAge.level === "red";
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const lvEnabled = sched?.localVolEnabled ?? true;
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const lvStale = calib?.lvStaleTickers ?? 0;

  const [fetchOpen, setFetchOpen] = useState(false);
  const [calibOpen, setCalibOpen] = useState(false);
  // Calibrate scope — three first-class choices (Param + LV / Param only /
  // LV only); the face runs the LAST chosen one and names it; sticky.
  const [calibScope, setCalibScope] = useState<CalibScope>(() => readCalibScope());
  const runScope = (scope: CalibScope) => {
    setCalibScope(scope);
    writeCalibScope(scope);
    return scope === "both" ? calibrate() : scope === "parametric" ? calibrateParametric() : calibrateLv();
  };
  const scopeCount = scopeBadge(calibScope, stale, lvStale);
  const fetching =
    pending === "spots" || pending === "options" || pending === "fetchSnapshot";
  const calibrating =
    pending === "calibrate" || pending === "calibrateParametric" || pending === "calibrateLv";

  return (
    <div className="flex items-center gap-2 text-xs">
      {/* Fetch ▾ — market-data pulls + the As-of picker */}
      <div className="relative">
        <button
          onClick={() => setFetchOpen((v) => !v)}
          disabled={busy && !fetching}
          title="Fetch market data · pick the as-of timestamp"
          className={`${BTN} ${fetching ? WORKING : ACTIVE}`}
        >
          <Download size={13} strokeWidth={1.75} className="opacity-80" />
          Fetch
          <ChevronDown size={11} className="text-slate-500" />
          {fetching && <WorkingBar />}
        </button>
        <MenuPanel open={fetchOpen} onClose={() => setFetchOpen(false)} width="w-72">
          {/* The unified verb (V3.7 item 15): quotes + spot in one pull; rolls
              the active priors to their latest saved snapshots when the Options
              toggle (Auto-roll prior on fetch) is on, then auto-calibrates. */}
          <MenuItem
            label="Snapshot (quotes + spot)"
            detail="chains + live spots in one pull"
            disabled={busy}
            onClick={() => { setFetchOpen(false); void fetchSnapshot(); }}
          />
          <MenuItem
            label={realtimeSpots ? "Spots · real-time" : "Spots"}
            detail={realtimeSpots ? "streaming (set in Options)" : "refresh live spots now"}
            disabled={realtimeSpots || busy}
            onClick={() => { setFetchOpen(false); void fetchSpots(); }}
          />
          <MenuItem
            label={autoOptions ? "Options quotes · auto" : "Options quotes"}
            detail={autoOptions ? "on a timer (status bar)" : "fetch fresh quotes now"}
            disabled={autoOptions || busy}
            onClick={() => { setFetchOpen(false); void fetchOptions(); }}
          />
          {/* As-of: Live / Previous Close / historical day → moment. Rows
              render only once GET /asof has answered (AsOfRows guards). */}
          {asof.asof !== null && (
            <>
              <MenuDivider />
              <AsOfRows asof={asof} onDone={() => setFetchOpen(false)} />
            </>
          )}
        </MenuPanel>
      </div>

      {/* Calibrate — a split control with THREE first-class scopes (V3.5 item
          9 verbs): "Parametric + LV" (POST /calibrate, LV still gated
          server-side by the Options toggle), "Parametric only" (the fast loop;
          LV surfaces go/stay stale) and "Local-Vol only" (no parametric
          refit). The primary face runs the LAST CHOSEN scope and names it
          ("Calibrate · Param only"); the chevron menu switches + runs (✓ marks
          the current scope, sticky across reloads). Badge: stale parametric
          nodes for the parametric scopes, stale LV surfaces for LV only.
          Background jobs; progress shows in the status bar. Red-stale live
          data (the market pill's age) shows a warning cue: calibrating still
          works, but it is a fit of the previous session. */}
      <div className="relative flex items-stretch">
        <button
          onClick={() => void runScope(calibScope)}
          disabled={running || busy}
          title={
            redStale
              ? `Warning: live quotes are ${dataAge!.label} old (previous session) — calibrating fits stale data`
              : `Calibrate — ${SCOPE_LABEL[calibScope]} (▾ to change the scope)`
          }
          className={[
            BTN,
            "rounded-r-none",
            running || calibrating
              ? WORKING
              : redStale
                ? "border-rose-500/50 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
                : scopeCount > 0
                  ? "border-accent-500/50 bg-accent-500/15 text-accent-300 hover:bg-accent-500/25"
                  : ACTIVE,
          ].join(" ")}
        >
          {redStale && !running ? (
            <TriangleAlert size={13} strokeWidth={1.75} className="opacity-90" />
          ) : (
            <Play size={13} strokeWidth={1.75} className="opacity-80" />
          )}
          <span>Calibrate</span>
          <span className="text-[10px] font-normal text-slate-400">· {SCOPE_SHORT[calibScope]}</span>
          {!running && scopeCount > 0 && <span>({scopeCount})</span>}
          {(running || calibrating) && <WorkingBar />}
        </button>
        <button
          onClick={() => setCalibOpen((v) => !v)}
          disabled={running || busy}
          title="Calibration scope: Parametric + LV / Parametric only / Local-Vol only"
          className={[
            BTN,
            "rounded-l-none border-l-0 px-1.5",
            running || calibrating ? WORKING : ACTIVE,
          ].join(" ")}
        >
          <ChevronDown size={11} className="text-slate-500" />
        </button>
        <MenuPanel open={calibOpen} onClose={() => setCalibOpen(false)} width="w-[22rem]">
          {CALIB_SCOPES.map((scope) => {
            const n = scopeBadge(scope, stale, lvStale);
            return (
              <MenuItem
                key={scope}
                label={n > 0 ? `${SCOPE_LABEL[scope]} (${n})` : SCOPE_LABEL[scope]}
                detail={scopeDetail(scope, stale, lvStale, lvEnabled)}
                active={scope === calibScope}
                disabled={running || busy}
                onClick={() => { setCalibOpen(false); void runScope(scope); }}
              />
            );
          })}
        </MenuPanel>
      </div>

      {/* Priors ▾ — visible tab / open tabs / all calibrated · fetch */}
      <PriorsMenu workflow={workflow} live={live} />
    </div>
  );
}
