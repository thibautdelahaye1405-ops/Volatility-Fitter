// Data hook for the Prior Evidence tab (V3.9 item 8): four read-only,
// poll-safe backend reads bundled into one payload —
//
//   GET /priors                    → the ticker's saved/active prior status + ages
//   GET /priors/history/{ticker}   → saved-snapshot history metadata (newest first)
//   GET /graph/innovations/{ticker}→ the persisted per-(day, expiry) ATM innovations
//   GET /graph/config/messages     → the ACTIVE layered policy's residualHalfLifeDays
//                                    (the H of the GRAPH residual decay curve)
//
// None of these trigger a fit or a solve. In mock mode (or when the primary
// status read fails while offline) the tab renders the deterministic
// getMockPriorEvidence bundle so it works standalone — the useWeights idiom.
import { useEffect, useState } from "react";
import { api } from "./api";
import { DEFAULT_POLICY, fetchMessageConfig } from "./useMessageConfig";
import { getMockPriorEvidence } from "../lib/mockData";
import type {
  InnovationPoint,
  PriorEvidenceStatus,
  PriorHistoryEntry,
} from "../lib/priorEvidence";

export interface PriorEvidenceData {
  status: PriorEvidenceStatus | null;
  history: PriorHistoryEntry[];
  innovations: InnovationPoint[];
  /** Active layered-policy residual half-life H, days (null = fully
   *  persistent / random walk — the schema default). */
  residualHalfLifeDays: number | null;
  /** True when the mock fallback is showing (backend off / fetch failed). */
  mock: boolean;
}

interface PriorStatusResponse {
  tickers: PriorEvidenceStatus[];
}
interface PriorHistoryResponse {
  ticker: string;
  entries: PriorHistoryEntry[];
}
interface InnovationSeriesResponse {
  ticker: string;
  series: InnovationPoint[];
}

function mockBundle(): PriorEvidenceData {
  const m = getMockPriorEvidence();
  return {
    status: m.status,
    history: m.history,
    innovations: m.innovations,
    residualHalfLifeDays: m.residualHalfLifeDays,
    mock: true,
  };
}

export interface UsePriorEvidenceResult {
  data: PriorEvidenceData | null;
  loading: boolean;
  reload: () => void;
}

export function usePriorEvidence(
  live: boolean,
  ticker: string,
  refreshKey: unknown,
): UsePriorEvidenceResult {
  const [data, setData] = useState<PriorEvidenceData | null>(null);
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!live || ticker === "") {
      setData(mockBundle());
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const signal = controller.signal;
    // The status read is the primary: its failure means "backend gone" and the
    // whole bundle falls back to mock. The three secondary reads degrade
    // individually (an empty history / series is a real, honest state).
    const primary = api
      .get<PriorStatusResponse>("/priors", { signal })
      .then((r) => r.tickers.find((t) => t.ticker === ticker) ?? null);
    const secondary = Promise.all([
      api
        .get<PriorHistoryResponse>(`/priors/history/${ticker}`, { signal })
        .then((r) => r.entries)
        .catch(() => [] as PriorHistoryEntry[]),
      api
        .get<InnovationSeriesResponse>(`/graph/innovations/${ticker}`, { signal })
        .then((r) => r.series)
        .catch(() => [] as InnovationPoint[]),
      fetchMessageConfig()
        .then(
          (pair) =>
            pair.active?.policy?.residualHalfLifeDays ??
            DEFAULT_POLICY.residualHalfLifeDays,
        )
        .catch(() => DEFAULT_POLICY.residualHalfLifeDays),
    ]);
    Promise.all([primary, secondary])
      .then(([status, [history, innovations, residualHalfLifeDays]]) => {
        setData({ status, history, innovations, residualHalfLifeDays, mock: false });
      })
      .catch(() => {
        if (!signal.aborted) setData(mockBundle());
      })
      .finally(() => {
        if (!signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [live, ticker, refreshKey, attempt]);

  return { data, loading, reload: () => setAttempt((n) => n + 1) };
}
