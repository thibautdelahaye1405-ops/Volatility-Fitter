// Shared fetch for GET /surface/{ticker} (the fitted (k, √T, σ) mesh + per-expiry
// forward / ATM vol). The Parametric workspace renders the mesh two ways — the 3D
// "IV surface" (SurfaceChart) and the "Stacked IV" total-variance overlay
// (StackedVarianceChart) — both off the exact same payload. This hook lets them
// share one request: a short-lived in-flight map keyed by (ticker, fitMode,
// reloadKey) coalesces identical concurrent fetches, so mounting both views (or a
// refresh fan-out that re-pulls both) costs one full-mesh download, not two.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { FitMode } from "./useSmile";

/** Response of GET /surface/{ticker} (backend SurfaceResponse). */
export interface SurfaceResponse {
  ticker: string;
  expiries: string[];
  t: number[];
  tau: number[]; // event-variance years the mesh vols are quoted in (= t with no events)
  k: number[];
  vol: number[][]; // one row per expiry, one column per k (= sqrt(w / tau))
  forward: number[]; // active forward per expiry (for strike / %ATM axes)
  atmVol: number[]; // ATM vol per expiry (for the normalized / delta axes)
}

/** In-flight requests keyed by (ticker, fitMode, reloadKey); cleared on settle,
 *  so the coalescing window is exactly the duration of one network round-trip. */
const inflight = new Map<string, Promise<SurfaceResponse>>();

function fetchSurface(ticker: string, fitMode: FitMode, reloadKey: number): Promise<SurfaceResponse> {
  const key = `${ticker}|${fitMode}|${reloadKey}`;
  const existing = inflight.get(key);
  if (existing) return existing;
  const pending = api
    .get<SurfaceResponse>(`/surface/${ticker}`, { params: { fit_mode: fitMode } })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, pending);
  return pending;
}

export interface UseSurfaceResult {
  data: SurfaceResponse | null;
  loading: boolean;
  error: string | null;
}

export function useSurface(ticker: string, fitMode: FitMode, reloadKey = 0): UseSurfaceResult {
  const [data, setData] = useState<SurfaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ticker === "") return;
    let active = true; // ignore results after unmount / a superseding fetch
    setLoading(true);
    setError(null);
    fetchSurface(ticker, fitMode, reloadKey)
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
  }, [ticker, fitMode, reloadKey]);

  return { data, loading, error };
}
