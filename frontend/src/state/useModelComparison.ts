// Lazy fetch for GET /smiles/{ticker}/{expiry}/compare (V3.2 item 12).
//
// Runs ONLY while the Compare view is open (`enabled`) and ONLY for the
// requested `models` (wave 2: the prevailing calibrated family shows at once,
// the others are fitted lazily when their chip is clicked — the endpoint's
// (fit_key, model) cache makes re-toggles free). Keyed on the node, the fit
// mode and the smile reload key (spot transports / recalibrations), the same
// refetch triggers as the sibling surface views. Backendless mode falls back
// to the built-in mock comparison so the app keeps working offline.
import { useEffect, useState } from "react";
import { api } from "./api";
import { getMockComparison } from "../lib/mockData";
import type { CompareResponse } from "../lib/mockData";
import type { FitMode } from "./useSmile";

export interface UseModelComparisonResult {
  data: CompareResponse | null;
  loading: boolean;
  error: string | null;
}

export function useModelComparison(
  enabled: boolean,
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  reloadKey = 0,
  models: readonly string[] = ["lqd", "svi", "sigmoid"],
): UseModelComparisonResult {
  const modelsKey = models.join(",");
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return; // lazy: fetch nothing until the Compare view opens
    if (!live || ticker === "" || expiry === "") {
      setData(getMockComparison()); // backendless: the app must still work
      setLoading(false);
      setError(null);
      return;
    }
    let active = true; // drop results landing after unmount / a newer key
    setLoading(true);
    setError(null);
    api
      .get<CompareResponse>(`/smiles/${ticker}/${expiry}/compare`, {
        params: { models: modelsKey, fit_mode: fitMode },
        timeoutMs: 120_000, // up to two extra fits on a cold node
      })
      .then((d) => {
        if (!active) return;
        setData(d);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setData(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      active = false;
    };
  }, [enabled, live, ticker, expiry, fitMode, reloadKey, modelsKey]);

  return { data, loading, error };
}
