// Compact calibration-weight strip under the smile chart (V3.4 item 5;
// series redefined 2026-09-09). Hand-rolled SVG, no chart deps: two bar
// series per quote — "target" (the scheme's target shape at the quote,
// normalized to max 1: flat for equal / uniform, time value, vega, |delta|)
// and "weight" (the mean-1 weight the LSQ actually sums = target × the
// Voronoi density correction, on its own scale) — drawn on the smile chart's
// OWN x axis: the chart hands the strip its live x view (brush window, then
// wheel-zoom / pan) and its k → display transform, so the bars sit under the
// quotes in every axis mode and follow every zoom. Excluded quotes render as
// hollow outlines. Binning / normalization lives in lib/weightStrip; data in
// state/useWeights.
//
// Readout (2026-09-10): the chart also hands the strip its crosshair k. The
// bar pair nearest the crosshair (within a few px) lights up and its readout
// — k, the scheme's target, the density multiplier applied, the weight — is
// drawn as the chart's crosshair badge on the strip, so sweeping the smile
// reads the weights without a native tooltip's delay. The SVG <title>s stay
// as the fallback when there is no crosshair (touch, a stripped chart).
import { useMemo } from "react";
import { CrosshairBadge } from "./CrosshairOverlay";
import type { SmileData } from "../lib/mockData";
import { linearScale } from "../lib/chartScale";
import { buildWeightBars, targetLabel } from "../lib/weightStrip";
import type { WeightBar } from "../lib/weightStrip";
import { useElementSize } from "../lib/useElementSize";
import { useWeights } from "../state/useWeights";
import type { FitMode } from "../state/useSmile";

/** Mirrors SmileChart's MARGIN so the bars align with the plot area. */
const MARGIN = { left: 52, right: 14 } as const;
const BAR_W = 2.5; // px per bar; the pair straddles the quote's x
const EXCLUDED_H = 0.35; // hollow-outline height, fraction of the strip
/** Max distance (px) between the crosshair and a bar pair's centre for the
 *  pair to count as "under" the crosshair — the pair's own width plus a hair. */
const ACTIVE_TOL = 6;

interface WeightStripProps {
  live: boolean;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** Current smile — identity changes on every edit/refit (reload key). */
  smile: SmileData | null;
  /** The chart's current x view in DISPLAY units (SmileChart's footer
   *  context): the brushed window, then the wheel-zoom / pan on top. */
  xView: readonly [number, number];
  /** The chart's k → display transform (its axis mode + market frame). */
  tx: (k: number) => number;
  /** The chart's crosshair k while the pointer is over its plot (null /
   *  omitted = no crosshair): the strip badges the bar pair under it. */
  crosshairK?: number | null;
}

/** The hover / badge text of one bar pair. */
export function weightReadout(b: WeightBar): string {
  if (b.excluded) return `k ${b.k.toFixed(3)} · excluded`;
  return `k ${b.k.toFixed(3)} · target ${b.targetRaw.toFixed(3)} · ×${b.spacingMult.toFixed(2)} spacing · weight ${b.weight.toFixed(2)}`;
}

/** The bar pair whose centre lies within ACTIVE_TOL px of the crosshair. */
function activeBar(
  bars: readonly WeightBar[],
  crosshairK: number | null | undefined,
  xOf: (k: number) => number,
): WeightBar | null {
  if (crosshairK == null || !Number.isFinite(crosshairK)) return null;
  const cx = xOf(crosshairK);
  let best: WeightBar | null = null;
  let bestD = ACTIVE_TOL;
  for (const b of bars) {
    const d = Math.abs(xOf(b.k) - cx);
    if (d <= bestD) {
      bestD = d;
      best = b;
    }
  }
  return best;
}

