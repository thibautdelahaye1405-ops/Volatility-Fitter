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
  /** Coarse phase of the in-flight item: "Parametric" | "Local Vol" | "". */
  phase: string;
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

/** Status poll cadence (ms): drives progress + the auto-fetch countdown. */
const POLL_MS = 1500;

/** Which manual action is currently in flight (drives the per-button gauge). */
export type WorkflowAction = "spots" | "options" | "calibrate";

export interface UseWorkflowResult {
  calib: CalibrationStatus | null;
  sched: SchedulerStatus | null;
  /** The in-flight manual action, or null. (`busy` = pending !== null.) */
  pending: WorkflowAction | null;
  busy: boolean;
  fetchSpots: () => Promise<void>;
  fetchOptions: () => Promise<void>;
  calibrate: () => Promise<void>;
}

export function useWorkflow(live: boolean, refreshViews: () => void): UseWorkflowResult {
  const [calib, setCalib] = useState<CalibrationStatus | null>(null);
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const wasRunning = useRef(false);
  const lastSpotVer = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        api.get<CalibrationStatus>("/calibration/status"),
        api.get<SchedulerStatus>("/scheduler"),
      ]);
      setCalib(c);
      setSched(s);
      if (wasRunning.current && !c.running) refreshViews(); // job finished
      wasRunning.current = c.running;
      if (lastSpotVer.current !== null && c.spotVersion !== lastSpotVer.current) {
        refreshViews(); // backend scheduler transported the surface (RT spot)
      }
      lastSpotVer.current = c.spotVersion;
    } catch {
      /* backend unreachable: leave the last status */
    }
  }, [refreshViews]);

  useEffect(() => {
    if (!live) return;
    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => window.clearInterval(id);
  }, [live, poll]);

  const action = useCallback(
    async (key: WorkflowAction, path: string, withBody: boolean) => {
      setPending(key);
      try {
        await api.post(path, withBody ? { body: {} } : undefined);
        refreshViews();
        await poll();
      } finally {
        setPending(null);
      }
    },
    [refreshViews, poll],
  );

  const fetchSpots = useCallback(() => action("spots", "/fetch/spots", true), [action]);
  const fetchOptions = useCallback(() => action("options", "/fetch/options", true), [action]);
  const calibrate = useCallback(() => action("calibrate", "/calibrate", false), [action]);

  return { calib, sched, pending, busy: pending !== null, fetchSpots, fetchOptions, calibrate };
}
