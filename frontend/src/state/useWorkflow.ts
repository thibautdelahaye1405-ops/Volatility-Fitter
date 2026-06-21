// Calibration / data-fetch workflow state for the TopBar controls.
//
// Polls the backend trigger model (GET /calibration/status + /scheduler) for the
// background-calibration progress, the lit/stale node counts and the auto-fetch
// countdowns, and exposes the manual actions (Fetch spots / Fetch Options /
// Calibrate). When a background calibration finishes, or the backend scheduler
// transports the surface (real-time spot), it bumps the session's view version
// so every workspace re-pulls the refreshed views. Live backend only.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** The fine-grained engine activity in flight (what the engine is doing now),
 *  narrated to the bottom status bar. `active` false => idle. */
export interface ActivityInfo {
  active: boolean;
  stage: string; // fetch | calibrate | localvol | term | density | surface
  message: string; // primary line, e.g. "Calibrating SPY 2026-07-17 (LQD)"
  detail: string; // secondary line, e.g. "de-americanizing"
  done: number; // progress numerator (0 with total 0 => indeterminate)
  total: number; // progress denominator
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

/** Status poll cadence (ms): a brisk cadence while the engine is active (so the
 *  status-bar narration keeps up with what it's doing) and a relaxed one when
 *  idle (just the auto-fetch countdown / stale accounting). */
const POLL_ACTIVE_MS = 500;
const POLL_IDLE_MS = 3000;
/** When the tab is hidden the user can't see any status, so we all but stop
 *  polling (a slow heartbeat keeps the connection warm); becoming visible again
 *  triggers an immediate poll via the visibilitychange listener below. */
const POLL_HIDDEN_MS = 15000;

/** Which manual action is currently in flight (drives the per-button gauge). */
export type WorkflowAction = "spots" | "options" | "calibrate" | "savePriors" | "fetchPriors";

export interface UseWorkflowResult {
  calib: CalibrationStatus | null;
  sched: SchedulerStatus | null;
  /** The in-flight manual action, or null. (`busy` = pending !== null.) */
  pending: WorkflowAction | null;
  busy: boolean;
  fetchSpots: () => Promise<void>;
  fetchOptions: () => Promise<void>;
  calibrate: () => Promise<void>;
  /** Saved-prior availability across the active universe (null until first poll). */
  priors: PriorStatus | null;
  /** Snapshot every ticker's current calibration as a prior (POST /priors/save-all).
   *  Returns the save result (tickers + total nodes snapshotted + whether it was
   *  persisted to disk) so the UI can acknowledge the action. */
  savePriors: () => Promise<PriorSaveResult | undefined>;
  /** Resolve + activate each ticker's prior via the freshness ladder (POST /priors/fetch).
   *  Returns the per-ticker fetch outcome (source + node count). */
  fetchPriors: () => Promise<PriorFetchResult | undefined>;
}

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

export function useWorkflow(
  live: boolean,
  refreshViews: () => void,
  fitMode: string,
): UseWorkflowResult {
  const [calib, setCalib] = useState<CalibrationStatus | null>(null);
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [priors, setPriors] = useState<PriorStatus | null>(null);
  // Last-seen monotonic counters; a poll that observes either advance refetches
  // every mounted view. Level-triggered (compare-to-last), so it is immune to
  // missed running->idle edges, fast single-node jobs, background / scheduler
  // calibrations, and which view happens to be open. null until the first poll
  // establishes a baseline (so the very first poll never spuriously refetches).
  const lastEpoch = useRef<number | null>(null);
  const lastSpotVer = useRef<number | null>(null);
  // Whether the engine is currently working (a job running or an activity in
  // flight) — drives the adaptive poll cadence.
  const activeRef = useRef(false);

  const refreshPriors = useCallback(async () => {
    try {
      setPriors(await api.get<PriorStatus>("/priors"));
    } catch {
      /* backend unreachable: leave the last status */
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        // Pass the viewed fit target so the stale accounting reports the SAME
        // per-mode pointer the smile is shown in (mid vs bid-ask vs haircut).
        api.get<CalibrationStatus>("/calibration/status", { params: { fit_mode: fitMode } }),
        api.get<SchedulerStatus>("/scheduler"),
      ]);
      setCalib(c);
      setSched(s);
      activeRef.current = c.running || c.activity.active;
      // A (re)calibration changed a displayed fit somewhere — refetch all mounted
      // views (covers the explicit Calibrate button, auto-calibrate on fetch, the
      // streaming refit, and progressive per-node commits during a running job).
      if (lastEpoch.current !== null && c.epoch !== lastEpoch.current) refreshViews();
      lastEpoch.current = c.epoch;
      // Pure spot transport (no recalibration) — the backend scheduler moved the
      // surface under real-time spot; refetch so the transported curves follow.
      if (lastSpotVer.current !== null && c.spotVersion !== lastSpotVer.current) {
        refreshViews();
      }
      lastSpotVer.current = c.spotVersion;
    } catch {
      /* backend unreachable: leave the last status */
    }
  }, [refreshViews, fitMode]);

  useEffect(() => {
    if (!live) return;
    let timer = 0;
    let stopped = false;
    const hidden = () => typeof document !== "undefined" && document.hidden;
    const nextDelay = () =>
      hidden() ? POLL_HIDDEN_MS : activeRef.current ? POLL_ACTIVE_MS : POLL_IDLE_MS;
    // Self-rescheduling loop so the cadence can follow the engine: brisk while it
    // works, relaxed when idle, all but paused when the tab is hidden.
    // (setInterval can't change its own period.)
    const tick = async () => {
      if (!hidden()) await poll(); // no point hitting the backend for an unseen UI
      if (stopped) return;
      timer = window.setTimeout(() => void tick(), nextDelay());
    };
    // Coming back to a visible tab: poll right away so the status is fresh.
    const onVisible = () => {
      if (!hidden() && !stopped) {
        window.clearTimeout(timer);
        void tick();
      }
    };
    void tick();
    void refreshPriors(); // saved-prior availability (not in the hot poll loop)
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [live, poll, refreshPriors]);

  // Snappy path for the explicit buttons: wait for the background job to go idle,
  // then refresh immediately rather than waiting up to one poll interval. This is
  // pure UX latency — the epoch-level poll above is the correctness backstop, so a
  // missed wait (fast job, backend blip) still self-heals on the next poll.
  // Bounded; a short startup grace lets the job thread flip running=true first.
  const awaitCalibration = useCallback(async () => {
    for (let i = 0; i < 400; i++) {
      await new Promise((r) => setTimeout(r, 150));
      try {
        const c = await api.get<CalibrationStatus>("/calibration/status", {
          params: { fit_mode: fitMode },
        });
        setCalib(c);
        if (!c.running && i >= 2) return; // idle past the ~450ms startup grace
      } catch {
        return; // backend unreachable: stop waiting
      }
    }
  }, [fitMode]);

  const action = useCallback(
    async (key: WorkflowAction, path: string, withBody: boolean, awaitJob = false) => {
      setPending(key);
      try {
        // fit_mode targets the mode the smile is VIEWED in, so Calibrate / the
        // auto-fetch re-point the same per-mode calibrated pointer (otherwise a
        // bid-ask / haircut smile stays frozen because only "mid" was calibrated).
        await api.post(path, { params: { fit_mode: fitMode }, ...(withBody ? { body: {} } : {}) });
        if (awaitJob) await awaitCalibration(); // block until the fit completes
        await poll(); // resync status + advance the epoch/spot baselines
        refreshViews(); // refetch every view against the now-current fit
      } finally {
        setPending(null);
      }
    },
    [refreshViews, poll, awaitCalibration, fitMode],
  );

  // calibrate + fetchOptions start a background calibration job, so they await its
  // completion before refreshing; fetchSpots is pure transport (nothing to await).
  const fetchSpots = useCallback(() => action("spots", "/fetch/spots", true), [action]);
  const fetchOptions = useCallback(() => action("options", "/fetch/options", true, true), [action]);
  const calibrate = useCallback(() => action("calibrate", "/calibrate", false, true), [action]);

  const savePriors = useCallback(async () => {
    setPending("savePriors");
    try {
      const res = await api.post<PriorSaveResult>("/priors/save-all");
      await refreshPriors();
      return res;
    } finally {
      setPending(null);
    }
  }, [refreshPriors]);

  const fetchPriors = useCallback(async () => {
    setPending("fetchPriors");
    try {
      const res = await api.post<PriorFetchResult>("/priors/fetch");
      await refreshPriors();
      refreshViews(); // the dotted, spot-updated prior overlays change on every view
      return res;
    } finally {
      setPending(null);
    }
  }, [refreshPriors, refreshViews]);

  return {
    calib, sched, pending, busy: pending !== null,
    fetchSpots, fetchOptions, calibrate, priors, savePriors, fetchPriors,
  };
}
