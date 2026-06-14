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
  t: number;
  model: SmilePoint[];
  quotes: QuoteBand[];
  maxIvErrorBp: number;
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
  minDensity: number[];
  calendarViolations: number;
  arbitrageFree: boolean;
  nEvals: number;
  message: string;
}

/** View-local vertex-grid + regularization controls (mirror AffineFitRequest). */
export interface AffineParams {
  nXNodes: number;
  nTNodes: number;
  regLambda: number;
  varLo: number;
  varHi: number;
}

export const DEFAULT_PARAMS: AffineParams = {
  nXNodes: 7,
  nTNodes: 4,
  regLambda: 1e-2,
  varLo: 0.0025,
  varHi: 0.36,
};

/** Collapse rapid control edits into one refit per pause. */
const PARAM_DEBOUNCE_MS = 350;

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
  params: AffineParams;
  setParams: (patch: Partial<AffineParams>) => void;
}

export function useAffine(): UseAffineResult {
  const { universe, ticker, setTicker } = useSmileSession();

  const [data, setData] = useState<AffineFitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const [params, setParamsState] = useState<AffineParams>(DEFAULT_PARAMS);
  const setParams = useCallback(
    (patch: Partial<AffineParams>) => setParamsState((p) => ({ ...p, ...patch })),
    [],
  );

  // Seed the vertex grid + roughness from the Options defaults once, but only
  // while the controls are still untouched (equal to DEFAULT_PARAMS), so a user
  // edit is never clobbered by a late-arriving seed (ROADMAP Phase 10).
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current) return;
    const controller = new AbortController();
    api
      .get<{ gridXNodes: number; gridTNodes: number; gridRegLambda: number }>(
        "/settings/options",
        { signal: controller.signal },
      )
      .then((o) => {
        seededRef.current = true;
        setParamsState((p) =>
          p.nXNodes === DEFAULT_PARAMS.nXNodes &&
          p.nTNodes === DEFAULT_PARAMS.nTNodes &&
          p.regLambda === DEFAULT_PARAMS.regLambda
            ? { ...p, nXNodes: o.gridXNodes, nTNodes: o.gridTNodes, regLambda: o.gridRegLambda }
            : p,
        );
      })
      .catch(() => {
        seededRef.current = true; // offline / mock: keep DEFAULT_PARAMS
      });
    return () => controller.abort();
  }, []);

  const hasDataRef = useRef(false);

  // Debounce the params so slider drags collapse into one refit.
  const [debounced, setDebounced] = useState<AffineParams>(params);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(params), PARAM_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [params]);

  useEffect(() => {
    if (ticker === "") return; // session universe still loading
    const controller = new AbortController();
    if (hasDataRef.current) setRefreshing(true);
    else setLoading(true);
    setError(null);
    api
      .post<AffineFitResponse>(`/fit/affine/${ticker}`, {
        body: { fitMode: "mid", ...debounced },
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
  }, [ticker, debounced, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return {
    data,
    loading,
    refreshing,
    error,
    reload,
    ticker,
    setTicker,
    tickers: universe?.tickers ?? [],
    params,
    setParams,
  };
}
