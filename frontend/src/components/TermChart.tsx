// Term-structure chart: two stacked SVG panels sharing one maturity axis.
//   top    ATM vol vs maturity — dense fit curve, per-expiry ATM markers (●)
//          and var-swap vols (◆ joined by a faint line)
//   bottom ATM total variance w = σ²·t — visibly nondecreasing when the
//          ladder is calendar-arbitrage-free
// The x axis is real time t or event-dilated time τ; in dilated mode each
// enabled event is drawn as a faint dashed vertical at its dilated position.
// Hand-rolled SVG, no chart deps; conventions match SmileChart.
import { useLayoutEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type {
  ClockMode,
  DividendMarker,
  TermCurve,
  TermEvent,
  TermPoint,
} from "../state/useTerm";
import type { LinearScale } from "../lib/chartScale";
import {
  clamp,
  formatAxisNumber,
  formatPct,
  linearScale,
  niceTicks,
} from "../lib/chartScale";

interface TermChartProps {
  points: TermPoint[];
  curve: TermCurve;
  /** Event markers, drawn on the dilated axis when enabled. */
  events: TermEvent[];
  eventsEnabled: boolean;
  axisClock: ClockMode;
  /** Discrete dividend ex-dates, drawn on both clocks. */
  dividends: DividendMarker[];
}

const MARGIN = { top: 14, right: 14, bottom: 44, left: 56 } as const;
/** Vertical gap between the vol panel and the variance panel. */
const PANEL_GAP = 30;
/** Height share of the top (ATM vol) panel. */
const TOP_SHARE = 0.55;

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

/** Linear interpolation of ys over ascending xs; clamped at the ends. */
function interp(xs: number[], ys: number[], x: number): number | null {
  const n = Math.min(xs.length, ys.length);
  if (n === 0) return null;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  for (let i = 1; i < n; i++) {
    if (x <= xs[i]) {
      const f = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return ys[i - 1] + f * (ys[i] - ys[i - 1]);
    }
  }
  return ys[n - 1];
}

export default function TermChart({
  points,
  curve,
  events,
  eventsEnabled,
  axisClock,
  dividends,
}: TermChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Hover position in x-domain units (t or τ), or null when outside. */
  const [hover, setHover] = useState<number | null>(null);

  const dilated = axisClock === "dilated";
  const curveX = dilated ? curve.tau : curve.t;
  const xOf = (p: TermPoint) => (dilated ? p.tau : p.t);

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);
  const topH = Math.max(0, (innerH - PANEL_GAP) * TOP_SHARE);
  const botH = Math.max(0, innerH - PANEL_GAP - topH);
  const botY0 = topH + PANEL_GAP;

  // ---- domains. Tiny arrays (~80 curve samples): recomputed per render ----
  let xLo = Infinity;
  let xHi = -Infinity;
  for (const x of curveX) { xLo = Math.min(xLo, x); xHi = Math.max(xHi, x); }
  for (const p of points) { xLo = Math.min(xLo, xOf(p)); xHi = Math.max(xHi, xOf(p)); }
  if (!Number.isFinite(xLo)) { xLo = 0; xHi = 1; }
  if (xLo === xHi) { xLo -= 0.5; xHi += 0.5; }

  let vLo = Infinity;
  let vHi = -Infinity;
  for (const v of curve.vol) { vLo = Math.min(vLo, v); vHi = Math.max(vHi, v); }
  for (const p of points) {
    vLo = Math.min(vLo, p.atmVol, p.varSwapVol);
    vHi = Math.max(vHi, p.atmVol, p.varSwapVol);
  }
  if (!Number.isFinite(vLo)) { vLo = 0; vHi = 1; }
  const vPad = Math.max(1e-4, (vHi - vLo) * 0.1);

  let wLo = Infinity;
  let wHi = -Infinity;
  for (const w of curve.w) { wLo = Math.min(wLo, w); wHi = Math.max(wHi, w); }
  for (const p of points) { wLo = Math.min(wLo, p.w0); wHi = Math.max(wHi, p.w0); }
  if (!Number.isFinite(wLo)) { wLo = 0; wHi = 1; }
  const wPad = Math.max(1e-6, (wHi - wLo) * 0.1);

  const xScale = linearScale([xLo, xHi], [0, plotW]);
  const volScale = linearScale([vLo - vPad, vHi + vPad], [topH, 0]);
  const wScale = linearScale([Math.max(0, wLo - wPad), wHi + wPad], [botH, 0]);

  /** SVG path through (xs[i], ys[i]) in a panel's local coordinates. */
  const pathOf = (xs: number[], ys: number[], y: LinearScale): string => {
    let d = "";
    const n = Math.min(xs.length, ys.length);
    for (let i = 0; i < n; i++) {
      d += `${d === "" ? "M" : "L"}${xScale.map(xs[i]).toFixed(2)},${y.map(ys[i]).toFixed(2)}`;
    }
    return d;
  };

  const sorted = [...points].sort((a, b) => xOf(a) - xOf(b));
  const volPath = pathOf(curveX, curve.vol, volScale);
  const wPath = pathOf(curveX, curve.w, wScale);
  const vsPath = pathOf(sorted.map(xOf), sorted.map((p) => p.varSwapVol), volScale);

  const xTicks = niceTicks(xLo, xHi, 8);
  const volTicks = niceTicks(volScale.domain[0], volScale.domain[1], 5);
  const wTicks = niceTicks(wScale.domain[0], wScale.domain[1], 5);

  // Events on the dilated axis: real event time mapped through t -> τ.
  const eventMarks =
    dilated && eventsEnabled
      ? events
          .map((ev) => ({ ev, x: interp(curve.t, curve.tau, ev.time) }))
          .filter(
            (m): m is { ev: TermEvent; x: number } =>
              m.x !== null && m.x >= xLo && m.x <= xHi,
          )
      : [];

  // Dividend ex-dates: drawn on both clocks at their real-time (t) or
  // dilated (τ) position, which the backend supplies for each marker.
  const divMarks = dividends
    .map((d) => ({ d, x: dilated ? d.tau : d.t }))
    .filter((m) => m.x >= xLo && m.x <= xHi);

  /* ---------------- crosshair ---------------- */

  const onMouseMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const px = e.clientX - svg.getBoundingClientRect().left - MARGIN.left;
    if (px < 0 || px > plotW) { setHover(null); return; }
    setHover(clamp(xScale.invert(px), xLo, xHi));
  };

  const hoverVol = hover !== null ? interp(curveX, curve.vol, hover) : null;
  const hoverW = hover !== null ? interp(curveX, curve.w, hover) : null;
  const hoverPx = hover !== null ? xScale.map(hover) : 0;
  const hoverLabel =
    hover !== null && hoverVol !== null && hoverW !== null
      ? `${dilated ? "τ" : "t"} ${hover.toFixed(2)}y · σ ${formatPct(hoverVol, 2)} · w ${hoverW.toFixed(4)}`
      : null;

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-5 px-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-accent-400" /> Fit (vol / variance)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent-400" /> Per-expiry ATM
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rotate-45 bg-sky-400/80" /> Var-swap
        </span>
        {eventMarks.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-0 border-l border-dashed border-amber-400/70" /> Events
          </span>
        )}
        {divMarks.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-0 border-l border-dashed border-emerald-400/70" /> Dividends
          </span>
        )}
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
            onMouseLeave={() => setHover(null)}
          >
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {/* ---- top panel: ATM vol ---- */}
              <g>
                {volTicks.map((t) => (
                  <line key={`gv${t}`} x1={0} x2={plotW} y1={volScale.map(t)} y2={volScale.map(t)}
                    stroke="rgb(255 255 255 / 0.05)" />
                ))}
                {xTicks.map((t) => (
                  <line key={`gxv${t}`} x1={xScale.map(t)} x2={xScale.map(t)} y1={0} y2={topH}
                    stroke="rgb(255 255 255 / 0.04)" />
                ))}
                {volTicks.map((t) => (
                  <text key={`lv${t}`} x={-8} y={volScale.map(t)} dy="0.32em" textAnchor="end"
                    className="fill-slate-500 font-mono text-[10px]">
                    {formatPct(t)}
                  </text>
                ))}
                <text x={4} y={11} className="fill-slate-600 font-mono text-[9px]">
                  ATM vol
                </text>

                {/* Var-swap vols: faint connecting line + diamond markers */}
                <path d={vsPath} fill="none" stroke="rgb(56 189 248 / 0.3)" strokeWidth={1} />
                {sorted.map((p) => {
                  const x = xScale.map(xOf(p));
                  const y = volScale.map(p.varSwapVol);
                  return (
                    <path key={`vs-${p.expiry}`}
                      d={`M${x},${y - 3}L${x + 3},${y}L${x},${y + 3}L${x - 3},${y}Z`}
                      fill="rgb(56 189 248 / 0.8)" />
                  );
                })}

                {/* Dense ATM-vol fit + per-expiry markers */}
                <path d={volPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />
                {points.map((p) => (
                  <circle key={`atm-${p.expiry}`} cx={xScale.map(xOf(p))} cy={volScale.map(p.atmVol)}
                    r={3} fill="var(--color-accent-400)" stroke="#0e131c" strokeWidth={1} />
                ))}
              </g>

              {/* ---- bottom panel: ATM total variance ---- */}
              <g transform={`translate(0,${botY0})`}>
                {wTicks.map((t) => (
                  <line key={`gw${t}`} x1={0} x2={plotW} y1={wScale.map(t)} y2={wScale.map(t)}
                    stroke="rgb(255 255 255 / 0.05)" />
                ))}
                {xTicks.map((t) => (
                  <line key={`gxw${t}`} x1={xScale.map(t)} x2={xScale.map(t)} y1={0} y2={botH}
                    stroke="rgb(255 255 255 / 0.04)" />
                ))}
                {wTicks.map((t) => (
                  <text key={`lw${t}`} x={-8} y={wScale.map(t)} dy="0.32em" textAnchor="end"
                    className="fill-slate-500 font-mono text-[10px]">
                    {t.toFixed(4)}
                  </text>
                ))}
                <text x={4} y={11} className="fill-slate-600 font-mono text-[9px]">
                  total variance w
                </text>

                <path d={wPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />
                {points.map((p) => (
                  <circle key={`w0-${p.expiry}`} cx={xScale.map(xOf(p))} cy={wScale.map(p.w0)}
                    r={3} fill="var(--color-accent-400)" stroke="#0e131c" strokeWidth={1} />
                ))}
              </g>

              {/* Shared x-axis labels + title (under the bottom panel) */}
              {xTicks.map((t) => (
                <text key={`lx${t}`} x={xScale.map(t)} y={botY0 + botH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatAxisNumber(t)}
                </text>
              ))}
              <text x={plotW / 2} y={botY0 + botH + 32} textAnchor="middle"
                className="fill-slate-500 font-mono text-[10px]">
                {dilated ? "dilated maturity τ (years)" : "maturity (years)"}
              </text>

              {/* Dividend ex-dates: emerald dashed verticals + cash label */}
              {divMarks.map(({ d, x }) => {
                const px = xScale.map(x);
                return (
                  <g key={`div-${d.exDate}`} pointerEvents="none">
                    <line x1={px} x2={px} y1={0} y2={botY0 + botH}
                      stroke="rgb(52 211 153 / 0.35)" strokeDasharray="2 4" />
                    <text x={px + 4} y={botY0 + botH - 4}
                      className="fill-emerald-400/70 font-mono text-[9px]">
                      ${d.amount}
                    </text>
                  </g>
                );
              })}

              {/* Event markers: dashed verticals at the dilated positions */}
              {eventMarks.map(({ ev, x }) => {
                const px = xScale.map(x);
                return (
                  <g key={ev.id} pointerEvents="none">
                    <line x1={px} x2={px} y1={0} y2={botY0 + botH}
                      stroke="rgb(251 191 36 / 0.35)" strokeDasharray="3 4" />
                    <text x={px + 4} y={9} className="fill-amber-400/70 font-mono text-[9px]">
                      {ev.label}
                    </text>
                  </g>
                );
              })}

              {/* Crosshair: vertical guide + markers on both fit curves */}
              {hover !== null && hoverVol !== null && hoverW !== null && (
                <g pointerEvents="none">
                  <line x1={hoverPx} x2={hoverPx} y1={0} y2={botY0 + botH}
                    stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                  <circle cx={hoverPx} cy={volScale.map(hoverVol)} r={3.5}
                    fill="var(--color-accent-400)" stroke="#0e131c" strokeWidth={1.5} />
                  <circle cx={hoverPx} cy={botY0 + wScale.map(hoverW)} r={3.5}
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
    </div>
  );
}
