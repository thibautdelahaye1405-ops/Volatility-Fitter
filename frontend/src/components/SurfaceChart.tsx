// 3D implied-volatility surface for the Parametric workspace: fetches
// GET /surface/{ticker} lazily (mounted only while the Surface view is open)
// and renders the (k, sqrt(T), σ) mesh via the shared SurfaceMesh renderer.
// Live backend only (the parent gates mock mode).
import type { FitMode } from "../state/useSmile";
import { useSurface } from "../state/useSurface";
import SurfaceMesh from "./SurfaceMesh";
import type { AxisMode } from "../lib/axisModes";

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
  const { data, loading, error } = useSurface(ticker, fitMode, reloadKey);

  if (data === null) {
    return loading
      ? message("Loading surface…")
      : message(`Surface unavailable${error !== null ? ` (${error})` : ""}.`);
  }
  return <SurfaceMesh data={data} axisMode={axisMode} />;
}
