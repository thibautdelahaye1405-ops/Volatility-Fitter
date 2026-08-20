// Compact calibration-weight strip under the smile chart (V3.4 item 5).
// Hand-rolled SVG, no chart deps: two bar series per quote — "density"
// (quote crowding 1/s_i, normalized to max 1) and "weight" (the mean-1
// weight the LSQ actually uses, on its own scale) — sharing the smile's
// x transform (same axis mode + brushed k window; margins mirror the
// chart's plot area). Excluded quotes render as hollow outlines. Binning /
// normalization lives in lib/weightStrip; data in state/useWeights.
import { useMemo } from "react";
import type { QuoteBand, SmileData } from "../lib/mockData";
import { axisTransform, makeVolAt } from "../lib/axisModes";
import type { AxisContext, AxisMode } from "../lib/axisModes";
import { linearScale } from "../lib/chartScale";
import { buildWeightBars } from "../lib/weightStrip";
import { useElementSize } from "../lib/useElementSize";
import { useWeights } from "../state/useWeights";
import type { FitMode } from "../state/useSmile";

/** Mirrors SmileChart's MARGIN so the bars align with the plot area. */
const MARGIN = { left: 52, right: 14 } as const;
const BAR_W = 2.5; // px per bar; the pair straddles the quote's x
const EXCLUDED_H = 0.35; // hollow-outline height, fraction of the strip

interface WeightStripProps {
  live: boolean;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** Current smile — identity changes on every edit/refit (reload key), and
   *  supplies the axis context (forward/T/ATM vol/model curve). */
  smile: SmileData | null;
  /** Brushed k window shared with the smile chart. */
  kWindow: readonly [number, number];
  axisMode: AxisMode;
}

export default function WeightStrip({
  live,
  ticker,
  expiry,
  fitMode,
  smile,
  kWindow,
  axisMode,
}: WeightStripProps) {
  const { ref, size } = useElementSize();
  const data = useWeights(true, live, ticker, expiry, fitMode, smile);
  const bars = useMemo(() => (data !== null ? buildWeightBars(data.entries) : []), [data]);

  // Same display transform as the smile chart (base brushed window; the
  // chart's wheel-zoom is intentionally not mirrored — the brush is shared).
  const quotes: QuoteBand[] = smile?.quotes ?? [];
  const model = useMemo(() => smile?.model ?? [], [smile]);
  const ctx: AxisContext = useMemo(
    () => ({
      forward: smile?.forward ?? 1,
      t: smile?.T ?? 0,
      atmVol: smile?.diagnostics.atmVol ?? 0,
      volAt: makeVolAt(model),
      kRange:
        model.length > 1
          ? ([model[0].k, model[model.length - 1].k] as const)
          : kWindow,
    }),
    [smile, model, kWindow],
  );
  const tx = (k: number) => axisTransform(axisMode, k, ctx);

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height);
  const xScale = linearScale([tx(kWindow[0]), tx(kWindow[1])], [0, plotW]);

  if (quotes.length === 0) return null;
  return (
    <div className="flex h-[70px] shrink-0 flex-col">
      {/* Tiny legend, matching the chart legend's grammar */}
      <div className="mb-0.5 flex shrink-0 items-center gap-4 px-1 text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-slate-400/50" /> density 1/sᵢ
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-accent-400/80" /> weight (mean 1)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm border border-slate-500" /> excluded
        </span>
        <span className="ml-auto font-mono text-slate-600">
          {data !== null ? `scheme ${data.scheme}` : "weights unavailable"}
        </span>
      </div>
      {/* Bar strip (measured for responsive SVG) */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg width={size.width} height={size.height} className="absolute inset-0">
            <g transform={`translate(${MARGIN.left},0)`}>
              <line x1={0} x2={plotW} y1={plotH - 0.5} y2={plotH - 0.5} stroke="rgb(255 255 255 / 0.08)" />
              {bars.map((b) => {
                const x = xScale.map(tx(b.k));
                if (x < -4 || x > plotW + 4) return null;
                if (b.excluded) {
                  return (
                    <rect
                      key={b.index}
                      x={x - BAR_W}
                      y={plotH * (1 - EXCLUDED_H)}
                      width={2 * BAR_W}
                      height={plotH * EXCLUDED_H - 1}
                      fill="none"
                      stroke="rgb(148 163 184 / 0.55)"
                      strokeDasharray="2 2"
                    />
                  );
                }
                const hd = Math.max(1, b.density * (plotH - 2));
                const hw = Math.max(1, b.weightNorm * (plotH - 2));
                return (
                  <g key={b.index}>
                    <rect x={x - BAR_W - 0.5} y={plotH - hd} width={BAR_W} height={hd} fill="rgb(148 163 184 / 0.5)">
                      <title>{`k ${b.k.toFixed(3)} · density ${b.density.toFixed(2)}`}</title>
                    </rect>
                    <rect x={x + 0.5} y={plotH - hw} width={BAR_W} height={hw} fill="var(--color-accent-400)" fillOpacity={0.8}>
                      <title>{`k ${b.k.toFixed(3)} · weight ${b.weight.toFixed(2)}`}</title>
                    </rect>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}
