// Local Vol toolbar (UI SHELL v2 wave 2): the header row of the Local Vol lens
// — the grouped NODE / TICKER view switch (shared LensViewSwitch, so it reads
// exactly like the Parametric lens), the per-view render / clock controls,
// the graph-source toggle and the right-aligned fit-status badges. The
// (ticker, expiry) identity lives in the workbench tab strip, so this row is
// controls only — no Underlying / Expiry selectors. The strike-axis unit
// selectors are NOT here either: they sit in the chart-card footer next to
// the x-axis (LocalVolViewer, via AxisModeSelect / AxisUnitSelect). Pure
// presentation: every piece of state is owned by LocalVolViewer and passed
// down through LocalVolToolbarProps; the sub-tab vocabulary (LvView & co.)
// lives here so the view and the toolbar share one definition.
import { Waypoints } from "lucide-react";
import SegmentedControl from "../SegmentedControl";
import LensViewSwitch from "../charts/LensViewSwitch";
import { badgeClass } from "../../lib/ui";
import type { AffineFitResponse } from "../../state/useAffine";
import type { ClockMode } from "../../state/useTerm";

/** Chart-card sub-tabs, mirroring the Parametric workspace. "LV surface" is the
 *  nodal local-vol grid (3D mesh or heatmap); "IV surface" is the reconstructed
 *  implied-vol mesh (both over t × strike). */
export type LvView =
  | "smile" | "densities" | "term" | "lvsurface" | "ivsurface" | "stackedvar" | "table";
/** NODE views: about the active tab's expiry. */
export const LV_NODE_VIEWS: { id: LvView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "table", label: "Table" },
];
/** TICKER views: the whole expiry ladder of the active tab's underlying. */
export const LV_TICKER_VIEWS: { id: LvView; label: string }[] = [
  { id: "term", label: "Term" },
  { id: "densities", label: "Densities" },
  { id: "stackedvar", label: "Stacked IV" },
  { id: "lvsurface", label: "LV surface" },
  { id: "ivsurface", label: "IV surface" },
];
/** Flat list (node views first) for any consumer that wants one vocabulary. */
export const LV_VIEWS: { id: LvView; label: string }[] = [...LV_NODE_VIEWS, ...LV_TICKER_VIEWS];
/** Which sub-tabs are per-expiry (follow the active node's expiry). */
export const PER_EXPIRY: Record<LvView, boolean> = {
  smile: true, table: true,
  densities: false, term: false, lvsurface: false, ivsurface: false, stackedvar: false,
};
/** Views whose x-axis can switch coordinate, exactly like the Parametric Smile:
 *  the reconstructed smile, the density overlay, the IV surface and stacked var. */
export const AXIS_MODE_VIEWS = new Set<LvView>(["smile", "densities", "ivsurface", "stackedvar"]);

/** LV-surface render mode: 3D local-variance mesh (default) or vertex heatmap. */
export type LvRender = "mesh" | "heatmap";
const LV_RENDER_OPTIONS: { id: LvRender; label: string }[] = [
  { id: "mesh", label: "3D σ²_loc" },
  { id: "heatmap", label: "Heat map" },
];

/** X-axis scales for the 3D LV mesh. The nodal grid lives in x = K/F, so only
 *  coordinates derivable from it are offered (Δ / normalized need an implied
 *  vol the LV grid does not carry). Strike uses the per-row forward F(t)
 *  interpolated from the expiry ladder, shearing the sheet like the IV view.
 *  Rendered by the chart-card footer's AxisUnitSelect (LocalVolViewer). */
export type LvAxis = "moneyness" | "logmoneyness" | "strike";
export const LV_AXIS_OPTIONS: { id: LvAxis; label: string }[] = [
  { id: "moneyness", label: "x = K/F" },
  { id: "logmoneyness", label: "k = ln(K/F)" },
  { id: "strike", label: "Strike K" },
];

/** Maturity clock (Term sub-tab): real vs shared event-dilated time. */
const CLOCK_OPTIONS: { id: ClockMode; label: string }[] = [
  { id: "real", label: "Real time" },
  { id: "dilated", label: "Event-dilated" },
];

/** Whole-bp figure that survives a null/NaN metric (a diverged fit's NaN
 *  serializes to null over JSON — degrade to "—", never crash the tab). */
