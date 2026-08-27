// Toolbar of the Parametric lens (UI SHELL v2 wave 2): the grouped view
// switch — NODE views (Smile · Density · Compare · Table, about the active
// tab's expiry) and TICKER views (Term · Densities · Stacked IV · Surface,
// the whole ladder) — the Density sub-toggle (Density / Log Q-density / CDF)
// and the status badges (LIVE/MOCK · STALE · UPDATED). Everything that acts
// on the chart itself lives ON the chart now: the layer toggles in the
// right-hand LayerRail, Y-center / Y-fit as chart overlay buttons, the x-axis
// unit next to the x-axis. Save prior moved to the top bar's Priors ▾.
import LensViewSwitch from "../charts/LensViewSwitch";
import SegmentedControl from "../SegmentedControl";
import type { DistKind } from "../DistributionChart";
import { badgeClass } from "../../lib/ui";

/** Chart-card content. "Stacked densities" overlays every expiry's density
 *  (no butterfly arb ⇔ all ≥ 0); "Stacked IV" overlays total variance w=σ²T
 *  (no calendar arb ⇔ curves don't cross). ROADMAP Phase 10. */
export type ChartView =
  | "smile"
  | "density"
  | "compare"
  | "table"
  | "term"
  | "stackeddensity"
  | "stackedvar"
  | "surface";

/** Views about the active tab's node vs the whole ticker ladder. */
export const NODE_VIEWS: { id: ChartView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "density", label: "Density" },
  { id: "compare", label: "Compare" },
  { id: "table", label: "Table" },
];
export const TICKER_VIEWS: { id: ChartView; label: string }[] = [
  { id: "term", label: "Term" },
  { id: "stackeddensity", label: "Densities" },
  { id: "stackedvar", label: "Stacked IV" },
  { id: "surface", label: "Surface" },
];

/** Views whose x-axis can switch coordinate (ln(K/F) / strike / %ATM / Δ / …). */
export const AXIS_MODE_VIEWS = new Set<ChartView>(["smile", "stackeddensity", "surface", "stackedvar"]);

/** Density sub-views: the pdf, the LQD backbone ℓ(u), the cumulative F(x). */
export const DENSITY_KINDS: { id: DistKind; label: string }[] = [
  { id: "density", label: "Density" },
  { id: "logqd", label: "Log Q-density" },
  { id: "cdf", label: "CDF" },
];

/** Interaction hint shown under the chart card, per view. */
export const VIEW_HINTS: Record<ChartView, string> = {
  smile: "Click a quote · Del exclude · ↑↓ amend · Ctrl+Z undo · scroll: zoom · drag: pan",
  density: "Risk-neutral distribution of the current fit — pdf, log quantile density ℓ(u) = log q(u), or the CDF",
  compare: "Prevailing model shown · click a family chip to fit it on the same quotes · validity = each family's analytic no-arb signal",
  table: "Market frame (prevailing quotes, target, fit @ market spot) · Calib. quotes toggles the calibration columns · Copy / CSV in the footer",
  term: "ATM term structure across the expiry ladder · real / event-dilated clock",
  stackeddensity: "All expiries' densities overlaid · ≥ 0 is structural for LQD only — SVI/MCS dips draw signed in red (clipped otherwise)",
  stackedvar: "Total variance w=σ²·T per expiry · non-crossing ⇒ no calendar arbitrage",
  surface: "Drag to rotate · σ(k, T) across the expiry ladder",
};

export interface ParametricToolbarProps {
  view: ChartView;
  onView: (v: ChartView) => void;
  densityKind: DistKind;
  onDensityKind: (k: DistKind) => void;
  /** Status badges. */
  live: boolean;
  error: string | null;
  stale: boolean;
  updatedFlash: boolean;
}

export default function ParametricToolbar(p: ParametricToolbarProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3">
      <LensViewSwitch
        groups={[
          { label: "node", options: NODE_VIEWS },
          { label: "ticker", options: TICKER_VIEWS },
        ]}
        value={p.view}
        onChange={p.onView}
      />

      {p.view === "density" && (
        <SegmentedControl options={DENSITY_KINDS} value={p.densityKind} onChange={p.onDensityKind} size="xs" />
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
        {p.updatedFlash && <span className={`volfit-fade-in ${badgeClass("accent")}`}>UPDATED</span>}
      </div>
    </div>
  );
}
