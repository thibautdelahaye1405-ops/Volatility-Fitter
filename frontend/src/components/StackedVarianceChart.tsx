// "Stacked IV" view of the Parametric workspace (ROADMAP Phase 10).
//
// Overlays every expiry's TOTAL VARIANCE w(k) = σ(k)²·T on shared axes
// (GET /surface/{ticker}, reusing the fitted mesh). Non-crossing total-variance
// curves ⟺ no calendar arbitrage — the exact statement (raw σ smiles can cross
// even when arbitrage-free, so total variance is the right y-axis). Self-
// fetching like SurfaceChart; refetches on node / fit-mode change.
import type { FitMode } from "../state/useSmile";
import { useSurface } from "../state/useSurface";
import OverlayCurvesChart, { maturityColor } from "./OverlayCurvesChart";
import type { OverlaySeries } from "./OverlayCurvesChart";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import {
  axisModeLabel,
  axisTickLabel,
  axisTransform,
  makeVolAt,
} from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

interface Props {
  ticker: string;
  fitMode: FitMode;
  /** Bumps to force a refetch (e.g. a spot move transports the surface). */
  reloadKey?: number;
  /** Strike-axis display mode (shared with the Smile view). */
  axisMode?: AxisMode;
}

export default function StackedVarianceChart({
  ticker,
  fitMode,
  reloadKey = 0,
  axisMode = "logmoneyness",
}: Props) {
  const { format } = useExpiryFormat();
  const { data, loading, error } = useSurface(ticker, fitMode, reloadKey);

  if (data === null) {
    return loading
      ? message("Loading surface…")
      : message(`Surface unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const n = data.t.length;
  // Total variance w(k) = σ(k)² · τ per expiry (σ is quoted in the event-variance
  // clock τ, so this recovers the price-implied w; non-crossing ⟺ no calendar arb).
  // Each expiry re-coordinates k by its own forward / smile for the chosen axis.
  const kRange: [number, number] = [data.k[0] ?? -1, data.k[data.k.length - 1] ?? 1];
  const series: OverlaySeries[] = data.t.map((ti, i) => {
    const xs =
      axisMode === "logmoneyness"
        ? data.k
        : data.k.map((k) =>
            axisTransform(axisMode, k, {
              forward: data.forward[i],
              t: ti,
              atmVol: data.atmVol[i],
              volAt: makeVolAt(data.k.map((k2, j) => ({ k: k2, vol: data.vol[i][j] }))),
              kRange,
            }),
          );
    return {
      label: formatExpiry(data.expiries[i], ti, format),
      xs,
      ys: data.vol[i].map((v) => v * v * data.tau[i]),
      color: maturityColor(n > 1 ? i / (n - 1) : 0),
    };
  });

  return (
    <OverlayCurvesChart
      series={series}
      xLabel={axisMode === "logmoneyness" ? "k = log(K / F)" : axisModeLabel(axisMode)}
      yLabel="total variance w = σ²·T"
      zeroBaseline
      zoomY
      formatX={(v) => axisTickLabel(axisMode, v)}
    />
  );
}
