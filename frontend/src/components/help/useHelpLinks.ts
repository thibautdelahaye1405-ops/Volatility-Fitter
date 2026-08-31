// Link handling shared by every Help Center page (HELP CENTER ARC, H4): the
// Markdown renderer hands raw `help:` / `cmd:` targets to one handler that
// navigates inside the center or runs a registry command — so a guide can say
// [Open the haircut setting](help:settings:haircut) or [Calibrate](cmd:calibrate.both).
import { useCallback } from "react";
import { useHelp } from "../../state/help";
import { useOptionalCommands } from "../../state/commands";
import { parseCommandLink, parseHelpLink } from "../../lib/help/pages";
import type { MarkdownHandlers } from "../../lib/help/markdown";

export function useHelpLinks(): MarkdownHandlers & { open: (target: string) => void; run: (command: string, arg?: string) => void } {
  const help = useHelp();
  const cmds = useOptionalCommands();
  const run = useCallback((command: string, arg?: string) => { cmds?.run(command, arg); }, [cmds]);
  const open = useCallback((target: string) => {
    const link = parseHelpLink(target);
    if (link) { help.navigate(link); return; }
    const c = parseCommandLink(target);
    if (c) run(c.command, c.arg);
  }, [help, run]);
  const onLink = useCallback((target: string) => {
    if (target.startsWith("help:") || target.startsWith("cmd:")) { open(target); return true; }
    return false;
  }, [open]);
  return { onLink, open, run };
}
