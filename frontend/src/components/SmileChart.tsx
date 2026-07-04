// Interactive implied-volatility smile chart. Hand-rolled SVG, no chart deps.
//
// Geometry is plotted in the SELECTED strike-axis coordinate (k = ln(K/F),
// strike, %ATM, delta, normalized…), so switching the mode genuinely reshapes
// the smile — the x-axis follows the chosen coordinate strictly, not a fixed
// log axis (every mode is a monotone map of k; delta runs high→low). The coarse
// strike window is owned by the parent via the RangeBrush; on top of that, the
// chart supports wheel-zoom (x by default, +Shift = x only, +Alt = y only),
// drag-to-pan and double-click / ⌂ reset — and zoom-out reveals beyond the data.
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { QuoteBand, SmilePoint } from "../lib/mockData";
import { clamp, formatPct, linearScale, niceTicks } from "../lib/chartScale";
import { axisDisplayTicks, axisInvert, axisTransform, formatHoverValue } from "../lib/axisModes";
import type { AxisContext, AxisMode } from "../lib/axisModes";
import { useZoom } from "../lib/useZoom";
import RangeBrush from "./RangeBrush";

interface SmileChartProps {
  model: SmilePoint[];
  prior: SmilePoint[];
  /** True when `prior` is the active fetched prior (spot-updated): drawn as a
   *  distinct dotted teal "spot-updated prior" line rather than the saved dash. */
  priorTransported?: boolean;
  quotes: QuoteBand[];
  /** Visible log-moneyness window [lo, hi] (controlled, the coarse brush). */
  kWindow: readonly [number, number];
  onKWindowChange: (next: [number, number]) => void;
  /** Full brushable k extent of the data. */
  fullRange: readonly [number, number];
  /** Strike-axis display coordinate (geometry plotted in these units). */
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
  /** Pre-transport calibration (the anchor smile); drawn dimmed when set. */
  anchorCurve?: SmilePoint[] | null;
  /** Massive provider's IV points (read-only comparison); cyan dots when set. */
  massiveIv?: SmilePoint[] | null;
  /** Active var-swap quote vol — drawn as a horizontal teal line when set. */
  varSwapLevel?: number | null;
  /** Graph-extrapolated reconstructed smile (plan Phase 5 overlay): solid violet
   *  posterior curve with a shaded credible band, over the live quotes. */
  graphPost?: SmilePoint[] | null;
  graphBandLo?: SmilePoint[] | null;
  graphBandHi?: SmilePoint[] | null;
  /** Observation-filter overlay (Note 15 Phase 4): solid teal filtered
   *  posterior with a shaded ±1σ band, plus a dashed one-step prediction. */
  filterPost?: SmilePoint[] | null;
  filterBandLo?: SmilePoint[] | null;
  filterBandHi?: SmilePoint[] | null;
  filterPred?: SmilePoint[] | null;
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
      const tt = (k - p0.k) / (p1.k - p0.k);
      return p0.vol + tt * (p1.vol - p0.vol);
    }
  }
  return last.vol;
}

