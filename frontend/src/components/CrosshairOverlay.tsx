// Presentational crosshair pieces shared by the 2D charts (lib/crosshair does
// the pointer -> domain mapping). The guides render inside a chart's
// plot-local <g>; the badge is an absolutely-positioned overlay in the chart's
// relative container — both follow the established SmileChart hover idiom
// (dashed slate guides, mono readout badge in the top-right corner).
import type { CrosshairPoint } from "../lib/crosshair";

const GUIDE_STROKE = "rgb(148 163 184 / 0.4)";

/** Vertical + horizontal dashed guides through the pointer position. */
export function CrosshairGuides({
  point,
  plotW,
  plotH,
}: {
  point: CrosshairPoint;
  plotW: number;
  plotH: number;
}) {
  return (
    <g pointerEvents="none">
      <line x1={point.px} x2={point.px} y1={0} y2={plotH} stroke={GUIDE_STROKE} strokeDasharray="3 3" />
      <line x1={0} x2={plotW} y1={point.py} y2={point.py} stroke={GUIDE_STROKE} strokeDasharray="3 3" />
    </g>
  );
}

/** Compact readout badge (top-right corner of the chart's relative container). */
export function CrosshairBadge({ label }: { label: string }) {
  return (
    <div className="pointer-events-none absolute top-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40">
      {label}
    </div>
  );
}
