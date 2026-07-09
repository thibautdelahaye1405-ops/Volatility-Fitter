// TopBar workflow controls, consolidated: Fetch ▾ (spots / options quotes) ·
// Calibrate · Priors ▾ (save / fetch).
//
// These are action triggers. The detailed progress narration (what the engine
// is fetching / calibrating, with gauges and node counts) lives in the bottom
// StatusBar; the buttons keep only a MINIMAL CUE — a subtle indeterminate bar
// + disabled state on the action that is currently in flight — so the click
// target still shows it is working. Mode-dependent disabled states (Real-time
// spots, auto options) are kept because they explain why an item is inert.
import { useRef, useState } from "react";
import { Bookmark, ChevronDown, Download, Play } from "lucide-react";
import type { UseWorkflowResult } from "../state/useWorkflow";
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

export default function WorkflowControls({ workflow }: { workflow: UseWorkflowResult }) {
  const { calib, sched, pending, busy, fetchSpots, fetchOptions, calibrate, priors, savePriors,
    fetchPriors } = workflow;
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;
  const activePriors = priors?.tickers.filter((t) => t.activeSource).length ?? 0;

  const [fetchOpen, setFetchOpen] = useState(false);
  const [priorsOpen, setPriorsOpen] = useState(false);
  const fetching = pending === "spots" || pending === "options";
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

      {/* Calibrate — the primary verb keeps its own button (background job;
          progress shows in the status bar). Stale count stays actionable. */}
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
        <Play size={13} strokeWidth={1.75} className="opacity-80" />
        {!running && stale > 0 ? `Calibrate (${stale})` : "Calibrate"}
        {running && <WorkingBar />}
      </button>

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
