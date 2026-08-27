// A menu row rendered FROM the command registry (UI SHELL v2 wave 3, C4):
// label, chord hint, detail, enabled and active state all come from the
// bound command (state/commands), so the menus and the Ctrl+K palette show
// the same thing and run the same code. `after` runs once the command fired
// (menus close themselves); `detail` can override the registry annotation.
import type { LucideIcon } from "lucide-react";
import { MenuItem } from "../topbar/Menu";
import { useCommands } from "../../state/commands";
import type { CommandId } from "../../lib/commands";

export default function CommandRow({
  id,
  icon,
  detail,
  label,
  after,
  intercept,
}: {
  id: CommandId | string;
  icon?: LucideIcon;
  /** Override the registry detail (e.g. a live status). */
  detail?: string;
  /** Override the registry label (e.g. a dynamic row's own name). */
  label?: string;
  after?: () => void;
  /** The menu owns the next step instead of running the command at once:
   *  an inline argument form, or a confirmation (File ▸ New). */
  intercept?: () => void;
}) {
  const { byId } = useCommands();
  const c = byId(id);
  if (!c) return null;
  return (
    <MenuItem
      icon={icon}
      label={label ?? c.label}
      detail={detail ?? c.detail}
      shortcut={c.shortcut}
      active={c.active === true}
      disabled={!c.enabled}
      onClick={() => {
        if (intercept) { intercept(); return; }
        if (c.arg) return; // needs a prompt the menu did not provide
        after?.();
        c.run();
      }}
    />
  );
}
