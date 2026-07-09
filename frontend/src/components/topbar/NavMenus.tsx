// Grouped workspace navigation: Surfaces ▾ (Parametric / Local Vol /
// Forwards), Universe ▾ (Graph / Selection) and Quality as a direct tab.
// A group's face shows its ACTIVE leaf ("Surfaces · Local Vol") so the
// current location stays visible even though the leaves live in a dropdown.
import { useState } from "react";
import {
  Box,
  ChevronDown,
  Gauge,
  ListChecks,
  Spline,
  TrendingUp,
  Waypoints,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { TabId } from "../../App";
import { MenuItem, MenuPanel } from "./Menu";

interface NavLeaf {
  id: TabId;
  label: string;
  icon: LucideIcon;
}
interface NavGroup {
  id: string;
  label: string;
  icon: LucideIcon;
  items: NavLeaf[];
}

/** The per-asset surface-fitting workspaces vs the cross-asset universe ones. */
const GROUPS: NavGroup[] = [
  {
    id: "surfaces",
    label: "Surfaces",
    icon: Spline,
    items: [
      { id: "parametric", label: "Parametric", icon: Spline },
      { id: "localvol", label: "Local Vol", icon: Box },
      { id: "forwards", label: "Forwards", icon: TrendingUp },
    ],
  },
  {
    id: "universe",
    label: "Universe",
    icon: Waypoints,
    items: [
      { id: "graph", label: "Graph", icon: Waypoints },
      { id: "universe", label: "Selection", icon: ListChecks },
    ],
  },
];

const QUALITY: NavLeaf = { id: "quality", label: "Quality", icon: Gauge };

/** Face styling shared by group triggers and the direct Quality tab. */
const faceClass = (active: boolean): string =>
  [
    "relative flex h-full items-center gap-1.5 px-3 text-sm font-medium transition-colors",
    active ? "text-accent-400" : "text-slate-400 hover:text-slate-200",
  ].join(" ");

const ActiveBar = () => (
  <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent-500" />
);

export default function NavMenus({
  activeTab,
  onSelect,
  localVolEnabled,
}: {
  activeTab: TabId;
  onSelect: (tab: TabId) => void;
  /** Master switch from Options; when off the Local Vol item is inert. */
  localVolEnabled: boolean;
}) {
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const pick = (tab: TabId) => {
    setOpenGroup(null);
    onSelect(tab);
  };

  return (
    <nav className="flex h-full items-stretch gap-1" aria-label="Workspaces">
      {GROUPS.map((g) => {
        const activeLeaf = g.items.find((it) => it.id === activeTab) ?? null;
        const GIcon = g.icon;
        return (
          <div key={g.id} className="relative flex items-stretch">
            <button
              onClick={() => setOpenGroup((v) => (v === g.id ? null : g.id))}
              aria-current={activeLeaf ? "page" : undefined}
              className={faceClass(activeLeaf !== null)}
            >
              <GIcon size={15} strokeWidth={1.75} className="opacity-80" />
              <span>{g.label}</span>
              {activeLeaf && (
                <span className="font-normal text-slate-500"> · {activeLeaf.label}</span>
              )}
              <ChevronDown size={12} className="text-slate-600" />
              {activeLeaf && <ActiveBar />}
            </button>

            <MenuPanel
              open={openGroup === g.id}
              onClose={() => setOpenGroup(null)}
              width="w-48"
            >
              {g.items.map((it) => {
                const disabled = it.id === "localvol" && !localVolEnabled;
                return (
                  <MenuItem
                    key={it.id}
                    icon={it.icon}
                    label={it.label}
                    active={it.id === activeTab}
                    disabled={disabled}
                    title={
                      disabled
                        ? "Local-Vol calibration is disabled (enable it in Options)"
                        : undefined
                    }
                    onClick={() => { if (!disabled) pick(it.id); }}
                  />
                );
              })}
            </MenuPanel>
          </div>
        );
      })}

      {/* Quality: the monitoring dashboard stays one click away. */}
      <button
        onClick={() => pick(QUALITY.id)}
        aria-current={activeTab === QUALITY.id ? "page" : undefined}
        className={faceClass(activeTab === QUALITY.id)}
      >
        <Gauge size={15} strokeWidth={1.75} className="opacity-80" />
        <span>{QUALITY.label}</span>
        {activeTab === QUALITY.id && <ActiveBar />}
      </button>
    </nav>
  );
}
