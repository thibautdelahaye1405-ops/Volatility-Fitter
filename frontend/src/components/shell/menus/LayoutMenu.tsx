// Layout ▾ (UI SHELL v2, top-right): the shell's panes — Nodes pane
// (Ctrl+B), the lenses' diagnostics / config asides, the status bar — plus
// zen mode (all three off), close-all-tabs and a layout reset.
import { useState } from "react";
import { LayoutPanelLeft } from "lucide-react";
import MenuButton from "./MenuButton";
import { MenuDivider, MenuItem, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkbench } from "../../../state/workbench";

export default function LayoutMenu() {
  const [open, setOpen] = useState(false);
  const wb = useWorkbench();
  const { layout, setLayout, resetLayout, closeAll } = wb;
  const zen = !layout.nodesPane && !layout.aside && !layout.statusBar;
  const close = () => setOpen(false);

  return (
    <div className="relative">
      <MenuButton
        label="Layout"
        chevron
        active={open}
        title="Panes & layout"
        onClick={() => setOpen((v) => !v)}
      >
        <LayoutPanelLeft size={13} strokeWidth={1.75} className="opacity-80" />
      </MenuButton>
      <MenuPanel open={open} onClose={close} align="right" width="w-64">
        <MenuSection label="Panes" />
        <MenuItem
          label="Nodes pane"
          shortcut="Ctrl+B"
          active={layout.nodesPane}
          onClick={() => setLayout({ nodesPane: !layout.nodesPane })}
        />
        <MenuItem
          label="Diagnostics aside"
          detail="fit / config side panels"
          active={layout.aside}
          onClick={() => setLayout({ aside: !layout.aside })}
        />
        <MenuItem
          label="Status bar"
          active={layout.statusBar}
          onClick={() => setLayout({ statusBar: !layout.statusBar })}
        />
        <MenuItem
          label="Zen mode"
          detail="charts only"
          active={zen}
          onClick={() =>
            setLayout(zen
              ? { nodesPane: true, aside: true, statusBar: true }
              : { nodesPane: false, aside: false, statusBar: false })
          }
        />
        <MenuDivider />
        <MenuItem label="Close all tabs" disabled={wb.tabs.length === 0} onClick={() => { close(); closeAll(); }} />
        <MenuItem label="Reset layout" detail="panes + widths" onClick={() => { close(); resetLayout(); }} />
      </MenuPanel>
    </div>
  );
}
