// Help ▾ menu (UI SHELL v2): keyboard shortcuts, the backend's OpenAPI docs,
// the client-facing quality report and the About box.
import { useState } from "react";
import { BookOpen, ExternalLink, Info, Keyboard } from "lucide-react";
import MenuButton from "./MenuButton";
import { MenuDivider, MenuItem, MenuPanel } from "../../topbar/Menu";
import { useWorkbench } from "../../../state/workbench";
import { API_BASE_URL } from "../../../state/api";

export default function HelpMenu() {
  const [open, setOpen] = useState(false);
  const wb = useWorkbench();
  const close = () => setOpen(false);
  const openUrl = (url: string) => {
    close();
    window.open(url, "_blank", "noopener");
  };

  return (
    <div className="relative">
      <MenuButton label="Help" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-64">
        <MenuItem
          icon={Keyboard}
          label="Keyboard shortcuts"
          shortcut="Ctrl+/"
          onClick={() => { close(); wb.openDialog("shortcuts"); }}
        />
        <MenuItem
          icon={BookOpen}
          label="API reference"
          detail="OpenAPI /docs"
          onClick={() => openUrl(`${API_BASE_URL}/docs`)}
        />
        <MenuItem
          icon={ExternalLink}
          label="Quality report"
          detail="HTML export"
          onClick={() => openUrl(`${API_BASE_URL}/export/report`)}
        />
        <MenuDivider />
        <MenuItem icon={Info} label="About VolFit" onClick={() => { close(); wb.openDialog("about"); }} />
      </MenuPanel>
    </div>
  );
}