export default function SmileChart({
  model,
  prior,
  priorTransported = false,
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
  anchorCurve = null,
  massiveIv = null,
  varSwapLevel = null,
  graphPost = null,
  graphBandLo = null,
  graphBandHi = null,
  filterPost = null,
  filterBandLo = null,
  filterBandHi = null,
  filterPred = null,
}: SmileChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const clipId = useId();
  const zoom = useZoom();
  /** Hover position in k-space, or null when the pointer is outside. */
  const [hoverK, setHoverK] = useState<number | null>(null);
  /** Active drag-pan: last pointer px and whether it has moved past a click. */
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const [kLo, kHi] = kWindow;
  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Context for the axis-mode transforms.
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

  /** Map k -> the selected display coordinate. */
  const tx = useMemo(() => (k: number) => axisTransform(axisMode, k, axisCtx), [axisMode, axisCtx]);

  // Scales: x in display units (base = brushed window mapped through tx, then
  // zoomed); y auto-fits the data visible inside the x view, then zoomed.
  const { xScale, yScale, xView } = useMemo(() => {
    const baseX: [number, number] = [tx(kLo), tx(kHi)];
    const view = zoom.viewX(baseX);
    const xs = linearScale(view, [0, plotW]);
    const vMin = Math.min(view[0], view[1]);
    const vMax = Math.max(view[0], view[1]);
    const inView = (k: number) => {
      const X = tx(k);
      return X >= vMin && X <= vMax;
    };
    let yMin = Infinity;
    let yMax = -Infinity;
    const scan = (pts: SmilePoint[]) => {
      for (const p of pts) if (inView(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    };
    scan(model);
    scan(prior);
    if (scenario) scan(scenario);
    if (anchorCurve) scan(anchorCurve);
    if (graphPost) scan(graphPost);
    if (graphBandLo) scan(graphBandLo);
    if (graphBandHi) scan(graphBandHi);
    if (filterPost) scan(filterPost);
    if (filterBandLo) scan(filterBandLo);
    if (filterBandHi) scan(filterBandHi);
    if (filterPred) scan(filterPred);
    for (const q of quotes) if (inView(q.k)) { yMin = Math.min(yMin, q.bid); yMax = Math.max(yMax, q.ask); }
    if (varSwapLevel !== null) { yMin = Math.min(yMin, varSwapLevel); yMax = Math.max(yMax, varSwapLevel); }
    if (!Number.isFinite(yMin)) { yMin = 0; yMax = 1; }
    const pad = Math.max(1e-4, (yMax - yMin) * 0.08);
    const yView = zoom.viewY([yMin - pad, yMax + pad]);
    return { xScale: xs, yScale: linearScale(yView, [plotH, 0]), xView: view };
  }, [model, prior, scenario, anchorCurve, graphPost, graphBandLo, graphBandHi, filterPost, filterBandLo, filterBandHi, filterPred, quotes, varSwapLevel, kLo, kHi, plotW, plotH, tx, zoom]);

  /** Build an SVG path for a curve in display coordinates (clip handles overflow). */
  const pathOf = (curve: SmilePoint[]): string => {
    let d = "";
    for (const p of curve) {
      const x = xScale.map(tx(p.k));
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    return d;
  };
  const modelPath = useMemo(() => pathOf(model), [model, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const priorPath = useMemo(() => pathOf(prior), [prior, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const scenarioPath = useMemo(() => (scenario ? pathOf(scenario) : ""), [scenario, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const anchorPath = useMemo(() => (anchorCurve ? pathOf(anchorCurve) : ""), [anchorCurve, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const graphPostPath = useMemo(() => (graphPost ? pathOf(graphPost) : ""), [graphPost, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterPostPath = useMemo(() => (filterPost ? pathOf(filterPost) : ""), [filterPost, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterPredPath = useMemo(() => (filterPred ? pathOf(filterPred) : ""), [filterPred, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  // Credible-band area: forward along the high edge, back along the low edge.
  const bandPathOf = (lo: SmilePoint[] | null, hi: SmilePoint[] | null): string => {
    if (!lo || !hi || lo.length === 0 || hi.length === 0) return "";
    let d = "";
    for (const p of hi) {
      const x = xScale.map(tx(p.k));
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    for (let i = lo.length - 1; i >= 0; i--) {
      const p = lo[i];
      d += `L${xScale.map(tx(p.k)).toFixed(2)},${yScale.map(p.vol).toFixed(2)}`;
    }
    return d + "Z";
  };
  const graphBandPath = useMemo(() => bandPathOf(graphBandLo, graphBandHi), [graphBandLo, graphBandHi, xScale, yScale, tx]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterBandPath = useMemo(() => bandPathOf(filterBandLo, filterBandHi), [filterBandLo, filterBandHi, xScale, yScale, tx]); // eslint-disable-line react-hooks/exhaustive-deps

  // X ticks: nice values in display units, placed directly on the display scale.
  const xTicks = useMemo(
    () => axisDisplayTicks(axisMode, xView[0], xView[1], 6).map((d) => ({ x: xScale.map(d.value), label: d.label })),
    [axisMode, xView, xScale],
  );
  const yTicks = niceTicks(yScale.domain[0], yScale.domain[1], 6);
  const zeroX = useMemo(() => {
    const X0 = axisTransform(axisMode, 0, axisCtx);
    const lo = Math.min(xView[0], xView[1]);
    const hi = Math.max(xView[0], xView[1]);
    return X0 >= lo && X0 <= hi ? xScale.map(X0) : null;
  }, [axisMode, axisCtx, xView, xScale]);

  /* ---------------- wheel zoom (native, non-passive) ---------------- */

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      if (plotW <= 0 || plotH <= 0) return;
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const fx = clamp((e.clientX - rect.left - MARGIN.left) / plotW, 0, 1);
      const fy = clamp((e.clientY - rect.top - MARGIN.top) / plotH, 0, 1);
      const axis = e.shiftKey ? "x" : e.altKey ? "y" : "both";
      zoom.zoomAt(fx, fy, e.deltaY, axis);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom, plotW, plotH]);

  /* ---------------- hover + drag-pan ---------------- */

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    // Hover readout.
    if (px < 0 || px > plotW) setHoverK(null);
    else {
      const k = axisInvert(axisMode, xScale.invert(px), axisCtx);
      setHoverK(k !== null && Number.isFinite(k) ? k : null);
    }
    // Drag-pan.
    const d = drag.current;
    if (d && plotW > 0 && plotH > 0) {
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        zoom.panBy(dx / plotW, dy / plotH, "both");
        drag.current = { x: e.clientX, y: e.clientY, moved: true };
      }
    }
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved) onQuoteSelect?.(null); // a plain click clears selection
  };
  const onPointerLeave = () => {
    setHoverK(null);
    drag.current = null;
  };

  const hoverVol = hoverK !== null ? volAt(model, hoverK) : null;
  const hoverX = hoverK !== null ? xScale.map(tx(hoverK)) : 0;
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
        {prior.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Prior
          </span>
        )}
        {scenarioPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dotted border-amber-400" /> SSR scenario
          </span>
        )}
        {massiveIv && massiveIv.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" /> Massive IV
          </span>
        )}
        {varSwapLevel !== null && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-teal-400" /> Var-swap
          </span>
        )}
        {graphPostPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded" style={{ background: "rgb(167 139 250)" }} /> Graph extrapolation
          </span>
        )}
        {filterPostPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded" style={{ background: "rgb(20 184 166)" }} /> Filter
          </span>
        )}
        {filterPredPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-teal-300" /> Filter pred
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-600">scroll: zoom · drag: pan · dbl-click: reset</span>
      </div>

      {/* Plot area (measured for responsive SVG) */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className="absolute inset-0 cursor-crosshair touch-none select-none"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerLeave}
            onDoubleClick={zoom.reset}
          >
            <defs>
              <clipPath id={clipId}>
                <rect x={0} y={0} width={plotW} height={plotH} />
              </clipPath>
            </defs>
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {/* Gridlines */}
              {yTicks.map((tv) => (
                <line key={`gy${tv}`} x1={0} x2={plotW} y1={yScale.map(tv)} y2={yScale.map(tv)}
                  stroke="rgb(255 255 255 / 0.05)" />
              ))}
              {xTicks.map((tick, i) => (
                <line key={`gx${i}`} x1={tick.x} x2={tick.x} y1={0} y2={plotH}
                  stroke="rgb(255 255 255 / 0.04)" />
              ))}

              {/* Zero log-moneyness (ATM forward) reference */}
              {zeroX !== null && (
                <line x1={zeroX} x2={zeroX} y1={0} y2={plotH}
                  stroke="rgb(148 163 184 / 0.25)" strokeDasharray="2 4" />
              )}

              {/* Axes labels */}
              {yTicks.map((tv) => (
                <text key={`ly${tv}`} x={-8} y={yScale.map(tv)} dy="0.32em" textAnchor="end"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatPct(tv)}
                </text>
              ))}
              {xTicks.map((tick, i) => (
                <text key={`lx${i}`} x={tick.x} y={plotH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {tick.label}
                </text>
              ))}

              {/* Clipped plot geometry */}
              <g clipPath={`url(#${clipId})`}>
                {/* Variance-swap quote: horizontal teal line at the quoted vol */}
                {varSwapLevel !== null &&
                  varSwapLevel >= yScale.domain[0] &&
                  varSwapLevel <= yScale.domain[1] && (
                    <g pointerEvents="none">
                      <line x1={0} x2={plotW} y1={yScale.map(varSwapLevel)} y2={yScale.map(varSwapLevel)}
                        stroke="rgb(45 212 191 / 0.85)" strokeWidth={1.5} strokeDasharray="6 4" />
                      <text x={plotW - 2} y={yScale.map(varSwapLevel) - 3} textAnchor="end"
                        className="fill-teal-300 font-mono text-[10px]">
                        VS {formatPct(varSwapLevel, 2)}
                      </text>
                    </g>
                  )}

                {/* Quote bands: I-beam bid/ask bars with a mid tick. */}
                {quotes.map((q) => {
                  const x = xScale.map(tx(q.k));
                  if (x < -20 || x > plotW + 20) return null;
                  const yb = yScale.map(q.bid);
                  const ya = yScale.map(q.ask);
                  const ym = yScale.map(q.mid);
                  const cap = 3.5;
                  const selected = selectedIndex !== null && q.index === selectedIndex;
                  // Observed quotes are drawn in bright red, bolder than the fitted
                  // smile, so the market is unmistakable against the model curve.
                  const beamStroke = selected ? "var(--color-accent-400)" : "rgb(248 113 113 / 0.95)";
                  const midStroke = q.amended
                    ? "rgb(251 191 36 / 0.95)"
                    : selected
                      ? "var(--color-accent-400)"
                      : "rgb(248 113 113)";
                  const midHalf = q.amended ? 4 : 2.5;
                  return (
                    <g key={q.index}>
                      {selected && <circle cx={x} cy={ym} r={7} fill="var(--color-accent-400)" opacity={0.18} />}
                      <g stroke={beamStroke} strokeWidth={1.4} opacity={q.excluded ? 0.25 : 1}>
                        <line x1={x} x2={x} y1={yb} y2={ya} />
                        <line x1={x - cap} x2={x + cap} y1={ya} y2={ya} />
                        <line x1={x - cap} x2={x + cap} y1={yb} y2={yb} />
                        <line x1={x - midHalf} x2={x + midHalf} y1={ym} y2={ym} stroke={midStroke} strokeWidth={2.2} />
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
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation();
                            onQuoteSelect(q.index);
                          }}
                        />
                      )}
                    </g>
                  );
                })}

                {/* Prior: saved = dashed slate; active fetched (spot-updated) =
                    dotted teal so it reads as the live, transported prior. */}
                <path
                  d={priorPath}
                  fill="none"
                  stroke={priorTransported ? "rgb(45 212 191 / 0.95)" : "rgb(100 116 139 / 0.9)"}
                  strokeWidth={1.5}
                  strokeDasharray={priorTransported ? "2 3" : "5 4"}
                />

                {/* SSR scenario overlay: dotted amber */}
                {scenarioPath !== "" && (
                  <path d={scenarioPath} fill="none" stroke="rgb(251 191 36 / 0.85)"
                    strokeWidth={1.5} strokeDasharray="2 3" />
                )}

                {/* Pre-transport calibration (anchor smile): dimmed accent */}
                {anchorPath !== "" && (
                  <path d={anchorPath} fill="none" stroke="var(--color-accent-400)"
                    strokeOpacity={0.32} strokeWidth={1.5} strokeLinejoin="round" />
                )}

                {/* Graph-extrapolated reconstruction: shaded credible band + a
                    solid violet posterior curve (plan Phase 5 live overlay). */}
                {graphBandPath !== "" && (
                  <path d={graphBandPath} fill="rgb(167 139 250 / 0.16)" stroke="none" pointerEvents="none" />
                )}
                {graphPostPath !== "" && (
                  <path d={graphPostPath} fill="none" stroke="rgb(167 139 250 / 0.95)"
                    strokeWidth={2} strokeLinejoin="round" pointerEvents="none" />
                )}

                {/* Observation-filter overlay (Note 15): shaded ±1σ band, a
                    dashed lighter one-step prediction and a solid teal
                    filtered-posterior curve. */}
                {filterBandPath !== "" && (
                  <path d={filterBandPath} fill="rgb(20 184 166 / 0.14)" stroke="none" pointerEvents="none" />
                )}
                {filterPredPath !== "" && (
                  <path d={filterPredPath} fill="none" stroke="rgb(94 234 212 / 0.8)"
                    strokeWidth={1.5} strokeDasharray="3 3" pointerEvents="none" />
                )}
                {filterPostPath !== "" && (
                  <path d={filterPostPath} fill="none" stroke="rgb(20 184 166 / 0.95)"
                    strokeWidth={2} strokeLinejoin="round" pointerEvents="none" />
                )}

                {/* Massive IV overlay: read-only cyan dots */}
                {(massiveIv ?? []).map((p, i) => {
                  if (p.vol < yScale.domain[0] || p.vol > yScale.domain[1]) return null;
                  const x = xScale.map(tx(p.k));
                  if (x < 0 || x > plotW) return null;
                  return (
                    <circle key={`miv${i}`} cx={x} cy={yScale.map(p.vol)}
                      r={2} fill="rgb(34 211 238 / 0.85)" pointerEvents="none" />
                  );
                })}

                {/* Current model fit: accent */}
                <path d={modelPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />

                {/* Trigger-gated cue: no model curve yet (never calibrated). */}
                {model.length === 0 && (
                  <text
                    x={plotW / 2}
                    y={18}
                    textAnchor="middle"
                    className="fill-slate-500"
                    style={{ fontSize: 11 }}
                  >
                    {quotes.length === 0
                      ? "No quotes — press Fetch"
                      : "No fit yet — press Calibrate"}
                  </text>
                )}

                {/* Crosshair */}
                {hoverK !== null && hoverVol !== null && (
                  <g pointerEvents="none">
                    <line x1={hoverX} x2={hoverX} y1={0} y2={plotH}
                      stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                    <circle cx={hoverX} cy={yScale.map(hoverVol)} r={3.5}
                      fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1.5} />
                  </g>
                )}
              </g>
            </g>
          </svg>
        )}

        {/* Tooltip readout badge (top-right corner) */}
        {hoverLabel && (
          <div className="pointer-events-none absolute top-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40">
            {hoverLabel}
          </div>
        )}

        {/* Reset-zoom affordance */}
        {zoom.zoomed && (
          <button
            onClick={zoom.reset}
            title="Reset zoom (or double-click the chart)"
            className="absolute bottom-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2 py-0.5 text-[10px] text-slate-300 shadow hover:text-slate-100"
          >
            ⌂ reset
          </button>
        )}
      </div>

      {/* Strike-window brush (coarse, in log-moneyness k) */}
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
