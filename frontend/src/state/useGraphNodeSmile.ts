// Fetches one node's reconstructed graph-extrapolated smile for the live overlay
// (GET /graph/extrapolate/nodes/{ticker}/{expiry}, plan Phase 5). The solver
// knobs ride as query params (the GET binds GraphExtrapolateRequest from query).
import { useEffect, useState } from "react";
import { api } from "./api";
import type { SmilePoint } from "../lib/mockData";

/** Quote-comparison metrics of the reconstruction vs the market. */
export interface GraphNodeMetrics {
  nQuotes: number;
  rmsVol: number;
  insideSpreadHitRate: number;
  atmResidualBp: number;
  skewResidual: number;
  curvResidual: number;
  standardizedResidual: number | null;
}

/** GET /graph/extrapolate/nodes/{ticker}/{expiry} response. */
export interface GraphNodeSmile {
  ticker: string;
  expiry: string;
  t: number;
  model: string; // the model family the smile is reconstructed in (lqd/svi/sigmoid)
  lit: boolean;
  calibrated: boolean;
  priorSource: string;
  postAtmVol: number;
  sd: number;
  post: SmilePoint[];
  postBandLo: SmilePoint[];
  postBandHi: SmilePoint[];
  prior: SmilePoint[];
  litCalibration: SmilePoint[];
  metrics: GraphNodeMetrics | null;
}

interface UseGraphNodeSmileResult {
  node: GraphNodeSmile | null;
  loading: boolean;
  error: string | null;
}

/** Fetch the reconstructed smile for (ticker, expiry) when `active`; refetches on
 *  any param change. Returns null while inactive or before the first response. */
export function useGraphNodeSmile(
  active: boolean,
  ticker: string,
  expiry: string,
  body: Record<string, string | number | boolean>,
): UseGraphNodeSmileResult {
  const [node, setNode] = useState<GraphNodeSmile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stable key so an unchanged body doesn't refetch every render.
  const bodyKey = JSON.stringify(body);

  useEffect(() => {
    if (!active || ticker === "" || expiry === "") {
      setNode(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .get<GraphNodeSmile>(
        `/graph/extrapolate/nodes/${ticker}/${encodeURIComponent(expiry)}`,
        { params: body, signal: controller.signal },
      )
      .then((res) => {
        setNode(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setNode(null);
        setLoading(false);
      });
    return () => controller.abort();
  }, [active, ticker, expiry, bodyKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return { node, loading, error };
}
