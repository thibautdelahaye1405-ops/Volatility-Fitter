// TopBar workflow controls, consolidated: Fetch ▾ (snapshot / spots / options
// quotes) · Calibrate · Priors ▾ (save / fetch).
//
// These are action triggers. The detailed progress narration (what the engine
// is fetching / calibrating, with gauges and node counts) lives in the bottom
// StatusBar; the buttons keep only a MINIMAL CUE — a subtle indeterminate bar
// + disabled state on the action that is currently in flight — so the click
// target still shows it is working. Mode-dependent disabled states (Real-time
// spots, auto options) are kept because they explain why an item is inert.
import { useRef, useState } from "react";
import { Bookmark, ChevronDown, Download, Play, TriangleAlert } from "lucide-react";
import type { DataAgeInfo } from "../state/useDataSources";
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
import { MenuItem, MenuPanel } from "./topbar/Menu";

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
  dataAge = null,
}: {
  workflow: UseWorkflowResult;
  /** Worst live-chain age (useDataSources): red = warn on Calibrate. */
  dataAge?: DataAgeInfo | null;
}) {
  const { calib, sched, pending, busy, fetchSpots, fetchOptions, fetchSnapshot,
    calibrate, calibrateParametric, calibrateLv, priors, savePriors, fetchPriors } = workflow;
  const redStale = dataAge !== null && dataAge.level === "red";
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const lvEnabled = sched?.localVolEnabled ?? true;
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const lvStale = calib?.lvStaleTickers ?? 0;
  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;
  const activePriors = priors?.tickers.filter((t) => t.activeSource).length ?? 0;

  const [fetchOpen, setFetchOpen] = useState(false);
  const [calibOpen, setCalibOpen] = useState(false);
  const [priorsOpen, setPriorsOpen] = useState(false);
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
  const priorsBusy = pending === "savePriors" || pending === "fetchPriors";

  // Transient "✓" acknowledgments on the Priors face (no toast system; mirrors
  // the per-node Save-prior flash). Tells the user the bulk action actually ran.
  const [flash, setFlash] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const showFlash = (text: string) => {
    setFlash(text);
    timers.current.push(window.setTimeout(() => setFlash(null), 2400));
  };
  const onSavePriors = () => {
    setPriorsOpen(false);
    void savePriors().then((r) => {
      if (r) showFlash(r.nodes > 0 ? `Saved ${r.nodes} ✓` : "Nothing to save");
    });
  };
  const onFetchPriors = () => {
    setPriorsOpen(false);
    void fetchPriors().then((r) => {
      if (r) {
        const active = r.tickers.filter((t) => t.source !== "none").length;
        showFlash(active > 0 ? `Activated ${active} ✓` : "No prior found");
      }
    });
  };

  return (
    <div className="flex items-center gap-2 text-xs">
      {/* Fetch ▾ — market-data pulls */}
      <div className="relative">
        <button
          onClick={() => setFetchOpen((v) => !v)}
          disabled={busy && !fetching}
          title="Fetch market data"
          className={`${BTN} ${fetching ? WORKING : ACTIVE}`}
        >
          <Download size={13} strokeWidth={1.75} className="opacity-80" />
          Fetch
          <ChevronDown size={11} className="text-slate-500" />
          {fetching && <WorkingBar />}
        </button>
        <MenuPanel open={fetchOpen} onClose={() => setFetchOpen(false)} width="w-64">
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

      {/* Priors ▾ — surface snapshots (save all / fetch freshness ladder) */}
      <div className="relative">
        <button
          onClick={() => setPriorsOpen((v) => !v)}
          disabled={busy && !priorsBusy}
          title="Prior surfaces (save / fetch)"
          className={`${BTN} ${
            flash
              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
              : priorsBusy
                ? WORKING
                : ACTIVE
          }`}
        >
          <Bookmark size={13} strokeWidth={1.75} className="opacity-80" />
          {flash ?? "Priors"}
          <ChevronDown size={11} className="text-slate-500" />
          {priorsBusy && <WorkingBar />}
        </button>
        <MenuPanel open={priorsOpen} onClose={() => setPriorsOpen(false)} width="w-64">
          <MenuItem
            label="Save priors"
            detail={
              savedTickers > 0 ? `${savedTickers} ticker(s) saved` : "snapshot all fits"
            }
            disabled={busy}
            onClick={onSavePriors}
          />
          <MenuItem
            label="Fetch priors"
            detail={
              savedTickers === 0
                ? "save priors first"
                : activePriors > 0
                  ? `${activePriors} active`
                  : "saved → 15m-before-close → close"
            }
            disabled={busy || savedTickers === 0}
            onClick={onFetchPriors}
          />
        </MenuPanel>
      </div>
    </div>
  );
}
