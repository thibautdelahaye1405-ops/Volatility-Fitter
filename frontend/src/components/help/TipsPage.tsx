// Help ▸ Tips & tricks (HELP CENTER ARC, H4): curated tips (lib/help/tips)
// with Try-it actions, filterable by scope (shell / a lens) and level
// (basic / pro). Deep link `tips:<id>`.
import { useCallback, useMemo, useState } from "react";
import { TIPS } from "../../lib/help/tips";
import { Markdown } from "../../lib/help/markdown";
import { useOptionalCommands } from "../../state/commands";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, EntryCard, useAnchorFlash } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

const SCOPES = ["all", "shell", "graph", "forwards", "parametric", "localvol", "quality"] as const;
const domId = (id: string) => `help-tip-${id}`;

export default function TipsPage({ anchor }: HelpPageProps) {
  const links = useHelpLinks();
  const cmds = useOptionalCommands();
  const [scope, setScope] = useState<(typeof SCOPES)[number]>("all");
  const [level, setLevel] = useState<"all" | "basic" | "pro">("all");
  useAnchorFlash(anchor, useCallback((a: string) => domId(a), []));
  const tips = useMemo(
    () => TIPS.filter((t) => (scope === "all" || t.scope === scope) && (level === "all" || t.level === level) || t.id === anchor),
    [scope, level, anchor],
  );
  const chip = (on: boolean) => ["rounded-full border px-2 py-0.5 text-[10px] font-medium", on ? "border-accent-500/60 bg-accent-500/15 text-accent-300" : "border-slate-700 text-slate-400 hover:text-slate-200"].join(" ");
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1">
        {SCOPES.map((s) => <button key={s} onClick={() => setScope(s)} className={chip(scope === s)}>{s === "all" ? "All" : s === "localvol" ? "Local Vol" : s[0].toUpperCase() + s.slice(1)}</button>)}
        <span className="mx-2 text-slate-700">|</span>
        {(["all", "basic", "pro"] as const).map((l) => <button key={l} onClick={() => setLevel(l)} className={chip(level === l)}>{l === "all" ? "Any level" : l}</button>)}
        <span className="ml-auto font-mono text-[10px] text-slate-500">{tips.length} / {TIPS.length}</span>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {tips.map((t) => {
          const bound = t.action ? cmds?.byId(t.action.command) : undefined;
          return (
            <EntryCard key={t.id} id={domId(t.id)} kind="tip" kindLabel={`${t.scope === "localvol" ? "local vol" : t.scope} · ${t.level}`} title={t.title} highlighted={anchor === t.id}
              actions={t.action && (
                <button onClick={() => links.run(t.action!.command, t.action!.arg)} disabled={bound ? !bound.enabled : false} className={ACTION_BTN}
                  title={bound && !bound.enabled ? "Not available right now (live backend / open node needed)" : undefined}>
                  ▶ {t.action.label}
                </button>
              )}>
              <Markdown source={t.body} handlers={links} className="mt-1" />
            </EntryCard>
          );
        })}
      </div>
    </div>
  );
}
