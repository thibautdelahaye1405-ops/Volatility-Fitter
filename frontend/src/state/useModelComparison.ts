// Lazy fetch for GET /smiles/{ticker}/{expiry}/compare (V3.2 item 12).
//
// Runs ONLY while the Compare view is open (`enabled`) and ONLY for the
// requested `models` (wave 2: the prevailing calibrated family shows at once,
// the others are fitted lazily when their chip is clicked — the endpoint's
// (fit_key, model) cache makes re-toggles free). `tails` are the tail-matching
// toggles (lib/tailMatch): with any lit, the SVI-JW / MCS rows are refit with
// their tails pulled onto LQD's and the response reports what applied. Keyed
// on the node, the fit mode and the smile reload key (spot transports /
// recalibrations), the same refetch triggers as the sibling surface views.
// Backendless mode falls back to the built-in mock comparison (cut to the
// requested models, the tail flags echoed as applied) so the app keeps
// working offline.
import { useEffect, useState } from "react";
import { api } from "./api";
import { getMockComparison } from "../lib/mockData";
import type { CompareResponse, CompareTailFlag } from "../lib/mockData";
import { CHIP_MODELS } from "../lib/modelColor";
import type { FitMode } from "./useSmile";

export interface UseModelComparisonResult {
  data: CompareResponse | null;
  loading: boolean;
  error: string | null;
}

/** The mock comparison as the live endpoint would answer the same request. */
function mockComparison(modelsKey: string, tailsKey: string): CompareResponse {
  const mock = getMockComparison();
  const wanted = new Set(modelsKey.split(","));
  const flags = tailsKey === "" ? [] : (tailsKey.split(",") as CompareTailFlag[]);
  const constrained = new Set(["svi", "sigmoid"]);
  const models = mock.models
    .filter((m) => wanted.has(m.model))
    .map((m) => (flags.length > 0 && constrained.has(m.model) ? { ...m, tailMatched: flags } : m));
  const tailMatch =
    flags.length > 0
      ? { requested: flags, applied: flags, target: "lqd", leeAvailable: true, leeClamped: false }
      : null;
  return { ...mock, models, tailMatch };
}

export function useModelComparison(
  enabled: boolean,
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  reloadKey = 0,
  models: readonly string[] = CHIP_MODELS, // reference families only when asked
  tails: readonly string[] = [],
): UseModelComparisonResult {
  const modelsKey = models.join(",");
  const tailsKey = tails.join(",");
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return; // lazy: fetch nothing until the Compare view opens
    if (!live || ticker === "" || expiry === "") {
      // Backendless: the app must still work — the mock, cut to the
      // requested families so the chips (incl. the reference reveal and
      // the tail toggles) behave.
      setData(mockComparison(modelsKey, tailsKey));
      setLoading(false);
      setError(null);
      return;
    }
    let active = true; // drop results landing after unmount / a newer key
    setLoading(true);
    setError(null);
    api
      .get<CompareResponse>(`/smiles/${ticker}/${expiry}/compare`, {
        params: {
          models: modelsKey,
          fit_mode: fitMode,
          ...(tailsKey === "" ? {} : { tail_match: tailsKey }),
        },
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
  }, [enabled, live, ticker, expiry, fitMode, reloadKey, modelsKey, tailsKey]);

  return { data, loading, error };
}
