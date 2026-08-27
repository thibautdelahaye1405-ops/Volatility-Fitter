// Layer rail of the Parametric chart (UI SHELL v2 wave 2): the chart-layer
// toggles — Target · Calib. quotes · Calib. fit · Weights — as a compact
// vertical strip at the RIGHT of the chart, next to what they switch on and
// off, instead of buttons in the toolbar. Each entry is a small square button
// with an icon; the label is the tooltip and appears inline on hover of the
// rail. Which entries apply depends on the view (the table only has the
// calibration-quotes toggle).
import { Crosshair, Layers, Scale, SquareDashed } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface LayerRailProps {
  view: "smile" | "table";
  showTarget: boolean;
  onShowTarget: () => void;
  showCalibQuotes: boolean;
  onShowCalibQuotes: () => void;
  showCalibFit: boolean;
  onShowCalibFit: () => void;
  showWeights: boolean;
  onShowWeights: () => void;
}

interface Entry {
  key: string;
  icon: LucideIcon;
  label: string;
  title: string;
  on: boolean;
  tone: string;
  onClick: () => void;
  views: readonly ("smile" | "table")[];
}

export default function LayerRail(p: LayerRailProps) {
  const entries: Entry[] = [
    {
      key: "target", icon: Crosshair, label: "Target",
      title: "Overlay the fit target (mid line + bid-ask / haircut band)",
      on: p.showTarget, tone: "border-red-500/50 bg-red-500/10 text-red-300",
      onClick: p.onShowTarget, views: ["smile"],
    },
    {
      key: "calibq", icon: SquareDashed, label: "Calib. quotes",
      title: "Show the quotes + target the last calibration used (with your exclusions / amended mids) next to the prevailing market — chart layer and table columns",
      on: p.showCalibQuotes, tone: "border-slate-400/60 bg-slate-500/15 text-slate-200",
      onClick: p.onShowCalibQuotes, views: ["smile", "table"],
    },
    {
      key: "calibfit", icon: Layers, label: "Calib. fit",
      title: "Show the fitted smile on its calibration spot (dashed) next to the fit rolled to the prevailing spot",
      on: p.showCalibFit, tone: "border-accent-500/50 bg-accent-500/10 text-accent-300",
      onClick: p.onShowCalibFit, views: ["smile"],
    },
    {
      key: "weights", icon: Scale, label: "Weights",
      title: "Show per-quote calibration weights under the chart (quote density vs the effective mean-1 weights)",
      on: p.showWeights, tone: "border-accent-500/50 bg-accent-500/10 text-accent-300",
      onClick: p.onShowWeights, views: ["smile"],
    },
  ];
  return (
    <div
      aria-label="Chart layers"
      className="group/rail flex w-9 shrink-0 flex-col items-stretch gap-1 border-l border-slate-800/80 pl-2 pt-1"
    >
      <span className="mb-0.5 text-center text-[8px] font-semibold uppercase tracking-wider text-slate-600">
        layers
      </span>
      {entries
        .filter((e) => e.views.includes(p.view))
        .map((e) => {
          const Icon = e.icon;
          return (
            <button
              key={e.key}
              aria-pressed={e.on}
              aria-label={e.label}
              title={`${e.label} — ${e.title}`}
              onClick={e.onClick}
              className={[
                "flex h-7 w-7 items-center justify-center rounded border transition-colors",
                e.on ? e.tone : "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-200",
              ].join(" ")}
            >
              <Icon size={13} strokeWidth={1.75} />
            </button>
          );
        })}
    </div>
  );
}