export const fmtBp0 = (v: number | null | undefined): string =>
  v == null || !Number.isFinite(v) ? "—" : v.toFixed(0);

export interface LocalVolToolbarProps {
  /** Active chart-card sub-tab. */
  view: LvView;
  onViewChange: (view: LvView) => void;
  /** LV-surface render mode (3D local-variance mesh vs vertex heatmap). */
  lvRender: LvRender;
  onLvRenderChange: (mode: LvRender) => void;
  /** Maturity clock for the Term sub-tab. */
  axisClock: ClockMode;
  onAxisClockChange: (mode: ClockMode) => void;
  /** Source: live quotes (false) vs the graph-extrapolated LV projection (true). */
  graphSource: boolean;
  onGraphSourceChange: (on: boolean) => void;
  /** Calibrated payload feeding the right-aligned status badges (none when null). */
  data: AffineFitResponse | null;
  /** Worst calendar crossing's label (Stacked IV marker), used as the
   *  "cal. viol." badge tooltip when known. */
  calendarWorstLabel?: string;
}

export default function LocalVolToolbar({
  view, onViewChange,
  lvRender, onLvRenderChange,
  axisClock, onAxisClockChange,
  graphSource, onGraphSourceChange,
  data, calendarWorstLabel,
}: LocalVolToolbarProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3">
      {/* Grouped view switch: NODE (per-expiry) · TICKER (whole ladder) */}
      <LensViewSwitch
        groups={[
          { label: "node", options: LV_NODE_VIEWS },
          { label: "ticker", options: LV_TICKER_VIEWS },
        ]}
        value={view}
        onChange={onViewChange}
      />

      {/* LV-surface render mode: 3D local-variance mesh vs vertex heatmap */}
      {view === "lvsurface" && (
        <SegmentedControl
          options={LV_RENDER_OPTIONS}
          value={lvRender}
          onChange={onLvRenderChange}
          size="xs"
        />
      )}

      {/* Maturity clock (Term sub-tab): real vs shared event-dilated time */}
      {view === "term" && (
        <SegmentedControl
          options={CLOCK_OPTIONS}
          value={axisClock}
          onChange={onAxisClockChange}
          size="xs"
        />
      )}

      {/* Source: live quotes vs the graph-extrapolated LV projection (Phase 9) */}
      <button
        onClick={() => onGraphSourceChange(!graphSource)}
        title="Calibrate the LV surface to the graph-extrapolated smiles instead of the live quotes"
        className={[
          "flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
          graphSource
            ? "border-violet-500/50 bg-violet-500/10 text-violet-300"
            : "border-slate-700 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-200",
        ].join(" ")}
      >
        <Waypoints size={12} strokeWidth={1.75} className="opacity-80" />
        Graph-extrapolated
      </button>

      {/* Status badges, right-aligned: STALE · arb-free / cal. viol. · rms/conv/max */}
      {data && (
        <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-slate-500">
          {data.stale && (
            <span
              title="Inputs changed since the last LV calibration — press Calibrate (top bar)"
              className={badgeClass("amber")}
            >
              STALE
            </span>
          )}
          <span
            className={
              data.arbitrageFree
                ? "rounded bg-emerald-600/15 px-1.5 py-0.5 text-emerald-400"
                : "rounded bg-amber-600/15 px-1.5 py-0.5 text-amber-400"
            }
            title={
              data.arbitrageFree
                ? "No butterfly / calendar violation on the PDE lattice"
                : calendarWorstLabel ??
                  "Adjacent-maturity price decreases on the PDE lattice (see Stacked IV)"
            }
          >
            {data.arbitrageFree ? "arb-free" : `${data.calendarViolations} cal. viol.`}
          </span>
          <span title="Per-quote IV error of the LV surface vs the FIT TARGET (mid, or the bid-ask / haircut band — zero inside the band): rms · rms on the converged operator · worst quote">
            rms {fmtBp0(data.rmsIvErrorBp)}
            {typeof data.rmsConvergedBp === "number" && Number.isFinite(data.rmsConvergedBp)
              ? ` · conv ${data.rmsConvergedBp.toFixed(0)}`
              : ""}{" "}
            · max {fmtBp0(data.maxIvErrorBp)} bp
          </span>
        </span>
      )}
    </div>
  );
}
