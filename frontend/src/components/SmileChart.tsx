// Interactive implied-volatility smile chart. Hand-rolled SVG, no chart deps.
// Controlled component: the visible strike window is owned by the parent and
// edited through the RangeBrush rendered underneath the plot.
//
// All internal geometry (brush window, quote hit-testing, curve clipping)
// lives in log-moneyness k = ln(K/F). The strike-axis display mode (strike,
// %ATM, delta, normalized…) only changes how ticks are generated and how the
// tick / crosshair labels read — see lib/axisModes.ts.
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type { QuoteBand, SmilePoint } from "../lib/mockData";
import { clamp, formatPct, linearScale, niceTicks } from "../lib/chartScale";
import { axisTicks, axisTransform, formatHoverValue } from "../lib/axisModes";
import type { AxisContext, AxisMode } from "../lib/axisModes";
import RangeBrush from "./RangeBrush";

interface SmileChartProps {
  model: SmilePoint[];
  prior: SmilePoint[];
  quotes: QuoteBand[];
  /** Visible log-moneyness window [lo, hi] (controlled). */
  kWindow: readonly [number, number];
  onKWindowChange: (next: [number, number]) => void;
  /** Full brushable k extent of the data. */
  fullRange: readonly [number, number];
  /** Strike-axis display mode (labels only; geometry stays in k). */
  axisMode?: AxisMode;
  /** Forward level — strike / %ATM axis modes. */
  forward?: number;
  /** Year-fraction to expiry — delta / normalized axis modes. */
  t?: number;
  /** ATM implied vol — normalized axis modes. */
  atmVol?: number;
  /** Stable `index` of the highlighted quote, or null for no selection. */
  selectedIndex?: number | null;
  /** Quote click handler; called with null on background clicks. */
  onQuoteSelect?: (index: number | null) => void;
  /** SSR scenario overlay (shifted smile); drawn dotted amber when set. */
  scenario?: SmilePoint[] | null;
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
  t,
  atmVol,
  selectedIndex = null,
  onQuoteSelect,
  scenario = null,
}: SmileChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Hover position in k-space, or null when the pointer is outside. */
  const [hoverK, setHoverK] = useState<number | null>(null);

  const [kLo, kHi] = kWindow;
  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Context for the axis-mode transforms (labels only, never geometry).
  const axisCtx: AxisContext = useMemo(
    () => ({
      forward: forward ?? 1,
      t: t ?? 0,
      atmVol: atmVol ?? 0,
      volAt: (kv: number) => volAt(model, kv),
      kRange:
        model.length > 1
          ? ([model[0].k, model[model.length - 1].k] as const)
          : fullRange,
    }),
    [forward, t, atmVol, model, fullRange],
  );

  // Scales over the *visible* window only; x is always linear in k and the
  // y domain auto-fits the visible data plus padding.
  const { xScale, yScale } = useMemo(() => {
    const inWindow = (k: number) => k >= kLo && k <= kHi;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (const p of model) if (inWindow(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    for (const p of prior) if (inWindow(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    for (const p of scenario ?? []) if (inWindow(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    for (const q of quotes) if (inWindow(q.k)) { yMin = Math.min(yMin, q.bid); yMax = Math.max(yMax, q.ask); }
    if (!Number.isFinite(yMin)) { yMin = 0; yMax = 1; }
    const pad = Math.max(1e-4, (yMax - yMin) * 0.08);
    return {
      xScale: linearScale([kLo, kHi], [0, plotW]),
      yScale: linearScale([yMin - pad, yMax + pad], [plotH, 0]),
    };
  }, [model, prior, scenario, quotes, kLo, kHi, plotW, plotH]);

  /** Build an SVG path for a curve, clipped to the visible window. */
  const pathOf = (curve: SmilePoint[]): string => {
    let d = "";
    for (const p of curve) {
      if (p.k < kLo || p.k > kHi) continue;
      const x = xScale.map(p.k);
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    return d;
  };
  const modelPath = useMemo(() => pathOf(model), [model, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const priorPath = useMemo(() => pathOf(prior), [prior, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const scenarioPath = useMemo(() => (scenario ? pathOf(scenario) : ""), [scenario, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps

  // X ticks: nice values in display units, positioned at their k preimage.
  const xTicks = useMemo(
    () => axisTicks(axisMode, kLo, kHi, axisCtx, 6),
    [axisMode, kLo, kHi, axisCtx],
  );
  const yTicks = niceTicks(yScale.domain[0], yScale.domain[1], 6);
  const visibleQuotes = quotes.filter((q) => q.k >= kLo && q.k <= kHi);

  /* ---------------- crosshair ---------------- */

  const onMouseMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    if (px < 0 || px > plotW) { setHoverK(null); return; }
    setHoverK(clamp(xScale.invert(px), kLo, kHi));
  };

  const hoverVol = hoverK !== null ? volAt(model, hoverK) : null;
  const hoverX = hoverK !== null ? xScale.map(hoverK) : 0;
  const hoverLabel =
    hoverK !== null && hoverVol !== null
      ? `${formatHoverValue(axisMode, axisTransform(axisMode, hoverK, axisCtx))} · σ ${formatPct(hoverVol, 2)}`
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
        {scenarioPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dotted border-amber-400" /> SSR scenario
          </span>
        )}
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
              {yTicks.map((tv) => (
                <line key={`gy${tv}`} x1={0} x2={plotW} y1={yScale.map(tv)} y2={yScale.map(tv)}
                  stroke="rgb(255 255 255 / 0.05)" />
              ))}
              {xTicks.map((tick) => (
                <line key={`gx${tick.k}`} x1={xScale.map(tick.k)} x2={xScale.map(tick.k)} y1={0} y2={plotH}
                  stroke="rgb(255 255 255 / 0.04)" />
              ))}

              {/* Zero log-moneyness (ATM forward) reference */}
              {kLo < 0 && kHi > 0 && (
                <line x1={xScale.map(0)} x2={xScale.map(0)} y1={0} y2={plotH}
                  stroke="rgb(148 163 184 / 0.25)" strokeDasharray="2 4" />
              )}

              {/* Axes labels */}
              {yTicks.map((tv) => (
                <text key={`ly${tv}`} x={-8} y={yScale.map(tv)} dy="0.32em" textAnchor="end"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatPct(tv)}
                </text>
              ))}
              {xTicks.map((tick) => (
                <text key={`lx${tick.k}`} x={xScale.map(tick.k)} y={plotH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {tick.label}
                </text>
              ))}

              {/* Quote bands: I-beam bid/ask bars with a mid tick.
                  States: excluded -> dimmed beam + small × at the mid;
                  amended -> amber, longer mid tick; selected -> accent
                  stroke + soft glow circle. Each quote also gets an
                  invisible click target for selection. */}
              {visibleQuotes.map((q) => {
                const x = xScale.map(q.k);
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

              {/* SSR scenario overlay: dotted amber, above prior, below fit */}
              {scenarioPath !== "" && (
                <path d={scenarioPath} fill="none" stroke="rgb(251 191 36 / 0.85)"
                  strokeWidth={1.5} strokeDasharray="2 3" />
              )}

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
