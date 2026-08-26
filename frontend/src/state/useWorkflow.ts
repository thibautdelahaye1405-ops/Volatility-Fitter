// Calibration / data-fetch workflow state for the TopBar controls.
//
// Polls the backend trigger model (GET /calibration/status + /scheduler) for the
// background-calibration progress, the lit/stale node counts and the auto-fetch
// countdowns, and exposes the manual actions (Fetch spots / Fetch Options /
// Calibrate). When a background calibration finishes, or the backend scheduler
// transports the surface (real-time spot), it bumps the session's view version
// so every workspace re-pulls the refreshed views. Live backend only.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE_URL } from "./api";
import { DONE_LABEL, FAIL_LABEL } from "./workflowTypes";
import type {
  CalibrationStatus,
  LastAction,
  PriorFetchResult,
  PriorSaveResult,
  PriorStatus,
  SchedulerStatus,
  WorkflowAction,
} from "./workflowTypes";

export type {
  ActivityInfo,
  CalibrationStatus,
  LastAction,
  PriorFetchResult,
  PriorSaveResult,
  PriorStatus,
  PriorTickerStatus,
  SchedulerStatus,
  WorkflowAction,
} from "./workflowTypes";

/** Status poll cadence (ms): a brisk cadence while the engine is active (so the
 *  status-bar narration keeps up with what it's doing) and a relaxed one when
 *  idle (just the auto-fetch countdown / stale accounting). */
const POLL_ACTIVE_MS = 500;
const POLL_IDLE_MS = 3000;
/** When the tab is hidden the user can't see any status, so we all but stop
 *  polling (a slow heartbeat keeps the connection warm); becoming visible again
 *  triggers an immediate poll via the visibilitychange listener below. */
const POLL_HIDDEN_MS = 15000;
/** Cadence while the SSE stream is connected: the stream pushes the status
 *  (epoch/spot/activity → view refetches), so the timer only refreshes the
 *  scheduler countdowns and acts as a backstop. (ROADMAP perf #4.) */
const POLL_SSE_MS = 5000;

