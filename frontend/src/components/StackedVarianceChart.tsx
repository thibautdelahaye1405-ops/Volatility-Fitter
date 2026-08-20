// "Stacked IV" view of the Parametric workspace (ROADMAP Phase 10; V3.3
// item 10 added the calendar-cross evidence).
//
// Overlays every expiry's TOTAL VARIANCE w(k) = σ(k)²·T on shared axes
// (GET /surface/{ticker}, reusing the fitted mesh). Non-crossing total-variance
// curves ⟺ no calendar arbitrage — the exact statement (raw σ smiles can cross
// even when arbitrage-free, so total variance is the right y-axis).
//
// Evidence (V3.3 item 10): the exact full-line calendar certificate's
// (ledgerGapMin, ledgerGapK) per far-expiry quality row places a circle at the
// refuted pair's minimizing strike (flag iff gap < -1e-6 — the certificate's
// own tolerance); a "Levels / Δ pairs" toggle plots w_far − w_near per
// adjacent pair on the shared k grid with sub-zero excursions filled red.
// Self-fetching like SurfaceChart; refetches on node / fit-mode change.
import { useState } from "react";
import type { FitMode } from "../state/useSmile";
import { useQuality } from "../state/useQuality";
import { useSurface } from "../state/useSurface";
import OverlayCurvesChart, { maturityColor } from "./OverlayCurvesChart";
import type { OverlayMarker, OverlaySeries } from "./OverlayCurvesChart";
import SegmentedControl from "./SegmentedControl";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import { calendarMarkers, deltaRows } from "../lib/stackedVariance";
import type { VarianceGrid } from "../lib/stackedVariance";
import {
  axisModeLabel,
  axisTickLabel,
  axisTransform,
  makeVolAt,
} from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

type StackMode = "levels" | "delta";
const MODE_OPTIONS = [
  { id: "levels" as const, label: "Levels" },
  { id: "delta" as const, label: "Δ pairs" },
];

interface Props {
  ticker: string;
  fitMode: FitMode;
  /** Bumps to force a refetch (e.g. a spot move transports the surface). */
  reloadKey?: number;
  /** Strike-axis display mode (shared with the Smile view). */
  axisMode?: AxisMode;
}

export default function StackedVarianceChart({
  ticker,
  fitMode,
  reloadKey = 0,
  axisMode = "logmoneyness",
}: Props) {
  const { format } = useExpiryFormat();
  const { data, loading, error } = useSurface(ticker, fitMode, reloadKey);
  // Certificate evidence rides the quality report (a cached-state read, never
  // a fit); keyed on the same reload epoch as the curves themselves.
  const { report } = useQuality(reloadKey);
  const [mode, setMode] = useState<StackMode>("levels");

  if (data === null) {
    return loading
      ? message("Loading surface…")
      : message(`Surface unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const n = data.t.length;
  // Total variance w(k) = σ(k)² · τ per expiry (σ is quoted in the event-variance
  // clock τ, so this recovers the price-implied w; non-crossing ⟺ no calendar arb).
  const grid: VarianceGrid = {
    expiries: data.expiries,
    k: data.k,
    w: data.vol.map((row, i) => row.map((v) => v * v * data.tau[i])),
  };
  const kRange: [number, number] = [data.k[0] ?? -1, data.k[data.k.length - 1] ?? 1];
  /** Per-expiry axis context for the chosen x-axis mode. */
  const ctxOf = (i: number) => ({
    forward: data.forward[i],
    t: data.t[i],
    atmVol: data.atmVol[i],
    volAt: makeVolAt(data.k.map((k2, j) => ({ k: k2, vol: data.vol[i][j] }))),
    kRange,
  });
  const txAt = (k: number, i: number): number =>
    axisMode === "logmoneyness" ? k : axisTransform(axisMode, k, ctxOf(i));

  // Certificate-refuted pairs for THIS ticker (flag iff gap < -CAL_TOL — the
  // certificate's own gate, mapped in lib/stackedVariance).
  const qNodes = (report?.nodes ?? []).filter((q) => q.ticker === ticker && q.hasFit);
  const markers: OverlayMarker[] = calendarMarkers(qNodes, grid, mode).map((m) => ({
    // Δ mode lives on the shared k grid; levels mode follows the axis mode
    // through the FAR expiry's context (the row that owns the certificate).
    x: mode === "delta" ? m.k : txAt(m.k, m.farIndex),
    y: m.y,
    label: m.label,
  }));

  const series: OverlaySeries[] =
    mode === "levels"
      ? data.t.map((ti, i) => ({
          label: formatExpiry(data.expiries[i], ti, format),
          xs: axisMode === "logmoneyness" ? data.k : data.k.map((k) => txAt(k, i)),
          ys: grid.w[i],
          color: maturityColor(n > 1 ? i / (n - 1) : 0),
        }))
      : // Δ mode: adjacent-pair differences on the SHARED k grid (the
        // subtraction is only meaningful there, so the axis stays k).
        deltaRows(grid).map((row, i) => ({
          label: `${formatExpiry(data.expiries[i], data.t[i], format)}→${formatExpiry(
            data.expiries[i + 1],
            data.t[i + 1],
            format,
          )}`,
          xs: data.k,
          ys: row.ys,
          color: maturityColor(n > 2 ? i / (n - 2) : 0),
          fillNegative: true,
        }));

  const deltaAxis = mode === "delta";
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-1 flex shrink-0 items-center justify-end gap-2">
        {markers.length > 0 && (
          <span
            className="rounded border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10px] text-rose-400"
            title="Exact full-line calendar certificate refuted on the circled pair(s) — hover a circle for ΔG min and location"
          >
            {markers.length} cal. cross
          </span>
        )}
        <SegmentedControl options={MODE_OPTIONS} value={mode} onChange={setMode} size="xs" />
      </div>
      <div className="min-h-0 flex-1">
        <OverlayCurvesChart
          series={series}
          xLabel={
            deltaAxis || axisMode === "logmoneyness"
              ? "k = log(K / F)"
              : axisModeLabel(axisMode)
          }
          yLabel={deltaAxis ? "Δw = w_far − w_near (adjacent pairs)" : "total variance w = σ²·T"}
          zeroBaseline
          zoomY
          formatX={(v) => (deltaAxis ? axisTickLabel("logmoneyness", v) : axisTickLabel(axisMode, v))}
          markers={markers}
        />
      </div>
    </div>
  );
}
