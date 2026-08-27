// Help ▾ menu (UI SHELL v2): keyboard shortcuts, the command palette, the
// backend's OpenAPI docs, the client-facing quality report and the About box
// — every row a registry command (CommandRow; wave 3, C4).
import { useState } from "react";
import { BookOpen, ExternalLink, Info, Keyboard, Terminal } from "lucide-react";
import MenuButton from "./MenuButton";
import CommandRow from "../CommandRow";
import { MenuDivider, MenuPanel } from "../../topbar/Menu";

export default function HelpMenu() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="relative">
      <MenuButton label="Help" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-64">
        <CommandRow id="help.shortcuts" icon={Keyboard} after={close} />
        <CommandRow id="help.palette" icon={Terminal} after={close} />
        <CommandRow id="help.api" icon={BookOpen} after={close} />
        <CommandRow id="help.report" icon={ExternalLink} after={close} />
        <MenuDivider />
        <CommandRow id="help.about" icon={Info} after={close} />
      </MenuPanel>
    </div>
  );
}
