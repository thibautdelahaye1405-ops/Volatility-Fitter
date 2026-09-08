// Fetches the Local Vol lens's Compare tab payload (LV Dupire-twin arc, D3):
//
//   POST /fit/affine/{ticker}/compare  body { fitMode, tInterp, tails: "model" }
//
// The backend (volfit.api.lv_compare) reads the parametric surface's Dupire
// twin off the affine vertex lattice, marches it through the LV fit's own
// operator and scores it beside the displayed LV sheet — a read-only view,
// never a fit (the twin is a reference like the eSSVI row). Only the active
// sub-tab's hook runs (`enabled`); a chip change refetches with the previous
// payload kept on screen dimmed (`refreshing`), like the surface fit. The
// build is value-only (~0.3 s uncached, cached server-side thereafter) but
// the LV bootstrap it may trigger on a never-calibrated ticker is not, hence
// the surface fit's own 300 s timeout.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { QuoteBand, SmilePoint } from "./useAffine";

/** The t-interpolation chip: monotone PCHIP in τ vs the market's staircase. */
export type LvTInterp = "smooth" | "buckets";

/** One surface's fit-target score (one expiry, or pooled). `rmsError` is the
 *  weighted RMS vol error in DECIMAL vol (the AffineSmile.rmsError basis);
 *  `rmsBp` / `maxBp` the plain per-quote |model − target| residuals in bp on
 *  the surface's own operator (null where the payload has none: the affine
 *  rows); `convergedBp` the same RMS on the converged operator (null for the
 *  parametric closed form). */
export interface LvCompareScore {
  rmsError: number;
  maxBp: number;
  rmsBp?: number | null;
  convergedBp?: number | null;
}

/** Per-t-vertex repair counts of the twin extraction (one entry per tNodes
 *  row): butterfly = Dupire denominator ≤ 0 (strike arbitrage in the implied
 *  surface), calendar = w_τ ≤ 0, floored / capped = clipped into the box. */
export interface LvCompareCounters {
  butterfly: number[];
  calendar: number[];
  floored: number[];
  capped: number[];
  clean: boolean;
}

/** One expiry of the Compare tab: the twin's reconstruction, the parametric
 *  source on the same core grid, the quotes, the three scores and the round
 *  trip (twin repriced back against its own parametric source, bp). */
export interface LvCompareSmile {
  expiry: string;
  t: number;
  tau: number;
  forward: number;
  twin: SmilePoint[];
  twinExt?: SmilePoint[];
  parametric: SmilePoint[];
  quotes: QuoteBand[];
  twinScore: LvCompareScore;
  parametricScore: LvCompareScore;
  affineScore?: LvCompareScore | null;
  roundTripBp: number;
  roundTripMaxBp: number;
  roundTripInOpBp: number;
}

/** Response of POST /fit/affine/{ticker}/compare (mirrors LvCompareResponse). */
export interface LvCompareResponse {
  ticker: string;
  tInterp: LvTInterp;
  tails: string;
  tNodes: number[];
  xNodes: number[];
  /** sqrt of the twin's nodal variance inside the box, one row per t-node. */
  localVolTwin: number[][];
  /** Unrepaired Gatheral local VARIANCE: null where the denominator failed or
   *  the vertex was not differentiated, negative where w_τ < 0. */
  rawLocalVariance: (number | null)[][];
  differentiated: boolean[];
  counters: LvCompareCounters;
  varLo: number;
  varHi: number;
  /** The displayed LV sheet and the signed difference twin − affine (vol),
   *  present only on the matching lattice (`affineLatticeMatches`). */
  localVolAffine?: number[][];
  diffLocalVol?: number[][];
  hasAffine: boolean;
  affineStale: boolean;
  affineLatticeMatches: boolean;
  smiles: LvCompareSmile[];
  skippedExpiries?: string[];
  twinScore: LvCompareScore;
  parametricScore: LvCompareScore;
  affineScore?: LvCompareScore | null;
  roundTripBp: number;
  roundTripMaxBp: number;
  message: string;
}

/** Human-readable message from a thrown value (FastAPI `detail` when present). */
function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(err.body);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        typeof (parsed as { detail?: unknown }).detail === "string"
      ) {
        return (parsed as { detail: string }).detail;
      }
    } catch {
      /* non-JSON body: fall through */
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export interface UseLvCompareResult {
  data: LvCompareResponse | null;
  /** First load (nothing on screen yet). */
  loading: boolean;
  /** A refetch with the previous payload still shown (dimmed). */
  refreshing: boolean;
  error: string | null;
}

export function useLvCompare(
  ticker: string,
  enabled: boolean,
  reloadKey: number = 0,
  fitMode: string = "mid",
  tInterp: LvTInterp = "smooth",
): UseLvCompareResult {
  const [data, setData] = useState<LvCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasDataRef = useRef(false);

  useEffect(() => {
    if (!enabled || ticker === "") return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .post<LvCompareResponse>(`/fit/affine/${ticker}/compare`, {
        body: { fitMode, tInterp, tails: "model" },
        signal: controller.signal,
        timeoutMs: 300_000,
      })
      .then((res) => {
        setData(res);
        hasDataRef.current = true;
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setData(null);
        hasDataRef.current = false;
        setError(messageOf(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [ticker, enabled, reloadKey, fitMode, tInterp]);

  return {
    data,
    loading: loading && !hasDataRef.current,
    refreshing: loading && hasDataRef.current,
    error,
  };
}
