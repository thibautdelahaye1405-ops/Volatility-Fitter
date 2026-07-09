// Brand mark + app menu (top-left). The σ VolFit button opens the menu that
// holds what is configuration rather than a workspace: Options (calibration &
// model settings) and View (display preferences). Its face lights up when one
// of those panes is the active view, since they no longer appear in the nav.
import { useState } from "react";
import { ChevronDown, Eye, SlidersHorizontal } from "lucide-react";
import type { TabId } from "../../App";
import { MenuDivider, MenuItem, MenuPanel } from "./Menu";

export default function BrandMenu({
  activeTab,
  onSelect,
}: {
  activeTab: TabId;
  onSelect: (tab: TabId) => void;
}) {
  const [open, setOpen] = useState(false);
  const active = activeTab === "options" || activeTab === "view";
  const pick = (tab: TabId) => {
    setOpen(false);
    onSelect(tab);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Settings & app menu"
        className={[
          "flex items-center gap-2.5 rounded-md px-1.5 py-1 transition-colors",
          active ? "text-accent-300" : "text-slate-100 hover:bg-slate-800/60",
        ].join(" ")}
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent-600/20 font-mono text-sm font-bold text-accent-400">
          σ
        </span>
        <span className="text-sm font-semibold tracking-wide">VolFit</span>
        <ChevronDown size={13} className="text-slate-500" />
      </button>

      <MenuPanel open={open} onClose={() => setOpen(false)} width="w-64">
        <MenuItem
          icon={SlidersHorizontal}
          label="Options"
          detail="calibration & models"
          active={activeTab === "options"}
          onClick={() => pick("options")}
        />
        <MenuItem
          icon={Eye}
          label="View"
          detail="display preferences"
          active={activeTab === "view"}
          onClick={() => pick("view")}
        />
        <MenuDivider />
        <div className="px-3 py-1.5 text-[10px] leading-snug text-slate-600">
          VolFit — implied-volatility surface workbench
        </div>
      </MenuPanel>
    </div>
  );
}