export interface UseWorkflowResult {
  calib: CalibrationStatus | null;
  sched: SchedulerStatus | null;
  /** The in-flight manual action, or null. (`busy` = pending !== null.) */
  pending: WorkflowAction | null;
  busy: boolean;
  /** Last completed action (explicit verb, or a background refit landing). */
  lastAction: LastAction | null;
  fetchSpots: () => Promise<void>;
  fetchOptions: () => Promise<void>;
  /** POST /fetch/snapshot — the unified verb (V3.7 item 15): chains + spot
   *  transport + (when the Options toggle enables it) the cheap prior roll,
   *  then auto-calibrate. May start a calibration, so it awaits the job. */
  fetchSnapshot: () => Promise<void>;
  /** POST /calibrate — the combined verb (parametric, then LV when the Options
   *  toggle enables it); wire behavior unchanged (V3.5 item 9). */
  calibrate: () => Promise<void>;
  /** POST /calibrate/parametric — parametric slices only (the fast loop);
   *  LV surfaces go/stay stale (lvStaleTickers). */
  calibrateParametric: () => Promise<void>;
  /** POST /calibrate/lv — LV (affine) surfaces only, no parametric barrier;
   *  runs regardless of the Options toggle. */
  calibrateLv: () => Promise<void>;
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

export function useWorkflow(
  live: boolean,
  refreshViews: () => void,
  fitMode: string,
): UseWorkflowResult {
  const [calib, setCalib] = useState<CalibrationStatus | null>(null);
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [priors, setPriors] = useState<PriorStatus | null>(null);
  const [lastAction, setLastAction] = useState<LastAction | null>(null);
  // Mirror of `pending` readable inside the status callback (no re-subscribe).
  const pendingRef = useRef<WorkflowAction | null>(null);
  const noteAction = useCallback((label: string, ok = true) => {
    setLastAction({ label, at: Date.now(), ok });
  }, []);
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

  // Apply a status snapshot (from the SSE push OR the fallback poll). Level-
  // triggered + idempotent: whichever source observes a counter advance first
  // refetches the views; the other no-ops (refs already updated). null baselines
  // on the first observation so it never spuriously refetches on connect.
  const applyStatus = useCallback(
    (c: CalibrationStatus) => {
      setCalib(c);
      activeRef.current = c.running || c.activity.active;
      // A (re)calibration changed a displayed fit somewhere — refetch all mounted
      // views (covers the explicit Calibrate button, auto-calibrate on fetch, the
      // streaming refit, and progressive per-node commits during a running job).
      if (lastEpoch.current !== null && c.epoch !== lastEpoch.current) {
        refreshViews();
        // A background / scheduler refit landed with no explicit verb in flight
        // (auto-calibrate on fetch, streaming refit): still worth a timestamp.
        if (pendingRef.current === null) {
          noteAction(c.error ? `Calibration error: ${c.error}` : "Refit landed", !c.error);
        }
      }
      lastEpoch.current = c.epoch;
      // Pure spot transport (no recalibration) — the backend scheduler moved the
      // surface under real-time spot; refetch so the transported curves follow.
      if (lastSpotVer.current !== null && c.spotVersion !== lastSpotVer.current) refreshViews();
      lastSpotVer.current = c.spotVersion;
    },
    [refreshViews, noteAction],
  );

  const pollScheduler = useCallback(async () => {
    try {
      setSched(await api.get<SchedulerStatus>("/scheduler"));
    } catch {
      /* backend unreachable: leave the last status */
    }
  }, []);

  // Full poll (status + scheduler) — the fallback when the SSE stream is down,
  // and the resync the explicit-action path awaits.
  const poll = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        // Pass the viewed fit target so the stale accounting reports the SAME
        // per-mode pointer the smile is shown in (mid vs bid-ask vs haircut).
        api.get<CalibrationStatus>("/calibration/status", { params: { fit_mode: fitMode } }),
        api.get<SchedulerStatus>("/scheduler"),
      ]);
      setSched(s);
      applyStatus(c);
    } catch {
      /* backend unreachable: leave the last status */
    }
  }, [applyStatus, fitMode]);

  useEffect(() => {
    if (!live) return;
    let timer = 0;
    let stopped = false;
    let es: EventSource | null = null;
    const sseOk = { current: false };
    const hidden = () => typeof document !== "undefined" && document.hidden;

    // SSE push of the calibration status (ROADMAP perf #4): one connection
    // replaces the 500ms status poll + N-view refetch fan-out. The poll stays as
    // a fallback (relaxed while the stream is healthy), so an absent / dropped
    // stream degrades to exactly the previous polling behaviour — never freezes.
    const closeSse = () => {
      if (es) es.close();
      es = null;
      sseOk.current = false;
    };
    const openSse = () => {
      if (es || typeof EventSource === "undefined") return;
      const url = new URL("/calibration/stream", API_BASE_URL);
      url.searchParams.set("fit_mode", fitMode);
      const src = new EventSource(url);
      src.onopen = () => (sseOk.current = true);
      src.onmessage = (e) => {
        try {
          applyStatus(JSON.parse(e.data) as CalibrationStatus);
        } catch {
          /* ignore a malformed frame; the next one / the poll backstop recovers */
        }
      };
      // EventSource auto-reconnects; flip the flag so the timer speeds back up to
      // the full poll until the stream is healthy again.
      src.onerror = () => (sseOk.current = false);
      es = src;
    };

    const nextDelay = () =>
      hidden()
        ? POLL_HIDDEN_MS
        : sseOk.current
          ? POLL_SSE_MS
          : activeRef.current
            ? POLL_ACTIVE_MS
            : POLL_IDLE_MS;
    // Self-rescheduling loop: while the SSE stream is healthy it only refreshes
    // the scheduler countdowns (the stream pushes the status); otherwise it does
    // the full status+scheduler poll, brisk while the engine works.
    const tick = async () => {
      if (!hidden()) await (sseOk.current ? pollScheduler() : poll());
      if (stopped) return;
      timer = window.setTimeout(() => void tick(), nextDelay());
    };
    // Hidden tab: drop the stream (no refetches for a UI nobody sees). Visible
    // again: reopen the stream + poll right away so the status is fresh.
    const onVisible = () => {
      if (stopped) return;
      if (hidden()) {
        closeSse();
      } else {
        openSse();
        window.clearTimeout(timer);
        void tick();
      }
    };

    if (!hidden()) openSse();
    void tick();
    void refreshPriors(); // saved-prior availability (not in the hot poll loop)
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      closeSse();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [live, poll, pollScheduler, applyStatus, refreshPriors, fitMode]);

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
      pendingRef.current = key;
      try {
        // fit_mode targets the mode the smile is VIEWED in, so Calibrate / the
        // auto-fetch re-point the same per-mode calibrated pointer (otherwise a
        // bid-ask / haircut smile stays frozen because only "mid" was calibrated).
        // Chain fetches / calibration kicks can legitimately run for minutes
        // on a large universe; the status poll below is the responsive layer.
        await api.post(path, {
          params: { fit_mode: fitMode },
          timeoutMs: 600_000,
          ...(withBody ? { body: {} } : {}),
        });
        if (awaitJob) await awaitCalibration(); // block until the fit completes
        await poll(); // resync status + advance the epoch/spot baselines
        refreshViews(); // refetch every view against the now-current fit
        noteAction(DONE_LABEL[key]);
      } catch (err: unknown) {
        // Recorded (status bar) rather than thrown: callers fire-and-forget.
        noteAction(`${FAIL_LABEL[key]}: ${messageOf(err)}`, false);
      } finally {
        pendingRef.current = null;
        setPending(null);
      }
    },
    [refreshViews, poll, awaitCalibration, fitMode, noteAction],
  );

  // calibrate + fetchOptions start a background calibration job, so they await its
  // completion before refreshing; fetchSpots is pure transport (nothing to await).
  const fetchSpots = useCallback(() => action("spots", "/fetch/spots", true), [action]);
  const fetchOptions = useCallback(() => action("options", "/fetch/options", true, true), [action]);
  // Unified fetch (V3.7 item 15): quotes + spot in one pull; awaitJob because it
  // may kick a background calibration (autoCalibrate), exactly like fetchOptions.
  const fetchSnapshot = useCallback(
    () => action("fetchSnapshot", "/fetch/snapshot", true, true),
    [action],
  );
  const calibrate = useCallback(() => action("calibrate", "/calibrate", false, true), [action]);
  // Stage-split verbs (V3.5 item 9): same background-job semantics as /calibrate
  // (one job at a time; a running job makes them a no-op server-side).
  const calibrateParametric = useCallback(
    () => action("calibrateParametric", "/calibrate/parametric", false, true),
    [action],
  );
  const calibrateLv = useCallback(
    () => action("calibrateLv", "/calibrate/lv", false, true),
    [action],
  );

  const savePriors = useCallback(async () => {
    setPending("savePriors");
    pendingRef.current = "savePriors";
    try {
      const res = await api.post<PriorSaveResult>("/priors/save-all", { timeoutMs: 300_000 });
      await refreshPriors();
      noteAction(`Saved priors (${res.nodes} node${res.nodes === 1 ? "" : "s"})`);
      return res;
    } catch (err: unknown) {
      noteAction(`Failed to save priors: ${messageOf(err)}`, false);
      return undefined;
    } finally {
      pendingRef.current = null;
      setPending(null);
    }
  }, [refreshPriors, noteAction]);

  const fetchPriors = useCallback(async () => {
    setPending("fetchPriors");
    pendingRef.current = "fetchPriors";
    try {
      const res = await api.post<PriorFetchResult>("/priors/fetch", { timeoutMs: 300_000 });
      await refreshPriors();
      refreshViews(); // the dotted, spot-updated prior overlays change on every view
      const active = res.tickers.filter((t) => t.source !== "none").length;
      noteAction(`Fetched priors (${active} active)`);
      return res;
    } catch (err: unknown) {
      noteAction(`Failed to fetch priors: ${messageOf(err)}`, false);
      return undefined;
    } finally {
      pendingRef.current = null;
      setPending(null);
    }
  }, [refreshPriors, refreshViews, noteAction]);

  return {
    calib, sched, pending, busy: pending !== null, lastAction,
    fetchSpots, fetchOptions, fetchSnapshot, calibrate, calibrateParametric, calibrateLv,
    priors, savePriors, fetchPriors,
  };
}

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
