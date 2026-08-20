// Fetches the LV calibration replay trace (V3.5 item 13).
//
// GET /fit/affine/{ticker}/trace serves the accepted-step checkpoints the last
// TRACED affine fit recorded (a read-only side channel — polling it can never
// trigger a fit). Keyed on the affine fit epoch the caller derives from its
// payload: a fresh calibration bumps the epoch, this hook refetches, and the
// player auto-replays once. 404 (no traced fit yet) and the mock/offline
// session both degrade to `null` — the player then simply shows nothing.
import { useEffect, useState } from "react";
import { api } from "./api";

/** One accepted-step checkpoint (mirrors the backend AffineTraceFrameOut). */
export interface LvTraceFrame {
  /** Objective evaluations spent when this iterate was accepted. */
  nEvals: number;
  /** Total LSQ cost ½‖r‖² at the iterate. */
  cost: number;
  /** sqrt(nodal variance) grid — same shape as AffineFitResponse.localVol. */
  localVol: number[][];
  /** Per-expiry option-residual RMS (one entry per `expiries` column). */
  expiryRms: number[];
}

/** Response of GET /fit/affine/{ticker}/trace. */
export interface LvTraceResponse {
  ticker: string;
  tNodes: number[];
  xNodes: number[];
  /** Tau per expiryRms column (the real fitted expiries, ascending). */
  expiries: number[];
  /** Ascending nEvals; the LAST frame equals the served (converged) surface. */
  frames: LvTraceFrame[];
}

export function useLvTrace(
  ticker: string,
  epoch: number,
  enabled: boolean,
): { trace: LvTraceResponse | null; loading: boolean } {
  const [trace, setTrace] = useState<LvTraceResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled || ticker === "") {
      setTrace(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<LvTraceResponse>(`/fit/affine/${ticker}/trace`, { signal: controller.signal })
      .then((t) => {
        setTrace(t);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setTrace(null); // 404 (no traced fit yet) or offline: empty fallback
        setLoading(false);
      });
    return () => controller.abort();
  }, [ticker, epoch, enabled]);

  return { trace, loading };
}
