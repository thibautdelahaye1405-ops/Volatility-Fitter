// Left activity bar (UI SHELL v2, S2; VS Code grammar): one icon per lens —
// Graph · Forwards · Parametric · Local Vol · Quality — applied to every open
// node tab. Alt+1…5 switch lenses. The bottom holds the two "manage" entries
// (Universe dialog, Settings dialog) exactly where VS Code keeps Accounts /
// Manage. The Local-Vol icon is inert while the Options master switch is
// off (tooltip explains).
import { Box, Database, Gauge, Settings, Spline, TrendingUp, Waypoints } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ACTIVITIES, useWorkbench } from "../../state/workbench";
import type { Activity } from "../../state/workbench";
import { useWorkflowContext } from "../../state/workflowContext";

const ICONS: Record<Activity, LucideIcon> = {
  graph: Waypoints,
  forwards: TrendingUp,
  parametric: Spline,
  localvol: Box,
  quality: Gauge,
};

function BarButton({
  icon: Icon,
  label,
  title,
  active = false,
  disabled = false,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  title: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      aria-pressed={active}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={[
        "relative flex h-11 w-12 items-center justify-center transition-colors",
        disabled
          ? "cursor-not-allowed text-slate-700"
          : active
            ? "text-slate-100"
            : "text-slate-500 hover:text-slate-200",
      ].join(" ")}
    >
      {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-r bg-accent-400" />}
      <Icon size={21} strokeWidth={1.6} />
    </button>
  );
}

export default function ActivityBar() {
  const { activity, setActivity, openDialog, dialog } = useWorkbench();
  const { workflow } = useWorkflowContext();
  const localVolEnabled = workflow.sched?.localVolEnabled ?? true;

  return (
    <nav
      aria-label="Lenses"
      className="flex w-12 shrink-0 flex-col border-r border-slate-800 bg-surface-950"
    >
      {ACTIVITIES.map((a, i) => {
        const disabled = a.id === "localvol" && !localVolEnabled;
        return (
          <BarButton
            key={a.id}
            icon={ICONS[a.id]}
            label={a.label}
            title={
              disabled
                ? "Local-Vol calibration is disabled (enable it in Options ▸ Local-Vol surface)"
                : `${a.label} — ${a.hint} (Alt+${i + 1})`
            }
            active={activity === a.id}
            disabled={disabled}
            onClick={() => setActivity(a.id)}
          />
        );
      })}
      <div className="mt-auto flex flex-col border-t border-slate-800/60 pt-1">
        <BarButton
          icon={Database}
          label="Manage universe"
          title="Manage universe — tickers, expiries, saved universes (Ctrl+Shift+U)"
          active={dialog === "universe"}
          onClick={() => openDialog("universe")}
        />
        <BarButton
          icon={Settings}
          label="Options"
          title="Options — calibration & model settings (Ctrl+,)"
          active={dialog === "options"}
          onClick={() => openDialog("options")}
        />
      </div>
    </nav>
  );
}
