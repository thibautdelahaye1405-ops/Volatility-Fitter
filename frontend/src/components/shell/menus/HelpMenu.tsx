// Help ▾ menu (HELP CENTER ARC): the full professional help surface — Welcome,
// the Walkthrough tour, F1 contextual help, the Help Center pages
// (Documentation · Command reference · Settings reference · Keyboard
// shortcuts · Glossary · Tips & tricks), Ask @Vol-Fitter, the command
// palette, What's new, the OpenAPI reference, the quality report and About.
// Every row is a registry command (CommandRow), so the Ctrl+K palette runs
// the same code and Help ▸ Command reference documents every one of them.
import { useState } from "react";
import {
  BookA, Compass, ExternalLink, FileCode2, Info, Keyboard, Library, Lightbulb, LifeBuoy,
  Megaphone, MessageCircleQuestion, SlidersHorizontal, Sparkles, Terminal,
} from "lucide-react";
import MenuButton from "./MenuButton";
import CommandRow from "../CommandRow";
import { MenuDivider, MenuPanel } from "../../topbar/Menu";

export default function HelpMenu() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="relative" data-tour="menu.help">
      <MenuButton label="Help" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-72">
        <CommandRow id="help.welcome" icon={Sparkles} after={close} />
        <CommandRow id="help.walkthrough" icon={Compass} after={close} />
        <CommandRow id="help.context" icon={LifeBuoy} after={close} />
        <MenuDivider />
        <CommandRow id="help.docs" icon={Library} after={close} />
        <CommandRow id="help.commands" icon={Terminal} after={close} />
        <CommandRow id="help.settings" icon={SlidersHorizontal} after={close} />
        <CommandRow id="help.shortcuts" icon={Keyboard} after={close} />
        <CommandRow id="help.glossary" icon={BookA} after={close} />
        <CommandRow id="help.tips" icon={Lightbulb} after={close} />
        <MenuDivider />
        <CommandRow id="help.ask" icon={MessageCircleQuestion} after={close} />
        <CommandRow id="help.palette" icon={Terminal} after={close} />
        <MenuDivider />
        <CommandRow id="help.whatsNew" icon={Megaphone} after={close} />
        <CommandRow id="help.api" icon={FileCode2} after={close} />
        <CommandRow id="help.report" icon={ExternalLink} after={close} />
        <CommandRow id="help.about" icon={Info} after={close} />
      </MenuPanel>
    </div>
  );
}
