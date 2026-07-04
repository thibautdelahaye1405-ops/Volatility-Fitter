// Fetches one node's observation-Kalman-filter diagnostics for the live
// overlay (GET /smiles/{ticker}/{expiry}/filter, Note 15 Phase 4). Advisory:
// the filtered handle posterior + credible band + one-step prediction curve,
// with per-handle gains / innovations for the badge and the Options table.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { SmilePoint } from "../lib/mockData";

/** GET /smiles/{ticker}/{expiry}/filter response (backend FilterDiagnostics).
 *  Per-handle arrays are ordered like `handleNames` (ATM, skew, curvature). */
export interface FilterDiagnostics {
  /** False when the filter is off or its state is unseeded — render nothing. */
  active: boolean;
  mode: "off" | "overlay" | "active";
  handleNames: string[];
  provenance: string | null;
  resetReason: string | null;
  /** The measurement failed the contamination gate (trust it less). */
  contaminated: boolean;
  transportDistance: number | null;
  prediction: number[];
  predictionStd: number[];
  observation: number[];
  observationStd: number[];
  innovation: number[];
  gain: number[];
  posterior: number[];
  posteriorStd: number[];
  measurementBreakdown: Record<string, number>;
  processBreakdown: Record<string, number[]>;
  /** Filtered-posterior smile + its ±1σ band + the pre-update prediction. */
  post: SmilePoint[];
  postBandLo: SmilePoint[];
  postBandHi: SmilePoint[];
  predCurve: SmilePoint[];
}

interface UseObservationFilterResult {
  data: FilterDiagnostics | null;
  loading: boolean;
}

/** Fetch the filter diagnostics for (ticker, expiry) when `enabled`; refetches
 *  on any param change (bump `refreshKey` after calibrations). Returns null
 *  while disabled, before the first response, or when the filter is inactive. */
export function useObservationFilter(
  enabled: boolean,
  ticker: string,
  expiry: string,
  fitMode: string,
  refreshKey: number,
): UseObservationFilterResult {
  const [data, setData] = useState<FilterDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled || ticker === "" || expiry === "") {
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<FilterDiagnostics>(
        `/smiles/${ticker}/${encodeURIComponent(expiry)}/filter`,
        { params: { fit_mode: fitMode }, signal: controller.signal },
      )
      .then((res) => {
        setData(res.active ? res : null); // off / unseeded -> no overlay
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setData(null);
        setLoading(false);
      });
    return () => controller.abort();
  }, [enabled, ticker, expiry, fitMode, refreshKey]);

  return { data, loading };
}
