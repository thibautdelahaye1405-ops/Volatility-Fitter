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
  const series: OverlaySeries[] = data.expiries.map((e, i) => {
    const xs =
      axisMode === "logmoneyness"
        ? e.x
        : e.x.map((k) =>
            axisTransform(axisMode, k, {
              forward: e.forward,
              t: e.t,
              atmVol: e.atmVol,
              volAt: makeVolAt(e.x.map((k2, j) => ({ k: k2, vol: e.vol[j] ?? e.atmVol }))),
              kRange: [e.x[0] ?? -1, e.x[e.x.length - 1] ?? 1],
            }),
          );
    return {
      label: formatExpiry(e.expiry, e.t, format),
      xs,
      ys: e.density,
      color: maturityColor(n > 1 ? i / (n - 1) : 0),
    };
  });

  return (
    <OverlayCurvesChart
      series={series}
      xLabel={axisMode === "logmoneyness" ? "x = log(Sₜ / F)" : axisModeLabel(axisMode)}
      yLabel="density"
      zeroBaseline
      formatX={(v) => axisTickLabel(axisMode, v)}
    />
  );
}
