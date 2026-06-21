// Data + interaction state for the Local Vol workspace.
//
// Talks to POST /fit/affine/{ticker}: calibrates the piecewise-affine local-
// variance surface straight to the ticker's option quotes and returns the
// nodal local-vol surface (for the heatmap), one reconstructed arbitrage-free
// smile per expiry (for charting vs quotes), and fit / no-arbitrage
// diagnostics. Distinct from GET /localvol/{ticker} (Dupire extraction from
// the LQD fit) — this is the *direct* surface calibration.
//
// The underlying selection is shared with the Smile tab through the smile
// session. Vertex-grid / regularization controls are view-local and debounced
// so dragging a slider issues one refit per pause. Live backend only (no mock
// fallback), matching the Term and Graph workspaces.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";
import type { VarSwapInfo } from "../lib/mockData";
import type { VarSwapAction } from "./useSmile";

/** One point of a reconstructed model curve. */
export interface SmilePoint {
  k: number;
  vol: number;
}

/** One market quote band at a strike (mirrors the backend QuoteBand). */
export interface QuoteBand {
  k: number;
  bid: number;
  ask: number;
  mid: number;
  index: number;
  excluded: boolean;
  amended: boolean;
}

/** One expiry's reconstructed arbitrage-free smile plus its quotes. */
export interface AffineSmile {
  expiry: string;
  /** Calendar year fraction (maturity axis). */
  t: number;
  /** Event-weighted variance years the smile is quoted in (= t with no events). */
  tau?: number;
  /** Active forward (for the strike / %ATM x-axis modes). */
  forward?: number;
  model: SmilePoint[];
  /** Active fetched prior, transported to the current forward (dotted overlay). */
  prior?: SmilePoint[];
  priorTransported?: boolean;
  quotes: QuoteBand[];
  /** Var-swap quote (shared with the Parametric workspace) + model level. */
  varSwap: VarSwapInfo;
  maxIvErrorBp: number;
  /** Weighted RMS vol error of this expiry (decimal), on the same fit-target /
   *  scheme / var-swap basis as the Parametric workspace. */
  rmsError?: number;
  /** Risk-neutral density (Breeden-Litzenberger from the Dupire PDE call
   *  prices): pdf f_X on the log-return grid x. Absent on older cached payloads. */
  density?: { x: number[]; density: number[] };
  /** Density left-extended to the display lower bound (k_min = -1.4); backs the
   *  stacked "Densities" overlay so its x-axis spans the full smile range. */
  densityExt?: { x: number[]; density: number[] };
}

