// Reconstructed-smile chart for the Local Vol workspace.
//
// Plots one expiry's arbitrage-free implied-vol curve (recovered by inverting
// the calibrated Dupire PDE call prices through Black) against its market
// quote band: bid/ask I-beams with a mid dot, excluded quotes dimmed. Pure
// SVG, reusing the shared linear-scale / tick helpers. Wheel-zoom (x; +Shift
// x-only, +Alt y-only — default both), drag-pan and double-click / ⌂ reset,
// matching the Parametric smile.
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { AffineSmile } from "../state/useAffine";
import { clamp, formatPct, linearScale, niceTicks } from "../lib/chartScale";
import { useZoom } from "../lib/useZoom";

interface LocalVolSmileProps {
  smile: AffineSmile;
}

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

const MARGIN = { top: 10, right: 14, bottom: 28, left: 44 };

export default function LocalVolSmile({ smile }: LocalVolSmileProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const clipId = useId();
  const zoom = useZoom();
  const drag = useRef<{ x: number; y: number } | null>(null);

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  const ks = smile.model.map((p) => p.k);
  const vols = smile.model.map((p) => p.vol);
  const kMin = Math.min(...ks, ...smile.quotes.map((q) => q.k));
  const kMax = Math.max(...ks, ...smile.quotes.map((q) => q.k));
  const vsLevel =
    smile.varSwap.enabled && !smile.varSwap.excluded ? smile.varSwap.level : null;
  let vMin = Math.min(...vols, ...smile.quotes.map((q) => q.bid), ...(vsLevel !== null ? [vsLevel] : []));
  let vMax = Math.max(...vols, ...smile.quotes.map((q) => q.ask), ...(vsLevel !== null ? [vsLevel] : []));
  const pad = (vMax - vMin) * 0.12 || 0.01;
  vMin -= pad;
  vMax += pad;

  // Apply zoom to the base domains.
  const [vkLo, vkHi] = zoom.viewX([kMin, kMax]);
  const [vvLo, vvHi] = zoom.viewY([vMin, vMax]);
  const x = linearScale([vkLo, vkHi], [MARGIN.left, MARGIN.left + plotW]);
  const y = linearScale([vvLo, vvHi], [MARGIN.top + plotH, MARGIN.top]);

  // Wheel zoom (native, non-passive so preventDefault works).
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

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || plotW <= 0 || plotH <= 0) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) {
      zoom.panBy(dx / plotW, dy / plotH, "both");
      drag.current = { x: e.clientX, y: e.clientY };
    }
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const path = smile.model
    .map((p, i) => `${i === 0 ? "M" : "L"}${x.map(p.k).toFixed(1)},${y.map(p.vol).toFixed(1)}`)
    .join("");

  // Active fetched prior, spot-updated (dotted teal), if present.
  const priorPath = (smile.prior ?? [])
    .map((p, i) => `${i === 0 ? "M" : "L"}${x.map(p.k).toFixed(1)},${y.map(p.vol).toFixed(1)}`)
    .join("");

  const ready = plotW > 0 && plotH > 0 && smile.model.length > 1;

  return (
    <div ref={ref} className="relative h-full min-h-0 w-full">
      {ready && (
        <svg
          ref={svgRef}
          width={size.width}
          height={size.height}
          className="absolute inset-0 cursor-crosshair touch-none select-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
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
              <line
                x1={MARGIN.left}
                x2={MARGIN.left + plotW}
                y1={y.map(v)}
                y2={y.map(v)}
                stroke="rgb(148 163 184 / 0.12)"
              />
              <text
                x={MARGIN.left - 6}
                y={y.map(v) + 3}
                textAnchor="end"
                className="fill-slate-500 font-mono text-[9px]"
              >
                {formatPct(v)}
              </text>
            </g>
          ))}

          {/* X labels (log-moneyness k) */}
          {niceTicks(vkLo, vkHi, 6).map((v) => (
            <text
              key={`x-${v}`}
              x={x.map(v)}
              y={size.height - 14}
              textAnchor="middle"
              className="fill-slate-500 font-mono text-[9px]"
            >
              {v.toFixed(2)}
            </text>
          ))}
          <text
            x={MARGIN.left + plotW / 2}
            y={size.height - 2}
            textAnchor="middle"
            className="fill-slate-600 font-mono text-[9px]"
          >
            k = log(K/F)
          </text>

          <g clipPath={`url(#${clipId})`}>
            {/* Quote I-beams (bid/ask) with mid dot */}
            {smile.quotes.map((q) => {
              const cx = x.map(q.k);
              const dim = q.excluded;
              const color = dim
                ? "rgb(100 116 139)"
                : q.amended
                  ? "rgb(251 191 36)"
                  : "rgb(148 163 184)";
              return (
                <g key={q.index} opacity={dim ? 0.35 : 1}>
                  <line x1={cx} x2={cx} y1={y.map(q.bid)} y2={y.map(q.ask)} stroke={color} strokeWidth={1} />
                  <circle cx={cx} cy={y.map(q.mid)} r={2} fill={color} />
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
        </svg>
      )}

      {zoom.zoomed && (
        <button
          onClick={zoom.reset}
          title="Reset zoom (or double-click)"
          className="absolute bottom-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2 py-0.5 text-[10px] text-slate-300 shadow hover:text-slate-100"
        >
          ⌂ reset
        </button>
      )}
    </div>
  );
}
