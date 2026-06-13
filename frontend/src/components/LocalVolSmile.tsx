// Reconstructed-smile chart for the Local Vol workspace.
//
// Plots one expiry's arbitrage-free implied-vol curve (recovered by inverting
// the calibrated Dupire PDE call prices through Black) against its market
// quote band: bid/ask I-beams with a mid dot, excluded quotes dimmed. Pure
// SVG, reusing the shared linear-scale / tick helpers.
import { useLayoutEffect, useRef, useState } from "react";
import type { AffineSmile } from "../state/useAffine";
import { formatPct, linearScale, niceTicks } from "../lib/chartScale";

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

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  const ks = smile.model.map((p) => p.k);
  const vols = smile.model.map((p) => p.vol);
  const kMin = Math.min(...ks, ...smile.quotes.map((q) => q.k));
  const kMax = Math.max(...ks, ...smile.quotes.map((q) => q.k));
  let vMin = Math.min(...vols, ...smile.quotes.map((q) => q.bid));
  let vMax = Math.max(...vols, ...smile.quotes.map((q) => q.ask));
  const pad = (vMax - vMin) * 0.12 || 0.01;
  vMin -= pad;
  vMax += pad;

  const x = linearScale([kMin, kMax], [MARGIN.left, MARGIN.left + plotW]);
  const y = linearScale([vMin, vMax], [MARGIN.top + plotH, MARGIN.top]);

  const path = smile.model
    .map((p, i) => `${i === 0 ? "M" : "L"}${x.map(p.k).toFixed(1)},${y.map(p.vol).toFixed(1)}`)
    .join("");

  const ready = plotW > 0 && plotH > 0 && smile.model.length > 1;

  return (
    <div ref={ref} className="relative h-full min-h-0 w-full">
      {ready && (
        <svg width={size.width} height={size.height} className="absolute inset-0">
          {/* Y grid + labels (vol %) */}
          {niceTicks(vMin, vMax, 5).map((v) => (
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
          {niceTicks(kMin, kMax, 6).map((v) => (
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

          {/* Reconstructed model curve */}
          <path d={path} fill="none" stroke="rgb(56 189 248)" strokeWidth={1.75} />
        </svg>
      )}
    </div>
  );
}
