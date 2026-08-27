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
import type { OverlayMarker, OverlaySeries } from "./OverlayCurvesChart";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import {
  axisModeLabel,
  axisTickLabel,
  axisTransform,
  makeVolAt,
} from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";

interface StackedItem {
  expiry: string;
  t: number;
  x: number[];
  density: number[];
  forward: number;
  atmVol: number;
  vol: number[]; // displayed-model IV at each x (for the Δ axis)
  /** Sub-zero evidence (V3.3 item 11), attached ONLY when the displayed
   *  model's SIGNED pdf dips below zero (butterfly arb — never for LQD):
   *  the un-clipped pdf plus its full-grid (pre-stride) min and location. */
  densityRaw?: number[];
  minDensity?: number | null;
  minDensityX?: number | null;
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
  /** Strike-axis display mode (shared with the Smile view). */
  axisMode?: AxisMode;
}

export default function StackedDensityChart({ ticker, fitMode, smile, axisMode = "logmoneyness" }: Props) {
  const { format } = useExpiryFormat();
  const [data, setData] = useState<StackedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refetch only when the surface fit actually changes, not on every new `smile`
  // object identity. The whole-surface RMS moves whenever ANY expiry refits, the
  // forward moves on a spot transport, and stale/hasFit flip on calibration — so
  // this stable key triggers exactly the density-relevant updates while skipping
  // the dense all-expiry payload on unrelated re-renders / quote-edit churn.
  const fitKey = smile
    ? `${smile.surfaceRmsError ?? ""}|${smile.forward}|${smile.stale ? 1 : 0}|${smile.hasFit ? 1 : 0}`
    : "none";

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
  }, [ticker, fitMode, fitKey]);

  if (data === null) {
    return loading
      ? message("Loading densities…")
      : message(`Densities unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const n = data.expiries.length;
  // x = log-return (= log-moneyness); each expiry re-coordinates by its own
  // forward / ATM vol / smile, so the overlay's axis switches just like the Smile.
  const txOf = (e: StackedItem) => {
    const ctx = {
      forward: e.forward,
      t: e.t,
      atmVol: e.atmVol,
      volAt: makeVolAt(e.x.map((k2, j) => ({ k: k2, vol: e.vol[j] ?? e.atmVol }))),
      kRange: [e.x[0] ?? -1, e.x[e.x.length - 1] ?? 1] as [number, number],
    };
    return (k: number) => (axisMode === "logmoneyness" ? k : axisTransform(axisMode, k, ctx));
  };
  const series: OverlaySeries[] = data.expiries.map((e, i) => {
    const tx = txOf(e);
    // Sub-zero evidence (V3.3 item 11): when the backend attached the SIGNED
    // pdf, plot IT (== the clipped curve wherever g >= 0) so the dip is
    // visible below the zero baseline, and fill the excursion red.
    const raw = e.densityRaw !== undefined && e.densityRaw.length === e.x.length;
    return {
      label: formatExpiry(e.expiry, e.t, format),
      t: e.t,
      xs: e.x.map(tx),
      ys: raw ? (e.densityRaw as number[]) : e.density,
      color: maturityColor(n > 1 ? i / (n - 1) : 0),
      fillNegative: raw,
    };
  });
  // Dip circles at the pre-stride minimum (a dip narrower than the chart
  // stride still gets its marker even when the plotted curve misses it).
  const markers: OverlayMarker[] = data.expiries.flatMap((e) => {
    if (e.minDensity == null || e.minDensityX == null) return [];
    return [
      {
        x: txOf(e)(e.minDensityX),
        y: e.minDensity,
        label:
          `min density ${e.minDensity.toExponential(2)} at k ${e.minDensityX.toFixed(3)} · ` +
          `${formatExpiry(e.expiry, e.t, format)} (butterfly arb — full-grid minimum)`,
      },
    ];
  });

  return (
    <OverlayCurvesChart
      series={series}
      xLabel={axisMode === "logmoneyness" ? "x = log(Sₜ / F)" : axisModeLabel(axisMode)}
      yLabel="density"
      zeroBaseline
      formatX={(v) => axisTickLabel(axisMode, v)}
      markers={markers}
      link={axisMode === "logmoneyness" ? { ticker, chartId: "parametric:densities" } : undefined}
    />
  );
}
