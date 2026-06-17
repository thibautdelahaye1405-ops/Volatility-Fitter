// TopBar workflow controls: Fetch spots · Fetch Options Quotes · Calibrate.
//
// Mirrors the backend trigger model (useWorkflow):
//  * Fetch spots       — greyed "Real-time Spots" when spotMode = realtime
//                        (the scheduler polls), else a manual button.
//  * Fetch Options     — a greyed countdown to the next auto fetch when
//                        optionsFetchMode = auto, else a manual button.
//  * Calibrate         — background-calibrates all lit nodes; shows progress
//                        while running and a stale-node badge when work is due.
import type { UseWorkflowResult } from "../state/useWorkflow";

/** "75" -> "1:15" (seconds -> m:ss for the auto-fetch countdown). */
function fmtCountdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const BTN =
  "relative overflow-hidden rounded-md border px-2.5 py-1 font-medium transition-colors disabled:cursor-not-allowed";
const ACTIVE = "border-slate-700 bg-surface-800 text-slate-200 hover:border-slate-600";
const MUTED = "border-slate-800 bg-surface-900 text-slate-500";
const FETCHING = "border-accent-500/50 bg-accent-500/10 text-accent-300";

/** Indeterminate "working" gauge overlaid on a fetch button while it runs. */
function FetchingBar() {
  return (
    <span className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-accent-500/15">
      <span className="volfit-indeterminate-fill bg-accent-400" />
    </span>
  );
}

export default function WorkflowControls({ workflow }: { workflow: UseWorkflowResult }) {
  const { calib, sched, pending, busy, fetchSpots, fetchOptions, calibrate, priors, savePriors } =
    workflow;
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const fetchingSpots = pending === "spots";
  const fetchingOptions = pending === "options";
  const savingPriors = pending === "savePriors";
  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;

  return (
    <div className="flex items-center gap-2 text-xs">
      {/* Fetch spots (indeterminate gauge while fetching) */}
      <button
        onClick={() => void fetchSpots()}
        disabled={realtimeSpots || busy}
        title={realtimeSpots ? "Spots stream in real time (set in Options)" : "Fetch live spots now"}
        className={`${BTN} ${realtimeSpots ? MUTED : fetchingSpots ? FETCHING : ACTIVE}`}
      >
        {realtimeSpots ? "Real-time Spots" : fetchingSpots ? "Fetching spots…" : "Fetch spots"}
        {fetchingSpots && <FetchingBar />}
      </button>

      {/* Fetch options quotes (countdown when auto, gauge while fetching) */}
      <button
        onClick={() => void fetchOptions()}
        disabled={autoOptions || busy}
        title={
          autoOptions
            ? "Options auto-refresh on a timer (set in Options)"
            : "Fetch fresh option quotes now"
        }
        className={`${BTN} ${autoOptions ? MUTED : fetchingOptions ? FETCHING : ACTIVE}`}
      >
        {autoOptions
          ? `Options in ${fmtCountdown(sched?.secondsToNextOptions ?? 0)}`
          : fetchingOptions
            ? "Fetching quotes…"
            : "Fetch Options Quotes"}
        {fetchingOptions && <FetchingBar />}
      </button>

      {/* Calibrate all lit nodes (background, with progress + stale badge) */}
      <button
        onClick={() => void calibrate()}
        disabled={running || busy}
        title="Calibrate all lit nodes"
        className={[
          BTN,
          running
            ? MUTED
            : stale > 0
              ? "border-accent-500/50 bg-accent-500/15 text-accent-300 hover:bg-accent-500/25"
              : ACTIVE,
        ].join(" ")}
      >
        {running
          ? `Calibrating ${calib?.phase || "…"}`
          : stale > 0
            ? `Calibrate (${stale})`
            : "Calibrate"}
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
        className={`${BTN} ${savingPriors ? FETCHING : ACTIVE}`}
      >
        {savingPriors ? "Saving priors…" : "Save priors"}
        {savingPriors && <FetchingBar />}
      </button>

      {/* Compact calibration progress gauge (only while a job is running) */}
      {running && (
        <div className="flex flex-col gap-0.5">
          <div className="h-1 w-16 overflow-hidden rounded-full bg-surface-700">
            <div
              className="h-full rounded-full bg-accent-500 transition-all"
              style={{
                width: `${
                  (calib?.total ?? 0) > 0
                    ? ((calib?.done ?? 0) / (calib?.total ?? 1)) * 100
                    : 0
                }%`,
              }}
            />
          </div>
          <span className="max-w-16 truncate font-mono text-[10px] text-slate-400">
            {calib?.current || "…"}
          </span>
        </div>
      )}
    </div>
  );
}
