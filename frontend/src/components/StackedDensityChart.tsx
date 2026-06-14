// "Stacked densities" view of the Parametric workspace (ROADMAP Phase 10).
//
// Overlays the risk-neutral density of every selected expiry on shared axes
// (GET /smiles/{ticker}/densities) — all curves staying above zero is the
// visual no-butterfly-arbitrage check. Self-fetching like QuoteTable; refetches
// when the node/fit-mode changes or the current smile is refitted.
import { useEffect, useState } from "react";
import { api } from "../state/api";
import type { FitMode } from "../state/useSmile";
import type { SmileData } from "../lib/mockData";
import OverlayCurvesChart, { maturityColor } from "./OverlayCurvesChart";
import type { OverlaySeries } from "./OverlayCurvesChart";

interface StackedItem {
  expiry: string;
  t: number;
  x: number[];
  density: number[];
}
interface StackedResponse {
  ticker: string;
  expiries: StackedItem[];
}

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

interface Props {
  ticker: string;
  fitMode: FitMode;
  /** Current smile: refetch when it is refitted (edits, settings changes). */
  smile: SmileData | null;
}

export default function StackedDensityChart({ ticker, fitMode, smile }: Props) {
  const [data, setData] = useState<StackedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ticker === "") return;
    const controller = new AbortController();
    setLoading(true);
    api
      .get<StackedResponse>(`/smiles/${ticker}/densities`, {
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
  }, [ticker, fitMode, smile]);

  if (data === null) {
    return loading
      ? message("Loading densities…")
      : message(`Densities unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const n = data.expiries.length;
  const series: OverlaySeries[] = data.expiries.map((e, i) => ({
    label: `${e.t.toFixed(2)}y`,
    xs: e.x,
    ys: e.density,
    color: maturityColor(n > 1 ? i / (n - 1) : 0),
  }));

  return (
    <OverlayCurvesChart
      series={series}
      xLabel="x = log(Sₜ / F)"
      yLabel="density"
      zeroBaseline
    />
  );
}
