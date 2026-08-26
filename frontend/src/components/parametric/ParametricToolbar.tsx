// Toolbar of the Parametric lens (UI SHELL v2, S3): the chart-card view
// switch (Smile / Compare / Densities / Log Q-density / Term / Surface /
// Stacked IV / Table), the strike-axis mode, the overlay toggles (Target ·
// Calib. quotes · Calib. fit · Weights · Y center · Y fit) and the status
// badges (LIVE/MOCK · STALE · UPDATED). The node identity lives in the tab
// strip, so this row is controls only — extracted from SmileViewer so the
// view stays under the file-size policy.
import SegmentedControl from "../SegmentedControl";
import { AXIS_MODE_OPTIONS } from "../../lib/axisModes";
import type { AxisMode } from "../../lib/axisModes";
import type { AutoScaleToggles } from "../../lib/autoScaleY";
import { badgeClass, chipClass, selectClass } from "../../lib/ui";

/** Chart-card content. "Stacked densities" overlays every expiry's density
 *  (no butterfly arb ⇔ all ≥ 0); "Stacked IV" overlays total variance w=σ²T
 *  (no calendar arb ⇔ curves don't cross). ROADMAP Phase 10. */
export type ChartView =
  | "smile"
  | "compare"
  | "stackeddensity"
  | "logqd"
  | "term"
  | "surface"
  | "stackedvar"
  | "table";

export const CHART_VIEWS: { id: ChartView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "compare", label: "Compare" },
  { id: "stackeddensity", label: "Densities" },
  { id: "logqd", label: "Log Q-density" },
  { id: "term", label: "Term" },
  { id: "surface", label: "Surface" },
  { id: "stackedvar", label: "Stacked IV" },
  { id: "table", label: "Table" },
];

/** Views whose x-axis can switch coordinate (ln(K/F) / strike / %ATM / Δ / …). */
export const AXIS_MODE_VIEWS = new Set<ChartView>(["smile", "stackeddensity", "surface", "stackedvar"]);

/** Interaction hint shown under the chart card, per view. */
export const VIEW_HINTS: Record<ChartView, string> = {
  smile: "Click a quote · Del exclude · ↑↓ amend · Ctrl+Z undo",
  compare: "LQD / SVI-JW / MCS fitted to the same quotes · validity = each family's analytic no-arb signal",
  stackeddensity: "All expiries' densities overlaid · ≥ 0 is structural for LQD only — SVI/MCS dips draw signed in red (clipped otherwise)",
  logqd: "Log quantile density ℓ(u) = log q(u) of the current fit",
  term: "ATM term structure across the expiry ladder · real / event-dilated clock",
  surface: "Drag to rotate · σ(k, T) across the expiry ladder",
  stackedvar: "Total variance w=σ²·T per expiry · non-crossing ⇒ no calendar arbitrage",
  table: "Market frame (prevailing quotes, target, fit @ market spot) · Calib. quotes toggles the calibration columns · Copy / CSV in the footer",
};

export interface ParametricToolbarProps {
  view: ChartView;
  onView: (v: ChartView) => void;
  axisMode: AxisMode;
  onAxisMode: (m: AxisMode) => void;
  showTarget: boolean;
  onShowTarget: () => void;
  showCalibQuotes: boolean;
  onShowCalibQuotes: () => void;
  showCalibFit: boolean;
  onShowCalibFit: () => void;
  showWeights: boolean;
  onShowWeights: () => void;
  autoScaleY: AutoScaleToggles;
  onToggleAutoScale: (key: keyof AutoScaleToggles) => void;
  /** Status badges. */
  live: boolean;
  error: string | null;
  stale: boolean;
  updatedFlash: boolean;
}

export default function ParametricToolbar(p: ParametricToolbarProps) {
  const { view } = p;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2">
      <SegmentedControl options={CHART_VIEWS} value={view} onChange={p.onView} size="xs" />

      {/* Strike-axis display mode (smile / densities / surface / stacked IV) */}
      {AXIS_MODE_VIEWS.has(view) && (
        <select
          className={selectClass}
          value={p.axisMode}
          title="Strike-axis display mode"
          onChange={(e) => p.onAxisMode(e.target.value as AxisMode)}
        >
          {AXIS_MODE_OPTIONS.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      )}

      {/* Fit-target overlay: mid polyline + bid-ask/haircut ribbons (which
          band is emphasized follows the live fit target). */}
      {view === "smile" && (
        <button
          className={chipClass(p.showTarget, "red")}
          title="Overlay the fit target (mid line + bid-ask / haircut band)"
          onClick={p.onShowTarget}
        >
          Target
        </button>
      )}
      {/* Calibration frame toggles: the quotes + target the last fit used and
          the fit on its calibration spot. */}
      {(view === "smile" || view === "table") && (
        <button
          className={chipClass(p.showCalibQuotes, "slate")}
          title="Show the quotes + target the last calibration used (with your exclusions / amended mids) next to the prevailing market — chart layer and table columns"
          onClick={p.onShowCalibQuotes}
        >
          Calib. quotes
        </button>
      )}
      {view === "smile" && (
        <button
          className={chipClass(p.showCalibFit)}
          title="Show the fitted smile on its calibration spot (dashed) next to the fit rolled to the prevailing spot"
          onClick={p.onShowCalibFit}
        >
          Calib. fit
        </button>
      )}
      {view === "smile" && (
        <button
          className={chipClass(p.showWeights)}
          title="Show per-quote calibration weights under the chart (quote density vs the effective mean-1 weights)"
          onClick={p.onShowWeights}
        >
          Weights
        </button>
      )}
      {/* Y-axis auto-scale chips: after any x zoom / pan / brush / axis-mode
          change, "Y fit" snaps the y window to the data in view; "Y center"
          keeps the y zoom but recenters it (fit wins when both are lit). */}
      {view === "smile" && (
        <>
          <button
            className={chipClass(p.autoScaleY.center)}
            title="After any x-view change, keep the y window centered on the data in view (preserves your y zoom; alt+wheel still zooms y)"
            onClick={() => p.onToggleAutoScale("center")}
          >
            Y center
          </button>
          <button
            className={chipClass(p.autoScaleY.fit)}
            title="After any x-view change, auto-fit the y-axis to every curve and quote in the visible x-range"
            onClick={() => p.onToggleAutoScale("fit")}
          >
            Y fit
          </button>
        </>
      )}

      {/* Status badges, right-aligned */}
      <div className="ml-auto flex items-center gap-2">
        <span title={p.error ?? undefined} className={badgeClass(p.live ? "accent" : "amber")}>
          {p.live ? "LIVE" : "MOCK"}
        </span>
        {p.stale && (
          <span
            title="Inputs changed since the last calibration — press Calibrate (top bar) to refit"
            className={badgeClass("amber")}
          >
            STALE
          </span>
        )}
        {p.updatedFlash && (
          <span className={`volfit-fade-in ${badgeClass("accent")}`}>UPDATED</span>
        )}
      </div>
    </div>
  );
}
