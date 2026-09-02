// Wire types of the calibration / data-fetch workflow (GET /calibration/status,
// GET /scheduler, GET /priors, POST /priors/*) plus the status-bar labels of
// the manual verbs. Split out of useWorkflow.ts (UI SHELL v2) so the hook
// stays under the file-size policy; useWorkflow re-exports the types.

/** The fine-grained engine activity in flight (what the engine is doing now),
 *  narrated to the bottom status bar. `active` false => idle. */
export interface ActivityInfo {
  active: boolean;
  stage: string; // fetch | calibrate | localvol | term | density | surface
  message: string; // primary line, e.g. "Calibrating SPY 2026-07-17 (LQD)"
  detail: string; // secondary line, e.g. "de-americanizing"
  done: number; // progress numerator (0 with total 0 => indeterminate)
  total: number; // progress denominator
  /** Caption for done/total when they are not plain counts ("3.2 / 13.0 MB"
   *  for a chain download); "" = show "done/total". Optional for older payloads. */
  label?: string;
  /** Milliseconds since the in-flight activity started (the elapsed gauge). */
  elapsedMs?: number;
  seq: number; // monotonic; advances on every change
}

/** Response of GET /calibration/status. */
export interface CalibrationStatus {
  running: boolean;
  total: number;
  done: number;
  current: string;
  error: string;
  cancelled: boolean;
  litNodes: number;
  staleNodes: number;
  /** Lit tickers whose LV (affine) surface drifted since its last LV
   *  calibration (V3.5 item 9 — the "Local-Vol only" badge). 0 while Local-Vol
   *  is gated off. Optional for older payloads. */
  lvStaleTickers?: number;
  spotVersion: number;
  /** Monotonic calibration epoch: advances whenever a re-calibration changes an
   *  already-calibrated node's displayed fit. The view layer refetches every
   *  mounted view the moment it advances (level-triggered, race-free). */
  epoch: number;
  /** Coarse phase of the in-flight item: "Parametric" | "Local Vol" | "". */
  phase: string;
  /** Fine-grained engine activity (the status-bar narration). */
  activity: ActivityInfo;
}

/** Response of GET /scheduler. */
export interface SchedulerStatus {
  running: boolean;
  spotMode: "realtime" | "static";
  optionsFetchMode: "auto" | "on_demand";
  autoCalibrate: boolean;
  localVolEnabled: boolean; // gates the Local Vol tab + LV calibration
  secondsToNextOptions: number; // -1 when on-demand
  secondsToNextSpot: number; // -1 when static
  /** The auto chain timer runs the unified snapshot sequence and absorbs the
   *  spot poll (OptionsSettings.schedulerUnifiedFetch echoed). */
  unifiedFetch?: boolean;
}

/** Per-ticker saved-prior availability (GET /priors). */
export interface PriorTickerStatus {
  ticker: string;
  dataTs: string | null;
  savedTs: string | null;
  asOfLabel: string | null;
  nodeCount: number;
  hasLvSurface: boolean;
  /** The active fetched prior (after 'Fetch priors'): ladder source + its moment. */
  activeSource: string | null; // "saved" | "15min" | "close" | null
  activeDataTs: string | null;
}
export interface PriorStatus {
  tickers: PriorTickerStatus[];
}

/** Which manual action is currently in flight (drives the per-button gauge). */
export type WorkflowAction =
  | "spots"
  | "options"
  | "fetchSnapshot"
  | "calibrate"
  | "calibrateParametric"
  | "calibrateLv"
  | "savePriors"
  | "fetchPriors";

/** POST /priors/save-all result. */
export interface PriorSaveResult {
  tickers: string[];
  nodes: number;
  persisted: boolean;
}

/** POST /priors/fetch result (per-ticker freshness-ladder outcome). */
export interface PriorFetchResult {
  tickers: { ticker: string; source: string; dataTs: string | null; nodeCount: number }[];
}

/** The last completed workflow action (status-bar "Last: …" chip). */
export interface LastAction {
  label: string;
  /** Epoch ms. */
  at: number;
  ok: boolean;
}

/** Status-bar label once an explicit action completed. */
export const DONE_LABEL: Record<WorkflowAction, string> = {
  spots: "Fetched spots",
  options: "Fetched option quotes",
  fetchSnapshot: "Fetched snapshot",
  calibrate: "Calibrated parametric + LV",
  calibrateParametric: "Calibrated parametric",
  calibrateLv: "Calibrated local-vol",
  savePriors: "Saved priors",
  fetchPriors: "Fetched priors",
};

/** Status-bar label when an explicit action failed (the error is appended). */
export const FAIL_LABEL: Record<WorkflowAction, string> = {
  spots: "Spot fetch failed",
  options: "Option-quote fetch failed",
  fetchSnapshot: "Snapshot fetch failed",
  calibrate: "Calibration failed",
  calibrateParametric: "Parametric calibration failed",
  calibrateLv: "Local-vol calibration failed",
  savePriors: "Saving priors failed",
  fetchPriors: "Fetching priors failed",
};
