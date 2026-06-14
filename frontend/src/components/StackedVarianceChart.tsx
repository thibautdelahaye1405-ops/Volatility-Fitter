// "Stacked IV" view of the Parametric workspace (ROADMAP Phase 10).
//
// Overlays every expiry's TOTAL VARIANCE w(k) = σ(k)²·T on shared axes
// (GET /surface/{ticker}, reusing the fitted mesh). Non-crossing total-variance
// curves ⟺ no calendar arbitrage — the exact statement (raw σ smiles can cross
// even when arbitrage-free, so total variance is the right y-axis). Self-
// fetching like SurfaceChart; refetches on node / fit-mode change.
import { useEffect, useState } from "react";
import { api } from "../state/api";
import type { FitMode } from "../state/useSmile";
import OverlayCurvesChart, { maturityColor } from "./OverlayCurvesChart";
import type { OverlaySeries } from "./OverlayCurvesChart";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";

/** Response of GET /surface/{ticker} (backend SurfaceResponse). */
interface SurfaceResponse {
  ticker: string;
  expiries: string[];
  t: number[];
  k: number[];
  vol: number[][]; // one row per expiry, one column per k
}

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

interface Props {
  ticker: string;
  fitMode: FitMode;
  /** Bumps to force a refetch (e.g. a spot move transports the surface). */
  reloadKey?: number;
}

export default function StackedVarianceChart({ ticker, fitMode, reloadKey = 0 }: Props) {
  const { format } = useExpiryFormat();
  const [data, setData] = useState<SurfaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ticker === "") return;
    const controller = new AbortController();
    setLoading(true);
    api
      .get<SurfaceResponse>(`/surface/${ticker}`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((d) => {
        setData(d);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
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

  const n = data.t.length;
  // w(k) = σ(k)² · T per expiry, on the shared k grid.
  const series: OverlaySeries[] = data.t.map((ti, i) => ({
    label: formatExpiry(data.expiries[i], ti, format),
    xs: data.k,
    ys: data.vol[i].map((v) => v * v * ti),
    color: maturityColor(n > 1 ? i / (n - 1) : 0),
  }));

  return (
    <OverlayCurvesChart
      series={series}
      xLabel="k = log(K / F)"
      yLabel="total variance w = σ²·T"
      zeroBaseline
      zoomY
    />
  );
}
