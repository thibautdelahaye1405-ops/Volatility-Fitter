// The chart-overlay buttons every zoomable 2-D chart shares (Smile, Local-Vol
// smile, Compare, Stacked IV / Densities): Y center / Y fit at the top-left of
// the plot (they flip the lib/autoScaleY toggles — the policy runs in
// lib/useChartZoom) and ⌂ reset at the bottom-right while zoomed. Mount it
// inside the chart's `relative` plot container, after the SVG.
import type { AutoScaleToggles } from "../../lib/autoScaleY";

export interface ZoomOverlayProps {
  /** Current Y auto-scale toggles; the buttons show only with a toggler. */
  autoScaleY?: AutoScaleToggles;
  onToggleAutoScale?: (key: keyof AutoScaleToggles) => void;
  /** Show the ⌂ reset affordance (the chart is zoomed / panned). */
  zoomed: boolean;
  onReset: () => void;
  /** Left offset (px) of the Y buttons — the chart's plot-area left margin,
   *  so they sit just inside the y-axis. */
  left?: number;
}

export const Y_BUTTON_TITLES: Record<keyof AutoScaleToggles, string> = {
  center:
    "Y center — after any x-view change, keep the y window centered on the data in view (preserves your y zoom; alt+wheel still zooms y)",
  fit: "Y fit — after any x-view change, auto-fit the y-axis to every curve and quote in the visible x-range",
};

export default function ZoomOverlay({ autoScaleY, onToggleAutoScale, zoomed, onReset, left = 56 }: ZoomOverlayProps) {
  return (
    <>
      {onToggleAutoScale && autoScaleY && (
        <div className="absolute top-1 flex gap-1" style={{ left: left + 2 }}>
          {(["center", "fit"] as const).map((key) => (
            <button
              key={key}
              aria-pressed={autoScaleY[key]}
              onClick={() => onToggleAutoScale(key)}
              title={Y_BUTTON_TITLES[key]}
              className={[
                "rounded border px-1.5 py-px font-mono text-[9px] shadow transition-colors",
                autoScaleY[key]
                  ? "border-accent-500/50 bg-accent-500/15 text-accent-300"
                  : "border-slate-700 bg-surface-800/90 text-slate-500 hover:text-slate-200",
              ].join(" ")}
            >
              {key === "center" ? "Y center" : "Y fit"}
            </button>
          ))}
        </div>
      )}
      {zoomed && (
        <button
          onClick={onReset}
          title="Reset zoom (or double-click the chart)"
          className="absolute bottom-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2 py-0.5 text-[10px] text-slate-300 shadow hover:text-slate-100"
        >
          ⌂ reset
        </button>
      )}
    </>
  );
}
