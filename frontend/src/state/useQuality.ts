// Data hook for the Quality dashboard (GET /quality): a pure cached-state
// read on the backend (never triggers a fit), refetched whenever the shared
// view-version advances (calibration epoch / spot version — the same signal
// every other view refreshes on).
import { useEffect, useState } from "react";
import { api } from "./api";
import { useSmileSession } from "./smileSession";

export interface QualityNode {
  ticker: string;
  expiry: string;
  tau: number;
  hasFit: boolean;
  stale: boolean;
  model: string;
  nQuotes: number;
  rmsBp: number;
  maxIvBp: number;
  atmVol: number;
  skew: number;
  leeLeft: number;
  leeRight: number;
  leeOk: boolean;
  calendarViolation: number;
  calendarOk: boolean;
  /** Extrapolated-region arb (advisory measurement, Notes 09/10 Phase 1). */
  extrapMinG: number | null;
  extrapOk: boolean;
  extrapCalBp: number | null;
  extrapCalOk: boolean;
  wingOrderOk: boolean | null;
  varSwapQuoted: boolean;
  filterActive: boolean;
  filterContaminated: boolean;
  /** Loaded live-chain age, minutes (null: historical / synthetic / unfetched).
   *  Red-stale data (past the Options threshold) fails readiness. */
  dataAgeMin: number | null;
  ready: boolean;
  issues: string[];
}

export interface LvQuality {
  hasFit: boolean;
  stale: boolean;
  rmsIvErrorBp: number;
  maxIvErrorBp: number;
  surfaceRmsBp: number;
  arbitrageFree: boolean;
  calendarViolations: number;
  worstMinDensity: number;
}

export interface QualityTicker {
  ticker: string;
  nodes: number;
  fitted: number;
  stale: number;
  surfaceRmsBp: number;
  worstNodeRmsBp: number;
  arbFlags: number;
  /** Loaded live-chain age in minutes (null: historical / synthetic / unfetched). */
  dataAgeMin: number | null;
  ready: number;
  lv: LvQuality | null;
}

export interface QualitySummary {
  tickers: number;
  litNodes: number;
  darkNodes: number;
  fitted: number;
  stale: number;
  noFit: number;
  readyNodes: number;
  arbFlags: number;
  medianRmsBp: number;
  worstRmsBp: number;
  filterMode: string;
  priorMode: string;
  lvTickers: number;
  lvArbFree: number;
  /** Tickers whose loaded live chain is red-stale (fails readiness). */
  staleDataTickers: number;
}

export interface QualityReport {
  fitMode: string;
  rmsBudgetBp: number;
  summary: QualitySummary;
  tickers: QualityTicker[];
  nodes: QualityNode[];
}

/** Human-readable message from an unknown thrown value. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export interface UseQualityResult {
  report: QualityReport | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useQuality(): UseQualityResult {
  const { spotVersion } = useSmileSession();
  const [report, setReport] = useState<QualityReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .get<QualityReport>("/quality", { signal: controller.signal })
      .then((r) => {
        setReport(r);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(messageOf(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [spotVersion, attempt]);

  return {
    report,
    loading,
    error,
    reload: () => setAttempt((n) => n + 1),
  };
}
