// 3D implied-volatility surface for the Parametric workspace: fetches
// GET /surface/{ticker} lazily (mounted only while the Surface view is open)
// and renders the (k, sqrt(T), σ) mesh via the shared SurfaceMesh renderer.
// Live backend only (the parent gates mock mode).
import { useEffect, useState } from "react";
import { api } from "../state/api";
import type { FitMode } from "../state/useSmile";
import SurfaceMesh from "./SurfaceMesh";
import type { SurfaceMeshData } from "./SurfaceMesh";
import type { AxisMode } from "../lib/axisModes";

/** Response of GET /surface/{ticker} (adds atmVol/forward beyond the mesh). */
interface SurfaceResponse extends SurfaceMeshData {
  ticker: string;
  atmVol: number[];
  forward: number[];
}

interface SurfaceChartProps {
  ticker: string;
  fitMode: FitMode;
  /** Bumps to force a refetch (e.g. a spot move transports the surface). */
  reloadKey?: number;
  /** Strike-axis display mode (shared with the Smile view). */
  axisMode?: AxisMode;
}

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function SurfaceChart({
  ticker,
  fitMode,
  reloadKey = 0,
  axisMode = "logmoneyness",
}: SurfaceChartProps) {
  const [data, setData] = useState<SurfaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ticker === "") return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .get<SurfaceResponse>(`/surface/${ticker}`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setData(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [ticker, fitMode, reloadKey]);

  if (data === null) {
    return loading
      ? message("Loading surface…")
      : message(`Surface unavailable${error !== null ? ` (${error})` : ""}.`);
  }
  return <SurfaceMesh data={data} axisMode={axisMode} />;
}
