// Layout ▾ (UI SHELL v2, top-right): the shell's panes — Nodes pane
// (Ctrl+B), the lenses' diagnostics / config asides, the status bar — plus
// zen mode (all three off), the per-tab view memory switch (wave 3, C2),
// close-all-tabs and a layout reset. Every row is a registry command
// (CommandRow; wave 3, C4) so the palette toggles the same state.
import { useState } from "react";
import { LayoutPanelLeft } from "lucide-react";
import MenuButton from "./MenuButton";
import CommandRow from "../CommandRow";
import { MenuDivider, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkbench } from "../../../state/workbench";

export default function LayoutMenu() {
  const [open, setOpen] = useState(false);
  const { layout } = useWorkbench();
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
        <CommandRow id="layout.nodesPane" />
        <CommandRow id="layout.aside" />
        <CommandRow id="layout.statusBar" />
        <CommandRow id="layout.zen" />
        <MenuDivider />
        <MenuSection label="Tabs" />
        <CommandRow id="layout.rememberView" detail={layout.rememberView ? "each tab keeps its view" : "one view per lens"} />
        <CommandRow id="tab.closeAll" after={close} />
        <CommandRow id="layout.reset" after={close} />
      </MenuPanel>
    </div>
  );
}