/** Response of POST /fit/affine/{ticker}. */
export interface AffineFitResponse {
  ticker: string;
  tNodes: number[];
  xNodes: number[];
  /** sqrt(nodal variance): one row per t-node, one column per x-node. */
  localVol: number[][];
  smiles: AffineSmile[];
  rmsPriceError: number;
  maxPriceError: number;
  rmsIvErrorBp: number;
  maxIvErrorBp: number;
  /** Whole-surface weighted RMS vol error (decimal), same basis as the
   *  per-expiry rmsError and the Parametric workspace. */
  surfaceRmsError?: number;
  minDensity: number[];
  calendarViolations: number;
  arbitrageFree: boolean;
  nEvals: number;
  message: string;
  /** Inputs drifted since the last LV calibration — frozen until Calibrate. */
  stale?: boolean;
  /** False when the LV surface has never been calibrated (gated workflow, before
   *  the Calibrate button): all arrays empty. Optional/true for older payloads. */
  hasFit?: boolean;
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

export interface UseAffineResult {
  data: AffineFitResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  reload: () => void;
  ticker: string;
  setTicker: (ticker: string) => void;
  tickers: string[];
  /** Whether var-swap quoting is enabled (OptionsSettings.varSwapEnabled). */
  varSwapEnabled: boolean;
  /** Source the LV surface from the GRAPH-EXTRAPOLATED smiles (the affine fit is
   *  calibrated to the graph reconstruction) instead of the live quotes (plan
   *  Phase 9 / Amendment G). */
  graphSource: boolean;
  setGraphSource: (on: boolean) => void;
  /** Bumped on every var-swap edit; feed to useAffineView so the derived
   *  (density/term/table) views refetch the recalibrated surface too. */
  varSwapNonce: number;
  /** Edit one expiry's var-swap quote (shared with Parametric), then refit the
   *  surface, the derived views and the Parametric smile. */
  applyVarSwap: (expiry: string, action: VarSwapAction, level?: number) => Promise<void>;
  undoVarSwap: (expiry: string) => Promise<void>;
  redoVarSwap: (expiry: string) => Promise<void>;
}

export function useAffine(): UseAffineResult {
  const { universe, ticker, setTicker, reload: reloadSmile, spotVersion, fitMode } =
    useSmileSession();
  const [varSwapEnabled, setVarSwapEnabled] = useState(true);
  const [varSwapNonce, setVarSwapNonce] = useState(0);
  const [graphSource, setGraphSource] = useState(false);

  const [data, setData] = useState<AffineFitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // The vertex grid + roughness are global hyperparameters (Options); the fit
  // reads them on the backend. We only track varSwapEnabled for the UI here.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current) return;
    const controller = new AbortController();
    api
      .get<{ varSwapEnabled: boolean }>("/settings/options", { signal: controller.signal })
      .then((o) => {
        seededRef.current = true;
        setVarSwapEnabled(o.varSwapEnabled);
      })
      .catch(() => {
        seededRef.current = true;
      });
    return () => controller.abort();
  }, []);

  const hasDataRef = useRef(false);

  useEffect(() => {
    if (ticker === "") return; // session universe still loading
    const controller = new AbortController();
    if (hasDataRef.current) setRefreshing(true);
    else setLoading(true);
    setError(null);
    // Graph-extrapolated source projects the graph reconstruction onto an LV
    // surface (POST /graph/extrapolate/lv); else the live-quote calibration.
    const endpoint = graphSource
      ? `/graph/extrapolate/lv/${ticker}`
      : `/fit/affine/${ticker}`;
    api
      .post<AffineFitResponse>(endpoint, {
        // Viewed fit target (mid / bid-ask / haircut), matching the Parametric
        // workspace + the Calibrate target. Hardcoding "mid" showed a stale mid
        // surface (auto-fit on read) whenever the user calibrated in a band mode,
        // instead of the bid-ask/haircut surface they actually fit.
        body: { fitMode },
        signal: controller.signal,
      })
      .then((res) => {
        setData(res);
        hasDataRef.current = true;
        setLoading(false);
        setRefreshing(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setError(messageOf(err));
        setLoading(false);
        setRefreshing(false);
      });
    return () => controller.abort();
    // spotVersion bumps on a spot move / calibration / Options change -> refetch.
    // fitMode: switching the viewed fit target re-reads that mode's surface.
    // graphSource: toggling the source re-fetches from the other endpoint.
  }, [ticker, attempt, spotVersion, fitMode, graphSource]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // Var-swap quote edits (shared /varswap endpoints): after the POST, refit the
  // affine surface (attempt) + bump the nonce so the derived views refetch, and
  // refit the Parametric smile so both workspaces stay consistent.
  const postVarSwap = useCallback(
    async (expiry: string, suffix: string, body?: unknown): Promise<void> => {
      if (ticker === "" || expiry === "") return;
      try {
        await api.post(`/smiles/${ticker}/${expiry}/${suffix}`, { body });
      } catch {
        /* surfaced indirectly via the next load */
      }
      setVarSwapNonce((n) => n + 1);
      setAttempt((n) => n + 1);
      reloadSmile();
    },
    [ticker, reloadSmile],
  );

  const applyVarSwap = useCallback(
    (expiry: string, action: VarSwapAction, level?: number) =>
      postVarSwap(expiry, "varswap", { action, level }),
    [postVarSwap],
  );
  const undoVarSwap = useCallback(
    (expiry: string) => postVarSwap(expiry, "varswap/undo"),
    [postVarSwap],
  );
  const redoVarSwap = useCallback(
    (expiry: string) => postVarSwap(expiry, "varswap/redo"),
    [postVarSwap],
  );

  return {
    data,
    loading,
    refreshing,
    error,
    reload,
    ticker,
    setTicker,
    tickers: universe?.tickers ?? [],
    varSwapEnabled,
    varSwapNonce,
    graphSource,
    setGraphSource,
    applyVarSwap,
    undoVarSwap,
    redoVarSwap,
  };
}