export default function WeightStrip({
  live,
  ticker,
  expiry,
  fitMode,
  smile,
  xView,
  tx,
  crosshairK = null,
}: WeightStripProps) {
  const { ref, size } = useElementSize();
  const data = useWeights(true, live, ticker, expiry, fitMode, smile);
  const bars = useMemo(
    () => (data !== null ? buildWeightBars(data.entries, { scheme: data.scheme, maxMult: data.maxMult }) : []),
    [data],
  );

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height);
  const xScale = linearScale([xView[0], xView[1]], [0, plotW]);
  const xOf = (k: number) => xScale.map(tx(k));
  const quoteCount = smile?.quotes.length ?? 0;
  const scheme = data?.scheme ?? null;
  const active = plotW > 0 ? activeBar(bars, crosshairK, xOf) : null;

  if (quoteCount === 0) return null;
  return (
    <div className="flex h-[70px] shrink-0 flex-col" data-testid="weight-strip">
      {/* Tiny legend, matching the chart legend's grammar */}
      <div className="mb-0.5 flex shrink-0 items-center gap-4 px-1 text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5" title="The scheme's target shape at each quote (normalized to its max): the aggregate weight distribution the fit is asked to follow along the smile">
          <span className="h-2 w-2 rounded-sm bg-slate-400/50" /> target{scheme !== null ? ` · ${targetLabel(scheme)}` : ""}
        </span>
        <span className="flex items-center gap-1.5" title="The mean-1 weight the least squares actually sums: the target × the strike-density correction min(sᵢ / s̄, cap) — equal applies no correction">
          <span className="h-2 w-2 rounded-sm bg-accent-400/80" /> weight (mean 1)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm border border-slate-500" /> excluded
        </span>
        <span className="ml-auto font-mono text-slate-600">
          {data !== null ? `scheme ${data.scheme}` : "weights unavailable"}
        </span>
      </div>
      {/* Bar strip (measured for responsive SVG) + the crosshair badge */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg width={size.width} height={size.height} className="absolute inset-0">
            <g transform={`translate(${MARGIN.left},0)`}>
              <line x1={0} x2={plotW} y1={plotH - 0.5} y2={plotH - 0.5} stroke="rgb(255 255 255 / 0.08)" />
              {bars.map((b) => {
                const x = xOf(b.k);
                if (x < -4 || x > plotW + 4) return null;
                const isActive = active !== null && active.index === b.index;
                if (b.excluded) {
                  return (
                    <rect
                      key={b.index}
                      data-quote-index={b.index}
                      data-active={isActive ? "true" : undefined}
                      x={x - BAR_W}
                      y={plotH * (1 - EXCLUDED_H)}
                      width={2 * BAR_W}
                      height={plotH * EXCLUDED_H - 1}
                      fill="none"
                      stroke={isActive ? "rgb(226 232 240 / 0.9)" : "rgb(148 163 184 / 0.55)"}
                      strokeDasharray="2 2"
                    >
                      <title>{weightReadout(b)}</title>
                    </rect>
                  );
                }
                const ht = Math.max(1, b.target * (plotH - 2));
                const hw = Math.max(1, b.weightNorm * (plotH - 2));
                return (
                  <g key={b.index} data-quote-index={b.index} data-active={isActive ? "true" : undefined}>
                    {/* The lit pair: brighter fills and a hairline outline, the
                        chart's own "selected quote" emphasis. */}
                    <rect x={x - BAR_W - 0.5} y={plotH - ht} width={BAR_W} height={ht}
                      fill={isActive ? "rgb(203 213 225 / 0.85)" : "rgb(148 163 184 / 0.5)"}
                      stroke={isActive ? "rgb(226 232 240)" : "none"} strokeWidth={0.75}>
                      <title>{weightReadout(b)}</title>
                    </rect>
                    <rect x={x + 0.5} y={plotH - hw} width={BAR_W} height={hw}
                      fill="var(--color-accent-400)" fillOpacity={isActive ? 1 : 0.8}
                      stroke={isActive ? "rgb(226 232 240)" : "none"} strokeWidth={0.75}>
                      <title>{weightReadout(b)}</title>
                    </rect>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
        {active !== null && (
          <div data-testid="weight-strip-badge">
            <CrosshairBadge label={weightReadout(active)} />
          </div>
        )}
      </div>
    </div>
  );
}
