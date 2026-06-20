// Fetches a Local-Vol-derived view (density / term / table) for the Local Vol
// workspace's Parametric-style sub-tabs (ROADMAP Phase 10).
//
// Each view POSTs the SAME AffineFitRequest body the surface fit (useAffine)
// uses, so it hits the identical backend cache key — the derived payload is
// reconstructed from the already-calibrated affine surface (no recalibration):
//   POST /fit/affine/{ticker}/term                 -> TermResponse
//   POST /fit/affine/{ticker}/density?expiry=ISO   -> DistributionData
//   POST /fit/affine/{ticker}/table?expiry=ISO     -> TableResponse
//
// Only the active sub-tab's hook runs (gated by `enabled`), so at most one
// derived view is in flight at a time. Params are debounced like useAffine so
// dragging a grid slider issues one refetch per pause.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

/** Which derived view to fetch. */
export type AffineViewKind = "density" | "term" | "table";

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

export interface UseAffineViewResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useAffineView<T>(
  kind: AffineViewKind,
  ticker: string,
  expiry: string | null,
  enabled: boolean,
  reloadKey: number = 0,
  fitMode: string = "mid",
): UseAffineViewResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasDataRef = useRef(false);

  // density/table need an expiry; term is whole-surface.
  const needsExpiry = kind !== "term";

  useEffect(() => {
    if (!enabled || ticker === "") return;
    if (needsExpiry && (expiry === null || expiry === "")) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .post<T>(`/fit/affine/${ticker}/${kind}`, {
        // Viewed fit target, matching useAffine's surface fit so the derived view
        // reconstructs from the SAME cached surface (grid + roughness are global).
        body: { fitMode },
        params: needsExpiry ? { expiry: expiry as string } : undefined,
        signal: controller.signal,
      })
      .then((res) => {
        setData(res);
        hasDataRef.current = true;
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setData(null);
        setError(messageOf(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [kind, ticker, expiry, enabled, needsExpiry, reloadKey, fitMode]);

  return { data, loading: loading && !hasDataRef.current, error };
}
