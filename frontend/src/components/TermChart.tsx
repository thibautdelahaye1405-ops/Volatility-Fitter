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
import { timeAxisValue } from "../lib/timeAxis";
import type { TimeAxisMode } from "../lib/timeAxis";

interface TermChartProps {
  points: TermPoint[];
  curve: TermCurve;
  /** Event markers, drawn on the dilated axis when enabled. */
  events: TermEvent[];
  eventsEnabled: boolean;
  axisClock: ClockMode;
  /** Discrete dividend ex-dates, drawn on both clocks. */
  dividends: DividendMarker[];
  /** Expiry currently selected for var-swap editing (highlighted), or null. */
  selectedExpiry?: string | null;
  /** Select an expiry by clicking its ATM marker (var-swap editing). */
  onSelectExpiry?: (expiry: string) => void;
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
  selectedExpiry = null,
  onSelectExpiry,
}: TermChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Hover position in x-domain units (t or τ), or null when outside. */
  const [hover, setHover] = useState<number | null>(null);
  /** Maturity-axis scaling: linear T or √T. */
  const [timeMode, setTimeMode] = useState<TimeAxisMode>("linear");

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
    if (p.varSwapQuote != null) {
      vLo = Math.min(vLo, p.varSwapQuote);
      vHi = Math.max(vHi, p.varSwapQuote);
    }
  }
  if (!Number.isFinite(vLo)) { vLo = 0; vHi = 1; }
  const vPad = Math.max(1e-4, (vHi - vLo) * 0.1);

  // Forward (annualized) variance between consecutive expiries: Δw / Δx on the
  // active clock — the level of each [x_{k-1}, x_k] interval (the first runs
  // from the origin). A negative level means total variance fell between two
  // expiries, i.e. a calendar-arbitrage interval (drawn below the zero line).
  const fwdSorted = [...points].sort((a, b) => xOf(a) - xOf(b));
  const fwdSegments: { x0: number; x1: number; level: number }[] = [];
  {
    let prevX = 0;
    let prevW = 0;
    for (const p of fwdSorted) {
      const x = xOf(p);
      const dx = x - prevX;
      fwdSegments.push({ x0: prevX, x1: x, level: dx > 1e-9 ? (p.w0 - prevW) / dx : 0 });
      prevX = x;
      prevW = p.w0;
    }
  }
  /** Forward variance at x (piecewise-constant step lookup). */
  const fwdAt = (x: number): number | null => {
    for (const s of fwdSegments) if (x <= s.x1) return s.level;
    return fwdSegments.length ? fwdSegments[fwdSegments.length - 1].level : null;
  };

  let wLo = 0;
  let wHi = -Infinity;
  for (const s of fwdSegments) { wLo = Math.min(wLo, s.level); wHi = Math.max(wHi, s.level); }
  if (!Number.isFinite(wHi)) { wLo = 0; wHi = 1; }
  const wPad = Math.max(1e-6, (wHi - wLo) * 0.1);

  // Maturity axis honours the T / √T toggle: positions go through xpos, labels
  // stay in years. xPosScale maps positions to pixels; X maps a t/τ value.
  const xpos = (v: number) => timeAxisValue(v, timeMode);
  const xposInv = (pos: number) => (timeMode === "sqrt" ? pos * pos : pos);
  const xPosScale = linearScale([xpos(xLo), xpos(xHi)], [0, plotW]);
  const X = (v: number) => xPosScale.map(xpos(v));
  const volScale = linearScale([vLo - vPad, vHi + vPad], [topH, 0]);
  const wScale = linearScale([wLo - wPad, wHi + wPad], [botH, 0]);

  /** SVG path through (xs[i], ys[i]) in a panel's local coordinates. */
  const pathOf = (xs: number[], ys: number[], y: LinearScale): string => {
    let d = "";
    const n = Math.min(xs.length, ys.length);
    for (let i = 0; i < n; i++) {
      d += `${d === "" ? "M" : "L"}${X(xs[i]).toFixed(2)},${y.map(ys[i]).toFixed(2)}`;
    }
    return d;
  };

  const sorted = [...points].sort((a, b) => xOf(a) - xOf(b));
  const volPath = pathOf(curveX, curve.vol, volScale);
  // Step path of the forward-variance levels (vertical risers at each expiry).
  let wPath = "";
  fwdSegments.forEach((seg, i) => {
    const y = wScale.map(seg.level).toFixed(2);
    const xa = X(seg.x0).toFixed(2);
    const xb = X(seg.x1).toFixed(2);
    wPath += `${i === 0 ? "M" : "L"}${xa},${y}L${xb},${y}`;
  });
  const vsPath = pathOf(sorted.map(xOf), sorted.map((p) => p.varSwapVol), volScale);
  // Active fetched prior's ATM term (dotted teal, spot-updated), where present.
  const priorPts = sorted.filter((p) => p.priorVol != null);
  const priorPath = pathOf(
    priorPts.map(xOf),
    priorPts.map((p) => p.priorVol as number),
    volScale,
  );

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
    setHover(clamp(xposInv(xPosScale.invert(px)), xLo, xHi));
  };

  const hoverVol = hover !== null ? interp(curveX, curve.vol, hover) : null;
  const hoverFwd = hover !== null ? fwdAt(hover) : null;
  const hoverPx = hover !== null ? X(hover) : 0;
  const hoverLabel =
    hover !== null && hoverVol !== null && hoverFwd !== null
      ? `${dilated ? "τ" : "t"} ${hover.toFixed(2)}y · σ ${formatPct(hoverVol, 2)} · fwd var ${hoverFwd.toFixed(4)}`
      : null;

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-5 px-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-accent-400" /> Fit σ(T) · fwd variance
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent-400" /> Per-expiry ATM
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rotate-45 bg-sky-400/80" /> Var-swap (model)
        </span>
        {points.some((p) => p.varSwapQuote != null) && (
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full border-2 border-teal-400" /> Var-swap quote
          </span>
        )}
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
        {/* Maturity-axis scaling toggle: linear T vs √T */}
        <div className="ml-auto flex overflow-hidden rounded border border-slate-700">
          {(["linear", "sqrt"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setTimeMode(m)}
              title={m === "sqrt" ? "√T axis (ATM vol ~ linear in √T)" : "Linear maturity axis"}
              className={[
                "px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                timeMode === m ? "bg-accent-600/25 text-accent-400" : "text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {m === "sqrt" ? "√T" : "T"}
            </button>
          ))}
        </div>
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
                  <line key={`gxv${t}`} x1={X(t)} x2={X(t)} y1={0} y2={topH}
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
                  const x = X(xOf(p));
                  const y = volScale.map(p.varSwapVol);
                  return (
                    <path key={`vs-${p.expiry}`}
                      d={`M${x},${y - 3}L${x + 3},${y}L${x},${y + 3}L${x - 3},${y}Z`}
                      fill="rgb(56 189 248 / 0.8)" />
                  );
                })}

                {/* Var-swap QUOTES: hollow teal rings (excluded = dimmed),
                    clickable to select the expiry for editing */}
                {points.map((p) =>
                  p.varSwapQuote == null ? null : (
                    <circle
                      key={`vsq-${p.expiry}`}
                      cx={X(xOf(p))}
                      cy={volScale.map(p.varSwapQuote)}
                      r={5}
                      fill="none"
                      stroke="rgb(45 212 191 / 0.95)"
                      strokeWidth={1.6}
                      opacity={p.varSwapExcluded ? 0.35 : 1}
                    />
                  ),
                )}

                {/* Active fetched prior's ATM term: dotted teal, spot-updated */}
                {priorPath !== "" && (
                  <path d={priorPath} fill="none" stroke="rgb(45 212 191 / 0.95)"
                    strokeWidth={1.5} strokeDasharray="2 3" />
                )}

                {/* Dense ATM-vol fit + per-expiry markers (clickable to select
                    an expiry for var-swap editing) */}
                <path d={volPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />
                {points.map((p) => {
                  const sel = selectedExpiry === p.expiry;
                  return (
                    <g key={`atm-${p.expiry}`}>
                      {sel && (
                        <circle cx={X(xOf(p))} cy={volScale.map(p.atmVol)} r={7}
                          fill="var(--color-accent-400)" opacity={0.18} />
                      )}
                      <circle cx={X(xOf(p))} cy={volScale.map(p.atmVol)}
                        r={3} fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1} />
                      {onSelectExpiry && (
                        <circle cx={X(xOf(p))} cy={volScale.map(p.atmVol)} r={9}
                          fill="transparent" className="cursor-pointer"
                          onClick={() => onSelectExpiry(p.expiry)} />
                      )}
                    </g>
                  );
                })}
              </g>

              {/* ---- bottom panel: forward (annualized) variance ---- */}
              <g transform={`translate(0,${botY0})`}>
                {wTicks.map((t) => (
                  <line key={`gw${t}`} x1={0} x2={plotW} y1={wScale.map(t)} y2={wScale.map(t)}
                    stroke="rgb(255 255 255 / 0.05)" />
                ))}
                {xTicks.map((t) => (
                  <line key={`gxw${t}`} x1={X(t)} x2={X(t)} y1={0} y2={botH}
                    stroke="rgb(255 255 255 / 0.04)" />
                ))}
                {wTicks.map((t) => (
                  <text key={`lw${t}`} x={-8} y={wScale.map(t)} dy="0.32em" textAnchor="end"
                    className="fill-slate-500 font-mono text-[10px]">
                    {t.toFixed(4)}
                  </text>
                ))}
                <text x={4} y={11} className="fill-slate-600 font-mono text-[9px]">
                  forward variance
                </text>

                {/* Zero reference (a forward variance below it is calendar arb) */}
                {wScale.domain[0] < 0 && (
                  <line x1={0} x2={plotW} y1={wScale.map(0)} y2={wScale.map(0)}
                    stroke="rgb(248 113 113 / 0.35)" strokeDasharray="2 4" />
                )}

                {/* Forward-variance step + a marker at each interval's level */}
                <path d={wPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />
                {fwdSegments.map((seg) => (
                  <circle key={`fw-${seg.x1}`} cx={X(seg.x1)} cy={wScale.map(seg.level)}
                    r={3} fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1} />
                ))}
              </g>

              {/* Shared x-axis labels + title (under the bottom panel) */}
              {xTicks.map((t) => (
                <text key={`lx${t}`} x={X(t)} y={botY0 + botH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatAxisNumber(t)}
                </text>
              ))}
              <text x={plotW / 2} y={botY0 + botH + 32} textAnchor="middle"
                className="fill-slate-500 font-mono text-[10px]">
                {dilated ? "dilated maturity τ" : "maturity"}
                {timeMode === "sqrt" ? " · √T axis" : ""} (years)
              </text>

              {/* Dividend ex-dates: emerald dashed verticals + cash label */}
              {divMarks.map(({ d, x }) => {
                const px = X(x);
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
                const px = X(x);
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
              {hover !== null && hoverVol !== null && hoverFwd !== null && (
                <g pointerEvents="none">
                  <line x1={hoverPx} x2={hoverPx} y1={0} y2={botY0 + botH}
                    stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                  <circle cx={hoverPx} cy={volScale.map(hoverVol)} r={3.5}
                    fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1.5} />
                  <circle cx={hoverPx} cy={botY0 + wScale.map(hoverFwd)} r={3.5}
                    fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1.5} />
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
