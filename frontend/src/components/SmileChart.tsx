// Interactive implied-volatility smile chart. Hand-rolled SVG, no chart deps.
// Controlled component: the visible strike window is owned by the parent and
// edited through the RangeBrush rendered underneath the plot.
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type { QuoteBand, SmilePoint } from "../lib/mockData";
import {
  clamp,
  formatAxisNumber,
  formatPct,
  linearScale,
  niceTicks,
} from "../lib/chartScale";
import RangeBrush from "./RangeBrush";

/** Strike axis rendering mode. 'strike' converts k to K = F * exp(k). */
export type StrikeAxisMode = "logmoneyness" | "strike";

interface SmileChartProps {
  model: SmilePoint[];
  prior: SmilePoint[];
  quotes: QuoteBand[];
  /** Visible log-moneyness window [lo, hi] (controlled). */
  kWindow: readonly [number, number];
  onKWindowChange: (next: [number, number]) => void;
  /** Full brushable k extent of the data. */
  fullRange: readonly [number, number];
  axisMode?: StrikeAxisMode;
  /** Forward level, required to label the axis in fixed-strike mode. */
  forward?: number;
  /** Stable `index` of the highlighted quote, or null for no selection. */
  selectedIndex?: number | null;
  /** Quote click handler; called with null on background clicks. */
  onQuoteSelect?: (index: number | null) => void;
}

const MARGIN = { top: 14, right: 14, bottom: 30, left: 52 } as const;

/** Track the pixel size of a container element via ResizeObserver. */
function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

/** Linear interpolation of a curve's vol at log-moneyness k. */
function volAt(curve: SmilePoint[], k: number): number | null {
  if (curve.length === 0) return null;
  const first = curve[0];
  const last = curve[curve.length - 1];
  if (k <= first.k) return first.vol;
  if (k >= last.k) return last.vol;
  for (let i = 1; i < curve.length; i++) {
    const p1 = curve[i];
    if (k <= p1.k) {
      const p0 = curve[i - 1];
      const t = (k - p0.k) / (p1.k - p0.k);
      return p0.vol + t * (p1.vol - p0.vol);
    }
  }
  return last.vol;
}

