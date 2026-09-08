// Fetches the Local Vol lens's Compare tab payload (LV Dupire-twin arc, D3):
//
//   POST /fit/affine/{ticker}/compare  body { fitMode, tInterp, tails: "model" }
//
// The backend (volfit.api.lv_compare) reads the parametric surface's Dupire
// twin off the affine vertex lattice, marches it through the LV fit's own
// operator and scores it beside the displayed LV sheet — a read-only view,
// never a fit (the twin is a reference like the eSSVI row). Only the active
// sub-tab's hook runs (`enabled`).
//
// Two kinds of change drive it, and they must not behave alike (the first
// live use on a streaming feed showed why — 2026-09-08):
//
//   HARD  the ticker, the fit mode, the interpolation chip, the tab opening:
//         abort whatever is in flight and fetch now; the previous payload
//         stays on screen dimmed (`refreshing`) until the new one lands.
//   SOFT  the session's view version (`reloadKey`): a live feed bumps it on
//         every real spot tick — up to once a second — while a twin build
//         takes ~0.3 s. Aborting the build on each bump starved it forever
//         (the sheets sat dimmed, "recalculating", and never updated). A
//         soft bump therefore NEVER aborts: a build in flight is left to
//         land, further bumps coalesce into ONE trailing refetch, a landed
//         build is not repeated within SOFT_REFRESH_MIN_MS, the refetch is
//         silent (`updating`, no dimming), a failed one keeps the sheets, and
//         a byte-identical payload keeps the same object — no repaint.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { QuoteBand, SmilePoint } from "./useAffine";

/** Minimum gap between two SILENT refreshes of the twin (spot ticks). */
export const SOFT_REFRESH_MIN_MS = 2000;

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
  /** The affine sheet's own reconstruction at the anchor spot; empty without an LV fit. */
  affine?: SmilePoint[];
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
  /** Per-cell diagonal of the lattice's Delaunay triangulation (the twin's
   *  own = the affine sheet's on the same vertices); the 3D meshes draw the
   *  pricing triangulation. Absent on older payloads. */
  cellDiagMain?: boolean[][];
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
  /** The ticker's active spot shift; the comparison is built AT THE ANCHOR
   *  whatever the shift (the twin is not transported), so a non-zero value
   *  is flagged. Absent on older payloads. */
  spotShift?: number;
  smiles: LvCompareSmile[];
  skippedExpiries?: string[];
  twinScore: LvCompareScore;
  parametricScore: LvCompareScore;
  affineScore?: LvCompareScore | null;
  roundTripBp: number;
  roundTripMaxBp: number;
  message: string;
}

/** The payload without its read-time fields (spot shift, message) — the
 *  identity of the anchored record. */
function stableJson(res: LvCompareResponse): string {
  const { spotShift: _shift, message: _message, ...record } = res;
  return JSON.stringify(record);
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
  /** A HARD refetch with the previous payload still shown (dimmed). */
  refreshing: boolean;
  /** A SOFT (silent) refetch in flight — a spinner, never a dimming. */
  updating: boolean;
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
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasDataRef = useRef(false);
  const jsonRef = useRef("");
  const inflight = useRef<AbortController | null>(null);
  const pending = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const lastLanded = useRef(0);
  const justHard = useRef(false);
  const args = useRef({ ticker, fitMode, tInterp });
  args.current = { ticker, fitMode, tInterp };
  const hardKey = enabled && ticker !== "" ? `${ticker}|${fitMode}|${tInterp}` : "";

  // The runner: the latest closure lives in a ref so a trailing refetch
  // scheduled from a landed promise always reads the current arguments.
  const fns = useRef({
    start: (_soft: boolean) => {},
    schedule: (_soft: boolean) => {},
  });
  fns.current.schedule = (soft: boolean) => {
    window.clearTimeout(timer.current);
    const wait = soft ? Math.max(0, SOFT_REFRESH_MIN_MS - (Date.now() - lastLanded.current)) : 0;
    if (wait > 0) timer.current = window.setTimeout(() => fns.current.start(soft), wait);
    else fns.current.start(soft);
  };
  fns.current.start = (soft: boolean) => {
    const { ticker: tk, fitMode: fm, tInterp: ti } = args.current;
    const controller = new AbortController();
    inflight.current = controller;
    if (soft) setUpdating(true);
    else {
      setLoading(true);
      setError(null);
    }
    const settle = () => {
      inflight.current = null;
      lastLanded.current = Date.now();
      setLoading(false);
      setUpdating(false);
      if (pending.current) {
        pending.current = false;
        fns.current.schedule(true);
      }
    };
    api
      .post<LvCompareResponse>(`/fit/affine/${tk}/compare`, {
        body: { fitMode: fm, tInterp: ti, tails: "model" },
        signal: controller.signal,
        timeoutMs: 300_000,
      })
      .then((res) => {
        if (controller.signal.aborted) return;
        // Identity modulo the READ-time fields (the spot shift and its message
        // suffix change on every tick while the anchored record does not): an
        // unchanged record keeps its object; only those two fields are patched
        // onto it, so every heavy array keeps its identity and nothing repaints.
        const json = stableJson(res);
        if (json !== jsonRef.current) {
          jsonRef.current = json;
          setData(res);
        } else {
          setData((cur) =>
            cur !== null && (cur.spotShift !== res.spotShift || cur.message !== res.message)
              ? { ...cur, spotShift: res.spotShift, message: res.message }
              : cur,
          );
        }
        hasDataRef.current = true;
        setError(null);
        settle();
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        // A failed SILENT refresh keeps the sheets on screen (the next tick
        // retries); a hard one, or the first, surfaces the error.
        if (!soft || !hasDataRef.current) {
          hasDataRef.current = false;
          jsonRef.current = "";
          setData(null);
          setError(messageOf(err));
        }
        settle();
      });
  };

  // HARD changes: abort, drop any trailing refetch, fetch now.
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    pending.current = false;
    if (inflight.current !== null) {
      inflight.current.abort();
      inflight.current = null;
    }
    setLoading(false);
    setUpdating(false);
    justHard.current = true;
    if (hardKey === "") return;
    fns.current.start(false);
  }, [hardKey]);

  // SOFT changes: coalesce onto the build in flight, else a throttled silent refetch.
  useEffect(() => {
    if (justHard.current) {
      justHard.current = false; // the hard effect of this very commit already fetched
      return;
    }
    if (hardKey === "") return;
    if (inflight.current !== null) {
      pending.current = true;
      return;
    }
    fns.current.schedule(true);
    // reloadKey alone is the soft key by design (the hard key has its own effect).
  }, [reloadKey]);

  // Unmount: nothing may land into a gone component.
  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
      inflight.current?.abort();
      inflight.current = null;
    },
    [],
  );

  return {
    data,
    loading: loading && !hasDataRef.current,
    refreshing: loading && hasDataRef.current,
    updating,
    error,
  };
}
