// Reconstructed-smile chart for the Local Vol workspace.
//
// Plots one expiry's arbitrage-free implied-vol curve (recovered by inverting
// the calibrated Dupire PDE call prices through Black) against its market
// quote band: bid/ask I-beams with a mid dot, excluded quotes dimmed, and the
// fit-target overlay UNDER them (mid polyline / bid-ask / haircut ribbon —
// LocalVolTarget, toggled by the "Target" chip; the mode comes from the smile
// session, like the Parametric chart). Pure SVG, reusing the shared
// linear-scale / tick helpers, with the Parametric smile's FULL interaction
// stack (lib/useChartZoom): wheel-zoom (+Shift x-only / +Alt y-only),
// drag-pan, double-click / ⌂ reset, the Y center / Y fit overlay buttons (the
// y base auto-fits the data inside the x view) and the coarse strike-window
// brush in log-moneyness under the plot.
import { useId, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { AffineSmile } from "../state/useAffine";
import { useSmileSession } from "../state/smileSession";
import { LocalVolTargetChip, LocalVolTargetLayer, useLvShowTarget } from "./LocalVolTarget";
import { formatPct, linearScale, niceTicks } from "../lib/chartScale";
import { useElementSize } from "../lib/useElementSize";
import { useChartZoom } from "../lib/useChartZoom";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import { crosshairLabel, crosshairPoint } from "../lib/crosshair";
import type { CrosshairPoint } from "../lib/crosshair";
import { CrosshairBadge, CrosshairGuides } from "./CrosshairOverlay";
import ZoomOverlay from "./charts/ZoomOverlay";
import RangeBrush from "./RangeBrush";
import {
  axisDisplayTicks,
  axisModeLabel,
  axisTransform,
  formatHoverValue,
  makeVolAt,
} from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";

interface LocalVolSmileProps {
  smile: AffineSmile;
  /** Strike-axis display mode (shared with the Parametric Smile). */
  axisMode?: AxisMode;
  /** Y auto-scale toggles + toggler (the Y center / Y fit buttons). */
  autoScaleY?: AutoScaleToggles;
  onToggleAutoScale?: (key: keyof AutoScaleToggles) => void;
}

const MARGIN = { top: 10, right: 14, bottom: 28, left: 44 };

export default function LocalVolSmile({
  smile,
  axisMode = "logmoneyness",
  autoScaleY,
  onToggleAutoScale,
}: LocalVolSmileProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const clipId = useId();
  /** Crosshair position, or null when the pointer is outside / panning. */
  const [cross, setCross] = useState<CrosshairPoint | null>(null);
  // The viewed fit target (mid / bid-ask / haircut) is the session's, exactly
  // the mode the LV surface was read in (useAffine posts the same fitMode).
  const { fitMode } = useSmileSession();
  const [showTarget, setShowTarget] = useLvShowTarget();

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Geometry is plotted in the SELECTED display coordinate (like the Parametric
  // Smile): tx maps log-moneyness k to the chosen axis (strike / %ATM / Δ / …).
  const modelVolAt = makeVolAt(smile.model);
  const axisCtx = {
    forward: smile.forward ?? 0,
    t: smile.t,
    atmVol: modelVolAt(0) ?? smile.model[0]?.vol ?? 0,
    volAt: modelVolAt,
    kRange: [smile.model[0]?.k ?? -1, smile.model[smile.model.length - 1]?.k ?? 1] as [
      number,
      number,
    ],
  };
  const tx = (k: number): number =>
    axisMode === "logmoneyness" ? k : axisTransform(axisMode, k, axisCtx);

  // Coarse strike window (log-moneyness k) over the data extent — the brush
  // under the plot; reset when the chart moves to another expiry (adjusted
  // during render so the previous window never paints).
  const ks = [...smile.model.map((p) => p.k), ...smile.quotes.map((q) => q.k)];
  const fullRange: [number, number] = [Math.min(...ks), Math.max(...ks)];
  const [kWindow, setKWindow] = useState<[number, number]>(fullRange);
  const [prevExpiry, setPrevExpiry] = useState(smile.expiry);
  if (smile.expiry !== prevExpiry) {
    setPrevExpiry(smile.expiry);
    setKWindow(fullRange);
  }
  const [kLo, kHi] = kWindow;
  const baseX: [number, number] = [Math.min(tx(kLo), tx(kHi)), Math.max(tx(kLo), tx(kHi))];

  const cz = useChartZoom(svgRef, {
    plotW, plotH, marginLeft: MARGIN.left, marginTop: MARGIN.top,
    autoScaleY, xBaseKey: `${baseX[0]},${baseX[1]},${axisMode}`,
  });
  const { zoom } = cz;

  // Scales: x = the brushed window in display units, zoomed; y auto-fits the
  // curve, the quotes and the var-swap level inside the x view, then zoomed.
  const [vkLo, vkHi] = zoom.viewX(baseX);
  const inView = (k: number) => {
    const X = tx(k);
    return X >= Math.min(vkLo, vkHi) && X <= Math.max(vkLo, vkHi);
  };
  const vsLevel =
    smile.varSwap.enabled && !smile.varSwap.excluded ? smile.varSwap.level : null;
  let vMin = Infinity;
  let vMax = -Infinity;
  for (const p of smile.model) if (inView(p.k)) { vMin = Math.min(vMin, p.vol); vMax = Math.max(vMax, p.vol); }
  for (const p of smile.prior ?? []) if (inView(p.k)) { vMin = Math.min(vMin, p.vol); vMax = Math.max(vMax, p.vol); }
  for (const q of smile.quotes) if (inView(q.k)) { vMin = Math.min(vMin, q.bid); vMax = Math.max(vMax, q.ask); }
  if (vsLevel !== null) { vMin = Math.min(vMin, vsLevel); vMax = Math.max(vMax, vsLevel); }
  if (!(vMin <= vMax)) {
    // Nothing in view (a window beyond the data): fall back to the full extent.
    vMin = Math.min(...smile.model.map((p) => p.vol), ...smile.quotes.map((q) => q.bid));
    vMax = Math.max(...smile.model.map((p) => p.vol), ...smile.quotes.map((q) => q.ask));
  }
  const pad = (vMax - vMin) * 0.12 || 0.01;
  const [vvLo, vvHi] = zoom.viewY([vMin - pad, vMax + pad]);
  const x = linearScale([vkLo, vkHi], [MARGIN.left, MARGIN.left + plotW]);
  const y = linearScale([vvLo, vvHi], [MARGIN.top + plotH, MARGIN.top]);

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => cz.beginDrag(e);
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    // Crosshair rides the same handler (hover-only, hidden while panning).
    // This chart's scales run in full-SVG pixels, so the inverts add the
    // margin back onto the plot-local coordinates the helper works in.
    if (cz.dragMove(e)) {
      setCross(null);
      return;
    }
    setCross(
      crosshairPoint(e.clientX, e.clientY, svg.getBoundingClientRect(), MARGIN,
        plotW, plotH, (p) => x.invert(p + MARGIN.left), (p) => y.invert(p + MARGIN.top)),
    );
  };
  const onPointerUp = () => cz.endDrag();
  const onPointerLeave = () => {
    cz.cancelDrag();
    setCross(null);
  };

  const path = smile.model
    .map((p, i) => `${i === 0 ? "M" : "L"}${x.map(tx(p.k)).toFixed(1)},${y.map(p.vol).toFixed(1)}`)
    .join("");

  // Active fetched prior, spot-updated (dotted teal), if present.
  const priorPath = (smile.prior ?? [])
    .map((p, i) => `${i === 0 ? "M" : "L"}${x.map(tx(p.k)).toFixed(1)},${y.map(p.vol).toFixed(1)}`)
    .join("");

  const ready = plotW > 0 && plotH > 0 && smile.model.length > 1;

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div ref={ref} className="relative min-h-0 flex-1">
        {ready && (
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
                <rect x={MARGIN.left} y={MARGIN.top} width={plotW} height={plotH} />
              </clipPath>
            </defs>
            {/* Y grid + labels (vol %) */}
            {niceTicks(vvLo, vvHi, 5).map((v) => (
              <g key={`y-${v}`}>
                <line x1={MARGIN.left} x2={MARGIN.left + plotW} y1={y.map(v)} y2={y.map(v)}
                  stroke="rgb(148 163 184 / 0.12)" />
                <text x={MARGIN.left - 6} y={y.map(v) + 3} textAnchor="end"
                  className="fill-slate-500 font-mono text-[9px]">
                  {formatPct(v)}
                </text>
              </g>
            ))}

            {/* X labels (in the selected display coordinate) */}
            {axisDisplayTicks(axisMode, vkLo, vkHi, 6).map((t) => (
              <text key={`x-${t.value}`} x={x.map(t.value)} y={size.height - 14} textAnchor="middle"
                className="fill-slate-500 font-mono text-[9px]">
                {t.label}
              </text>
            ))}
            <text x={MARGIN.left + plotW / 2} y={size.height - 2} textAnchor="middle"
              className="fill-slate-600 font-mono text-[9px]">
              {axisMode === "logmoneyness" ? "k = log(K/F)" : axisModeLabel(axisMode)}
            </text>

            <g clipPath={`url(#${clipId})`}>
              {/* Fit-target overlay, under the quotes (same axis mapping). */}
              <LocalVolTargetLayer
                quotes={smile.quotes} fitMode={fitMode} show={showTarget}
                toX={(k) => x.map(tx(k))} toY={(v) => y.map(v)}
              />
              {/* Quote I-beams (bid/ask) with mid dot. Observed quotes are bright
                  red and bolder than the fitted smile so the market stands out. */}
              {smile.quotes.map((q) => {
                const cx = x.map(tx(q.k));
                const dim = q.excluded;
                const color = dim
                  ? "rgb(100 116 139)"
                  : q.amended
                    ? "rgb(251 191 36)"
                    : "rgb(248 113 113)";
                return (
                  <g key={q.index} opacity={dim ? 0.35 : 1}>
                    <line x1={cx} x2={cx} y1={y.map(q.bid)} y2={y.map(q.ask)} stroke={color} strokeWidth={1.4} />
                    <circle cx={cx} cy={y.map(q.mid)} r={2.6} fill={color} />
                  </g>
                );
              })}

              {/* Variance-swap quote: horizontal teal line at the quoted vol */}
              {vsLevel !== null && vsLevel >= vvLo && vsLevel <= vvHi && (
                <g>
                  <line x1={MARGIN.left} x2={MARGIN.left + plotW} y1={y.map(vsLevel)} y2={y.map(vsLevel)}
                    stroke="rgb(45 212 191 / 0.85)" strokeWidth={1.5} strokeDasharray="6 4" />
                  <text x={MARGIN.left + plotW - 2} y={y.map(vsLevel) - 3} textAnchor="end"
                    className="fill-teal-300 font-mono text-[9px]">
                    VS {formatPct(vsLevel, 2)}
                  </text>
                </g>
              )}

              {/* Active fetched prior (spot-updated): dotted teal */}
              {priorPath !== "" && (
                <path d={priorPath} fill="none" stroke="rgb(45 212 191 / 0.95)"
                  strokeWidth={1.5} strokeDasharray="2 3" />
              )}

              {/* Reconstructed model curve */}
              <path d={path} fill="none" stroke="rgb(56 189 248)" strokeWidth={1.75} />
            </g>

            {/* Crosshair guides (hover-only; the SVG has no translated plot
                group, so wrap the plot-local guides in one). */}
            {cross !== null && (
              <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
                <CrosshairGuides point={cross} plotW={plotW} plotH={plotH} />
              </g>
            )}
          </svg>
        )}

        {ready && (
          <LocalVolTargetChip on={showTarget} fitMode={fitMode} onToggle={setShowTarget} />
        )}

        {/* Crosshair readout badge (x in the display coordinate, y in vol) */}
        {cross !== null && (
          <CrosshairBadge
            label={crosshairLabel(cross, (v) => formatHoverValue(axisMode, v), (v) => `σ ${formatPct(v, 2)}`)}
          />
        )}

        <ZoomOverlay autoScaleY={autoScaleY} onToggleAutoScale={onToggleAutoScale}
          zoomed={zoom.zoomed} onReset={zoom.reset} left={MARGIN.left} />
      </div>

      {/* Strike-window brush (coarse, in log-moneyness k) */}
      <div className="mt-2 shrink-0 px-1">
        <RangeBrush min={fullRange[0]} max={fullRange[1]} value={kWindow} onChange={setKWindow}
          format={(v) => v.toFixed(2)} />
      </div>
    </div>
  );
}