export default function SmileChart({
  model,
  prior,
  quotes,
  kWindow,
  onKWindowChange,
  fullRange,
  axisMode = "logmoneyness",
  forward,
  selectedIndex = null,
  onQuoteSelect,
}: SmileChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Hover position in k-space, or null when the pointer is outside. */
  const [hoverK, setHoverK] = useState<number | null>(null);

  const [kLo, kHi] = kWindow;
  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Map k to the displayed x value (log-moneyness now, fixed strike later).
  const xValue = useMemo(() => {
    if (axisMode === "strike" && forward !== undefined) {
      return (k: number) => forward * Math.exp(k);
    }
    return (k: number) => k;
  }, [axisMode, forward]);

  // Scales over the *visible* window only; y auto-fits visible data + padding.
  const { xScale, yScale } = useMemo(() => {
    const inWindow = (k: number) => k >= kLo && k <= kHi;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (const p of model) if (inWindow(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    for (const p of prior) if (inWindow(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    for (const q of quotes) if (inWindow(q.k)) { yMin = Math.min(yMin, q.bid); yMax = Math.max(yMax, q.ask); }
    if (!Number.isFinite(yMin)) { yMin = 0; yMax = 1; }
    const pad = Math.max(1e-4, (yMax - yMin) * 0.08);
    return {
      xScale: linearScale([xValue(kLo), xValue(kHi)], [0, plotW]),
      yScale: linearScale([yMin - pad, yMax + pad], [plotH, 0]),
    };
  }, [model, prior, quotes, kLo, kHi, plotW, plotH, xValue]);

  /** Build an SVG path for a curve, clipped to the visible window. */
  const pathOf = (curve: SmilePoint[]): string => {
    let d = "";
    for (const p of curve) {
      if (p.k < kLo || p.k > kHi) continue;
      const x = xScale.map(xValue(p.k));
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    return d;
  };
  const modelPath = useMemo(() => pathOf(model), [model, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const priorPath = useMemo(() => pathOf(prior), [prior, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps

  const xTicks = niceTicks(xScale.domain[0], xScale.domain[1], 8);
  const yTicks = niceTicks(yScale.domain[0], yScale.domain[1], 6);
  const visibleQuotes = quotes.filter((q) => q.k >= kLo && q.k <= kHi);

  /* ---------------- crosshair ---------------- */

  const onMouseMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    if (px < 0 || px > plotW) { setHoverK(null); return; }
    const xv = xScale.invert(px);
    // Invert the axis transform back to k-space.
    const k = axisMode === "strike" && forward !== undefined ? Math.log(xv / forward) : xv;
    setHoverK(clamp(k, kLo, kHi));
  };

  const hoverVol = hoverK !== null ? volAt(model, hoverK) : null;
  const hoverX = hoverK !== null ? xScale.map(xValue(hoverK)) : 0;
  const hoverLabel =
    hoverK !== null && hoverVol !== null
      ? axisMode === "strike" && forward !== undefined
        ? `K ${formatAxisNumber(forward * Math.exp(hoverK))} · σ ${formatPct(hoverVol, 2)}`
        : `k ${hoverK.toFixed(3)} · σ ${formatPct(hoverVol, 2)}`
      : null;

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-5 px-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-accent-400" /> Current fit
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Prior
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-slate-500">⊺</span> Bid/Ask quotes
        </span>
      </div>

      {/* Plot area (measured for responsive SVG) */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className="absolute inset-0 cursor-crosshair"
            onMouseMove={onMouseMove}
            onMouseLeave={() => setHoverK(null)}
            onClick={() => onQuoteSelect?.(null)}
          >
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {/* Gridlines */}
              {yTicks.map((t) => (
                <line key={`gy${t}`} x1={0} x2={plotW} y1={yScale.map(t)} y2={yScale.map(t)}
                  stroke="rgb(255 255 255 / 0.05)" />
              ))}
              {xTicks.map((t) => (
                <line key={`gx${t}`} x1={xScale.map(t)} x2={xScale.map(t)} y1={0} y2={plotH}
                  stroke="rgb(255 255 255 / 0.04)" />
              ))}

              {/* Zero log-moneyness (ATM forward) reference */}
              {kLo < 0 && kHi > 0 && (
                <line x1={xScale.map(xValue(0))} x2={xScale.map(xValue(0))} y1={0} y2={plotH}
                  stroke="rgb(148 163 184 / 0.25)" strokeDasharray="2 4" />
              )}

              {/* Axes labels */}
              {yTicks.map((t) => (
                <text key={`ly${t}`} x={-8} y={yScale.map(t)} dy="0.32em" textAnchor="end"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatPct(t)}
                </text>
              ))}
              {xTicks.map((t) => (
                <text key={`lx${t}`} x={xScale.map(t)} y={plotH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatAxisNumber(t)}
                </text>
              ))}

              {/* Quote bands: I-beam bid/ask bars with a mid tick.
                  States: excluded -> dimmed beam + small × at the mid;
                  amended -> amber, longer mid tick; selected -> accent
                  stroke + soft glow circle. Each quote also gets an
                  invisible click target for selection. */}
              {visibleQuotes.map((q) => {
                const x = xScale.map(xValue(q.k));
                const yb = yScale.map(q.bid);
                const ya = yScale.map(q.ask);
                const ym = yScale.map(q.mid);
                const cap = 3.5;
                const selected = selectedIndex !== null && q.index === selectedIndex;
                const beamStroke = selected
                  ? "var(--color-accent-400)"
                  : "rgb(148 163 184 / 0.55)";
                const midStroke = q.amended
                  ? "rgb(251 191 36 / 0.95)"
                  : selected
                    ? "var(--color-accent-400)"
                    : "rgb(226 232 240 / 0.9)";
                const midHalf = q.amended ? 4 : 2.5;
                return (
                  <g key={q.index}>
                    {selected && (
                      <circle cx={x} cy={ym} r={7}
                        fill="var(--color-accent-400)" opacity={0.18} />
                    )}
                    <g stroke={beamStroke} strokeWidth={1}
                      opacity={q.excluded ? 0.25 : 1}>
                      <line x1={x} x2={x} y1={yb} y2={ya} />
                      <line x1={x - cap} x2={x + cap} y1={ya} y2={ya} />
                      <line x1={x - cap} x2={x + cap} y1={yb} y2={yb} />
                      <line x1={x - midHalf} x2={x + midHalf} y1={ym} y2={ym}
                        stroke={midStroke} strokeWidth={1.5} />
                    </g>
                    {q.excluded && (
                      <g stroke="rgb(148 163 184 / 0.8)" strokeWidth={1.2}>
                        <line x1={x - 3} x2={x + 3} y1={ym - 3} y2={ym + 3} />
                        <line x1={x - 3} x2={x + 3} y1={ym + 3} y2={ym - 3} />
                      </g>
                    )}
                    {onQuoteSelect && (
                      <rect
                        x={x - 6}
                        y={Math.min(ya, yb) - 8}
                        width={12}
                        height={Math.abs(yb - ya) + 16}
                        fill="transparent"
                        className="cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          onQuoteSelect(q.index);
                        }}
                      />
                    )}
                  </g>
                );
              })}

              {/* Prior fit: dashed slate */}
              <path d={priorPath} fill="none" stroke="rgb(100 116 139 / 0.9)"
                strokeWidth={1.5} strokeDasharray="5 4" />

              {/* Current model fit: accent */}
              <path d={modelPath} fill="none" stroke="var(--color-accent-400)"
                strokeWidth={2} strokeLinejoin="round" />

              {/* Crosshair: vertical guide + marker on the model curve */}
              {hoverK !== null && hoverVol !== null && (
                <g pointerEvents="none">
                  <line x1={hoverX} x2={hoverX} y1={0} y2={plotH}
                    stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                  <circle cx={hoverX} cy={yScale.map(hoverVol)} r={3.5}
                    fill="var(--color-accent-400)" stroke="#0e131c" strokeWidth={1.5} />
                </g>
              )}
            </g>
          </svg>
        )}

        {/* Tooltip readout badge (top-right corner) */}
        {hoverLabel && (
          <div className="pointer-events-none absolute top-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40">
            {hoverLabel}
          </div>
        )}
      </div>

      {/* Strike-window brush */}
      <div className="mt-2 shrink-0 px-1">
        <RangeBrush
          min={fullRange[0]}
          max={fullRange[1]}
          value={kWindow}
          onChange={onKWindowChange}
          format={(v) => v.toFixed(2)}
        />
      </div>
    </div>
  );
}
