// TopBar workflow controls: Fetch spots · Fetch Options Quotes · Calibrate ·
// Save priors · Fetch priors.
//
// These are action triggers. The detailed progress narration (what the engine
// is fetching / calibrating, with gauges and node counts) now lives in the
// bottom StatusBar; the buttons keep only a MINIMAL CUE — a subtle indeterminate
// bar + disabled state on the action that is currently in flight — so the click
// target still shows it is working. Mode-dependent disabled states (Real-time
// spots, auto options) are kept because they explain why a button is inert.
import type { UseWorkflowResult } from "../state/useWorkflow";

const BTN =
  "relative overflow-hidden rounded-md border px-2.5 py-1 font-medium transition-colors disabled:cursor-not-allowed";
const ACTIVE = "border-slate-700 bg-surface-800 text-slate-200 hover:border-slate-600";
const MUTED = "border-slate-800 bg-surface-900 text-slate-500";
const WORKING = "border-accent-500/50 bg-accent-500/10 text-accent-300";

/** Subtle indeterminate "working" cue overlaid on the in-flight button. */
function WorkingBar() {
  return (
    <span className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-accent-500/15">
      <span className="volfit-indeterminate-fill bg-accent-400" />
    </span>
  );
}

export default function WorkflowControls({ workflow }: { workflow: UseWorkflowResult }) {
  const { calib, sched, pending, busy, fetchSpots, fetchOptions, calibrate, priors, savePriors,
    fetchPriors } = workflow;
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;
  const activePriors = priors?.tickers.filter((t) => t.activeSource).length ?? 0;

  return (
    <div className="flex items-center gap-2 text-xs">
      {/* Fetch spots */}
      <button
        onClick={() => void fetchSpots()}
        disabled={realtimeSpots || busy}
        title={realtimeSpots ? "Spots stream in real time (set in Options)" : "Fetch live spots now"}
        className={`${BTN} ${realtimeSpots ? MUTED : pending === "spots" ? WORKING : ACTIVE}`}
      >
        {realtimeSpots ? "Real-time Spots" : "Fetch spots"}
        {pending === "spots" && <WorkingBar />}
      </button>

      {/* Fetch options quotes (muted when on the auto timer — countdown is in the
          status bar; this just marks why the button is inert) */}
      <button
        onClick={() => void fetchOptions()}
        disabled={autoOptions || busy}
        title={
          autoOptions
            ? "Options auto-refresh on a timer (countdown in the status bar)"
            : "Fetch fresh option quotes now"
        }
        className={`${BTN} ${autoOptions ? MUTED : pending === "options" ? WORKING : ACTIVE}`}
      >
        {autoOptions ? "Options · auto" : "Fetch Options Quotes"}
        {pending === "options" && <WorkingBar />}
      </button>

      {/* Calibrate all lit nodes (background; progress shows in the status bar).
          A stale-count highlight remains as an actionable cue. */}
      <button
        onClick={() => void calibrate()}
        disabled={running || busy}
        title="Calibrate all lit nodes"
        className={[
          BTN,
          running
            ? WORKING
            : stale > 0
              ? "border-accent-500/50 bg-accent-500/15 text-accent-300 hover:bg-accent-500/25"
              : ACTIVE,
        ].join(" ")}
      >
        {!running && stale > 0 ? `Calibrate (${stale})` : "Calibrate"}
        {running && <WorkingBar />}
      </button>

      {/* Save all current calibrations as priors (a full surface snapshot each) */}
      <button
        onClick={() => void savePriors()}
        disabled={busy}
        title={
          savedTickers > 0
            ? `Save all current calibrations as priors (${savedTickers} ticker(s) saved)`
            : "Save all current calibrations as priors"
        }
        className={`${BTN} ${pending === "savePriors" ? WORKING : ACTIVE}`}
      >
        Save priors
        {pending === "savePriors" && <WorkingBar />}
      </button>

      {/* Fetch priors (freshness ladder) — activates the dotted spot-updated overlay */}
      <button
        onClick={() => void fetchPriors()}
        disabled={busy || savedTickers === 0}
        title={
          savedTickers === 0
            ? "Save priors first, then fetch to overlay them"
            : activePriors > 0
              ? `Fetch priors (${activePriors} active)`
              : "Fetch priors (Saved → 15m-before-prev-close → prev-close)"
        }
        className={`${BTN} ${
          savedTickers === 0 ? MUTED : pending === "fetchPriors" ? WORKING : ACTIVE
        }`}
      >
        Fetch priors
        {pending === "fetchPriors" && <WorkingBar />}
      </button>
    </div>
  );
}
