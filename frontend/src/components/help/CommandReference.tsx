// Help ▸ Command reference (HELP CENTER ARC, H4): EVERY registry command —
// label, id, chord, category — with its documentation (lib/help/commandDocs:
// what it does, when it is enabled, an example), a live enabled/active state
// from the bound registry, and a Run button. A filter box narrows by any
// field; a category rail jumps; the deep link `commands:<id>` scrolls to and
// flashes the entry. Locked complete by commandDocs.test.ts.
import { useCallback, useMemo, useState } from "react";
import { COMMANDS, DYNAMIC } from "../../lib/commands";
import type { CommandCategory, CommandDef } from "../../lib/commands";
import { commandDoc } from "../../lib/help/commandDocs";
import { Markdown } from "../../lib/help/markdown";
import { useOptionalCommands } from "../../state/commands";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, EntryCard, GHOST_BTN, useAnchorFlash } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

const CATEGORIES: CommandCategory[] = ["File", "Export", "Universe", "Fetch", "Calibrate", "Priors", "Lens", "Layout", "Tabs", "View", "Help"];
const domId = (id: string) => `help-cmd-${id.replace(/[^a-zA-Z0-9]+/g, "-")}`;

const DYNAMIC_ROWS: CommandDef[] = [
  { id: DYNAMIC.universeLoad, label: "Load universe: <name>", category: "Universe", detail: "one row per saved universe" },
  { id: DYNAMIC.workspaceServer, label: "Open workspace from server: <name>", category: "File", detail: "one row per server workspace" },
  { id: DYNAMIC.workspaceDelete, label: "Delete workspace from server: <name>", category: "File", detail: "one row per server workspace" },
  { id: DYNAMIC.workspaceRecent, label: "Open recent: <name>", category: "File", detail: "one row per recent file / server workspace" },
];

export default function CommandReference({ anchor }: HelpPageProps) {
  const cmds = useOptionalCommands();
  const links = useHelpLinks();
  const [filter, setFilter] = useState("");
  const [cat, setCat] = useState<CommandCategory | "all">("all");
  useAnchorFlash(anchor, useCallback((a: string) => domId(a), []));

  const rows = useMemo(() => {
    const all: CommandDef[] = [...COMMANDS, ...DYNAMIC_ROWS];
    const q = filter.trim().toLowerCase();
    return all.filter((c) => {
      if (cat !== "all" && c.category !== cat) return false;
      if (!q) return true;
      const d = commandDoc(c.id);
      return [c.id, c.label, c.category, c.shortcut ?? "", c.detail ?? "", d?.summary ?? "", d?.details ?? ""].join(" ").toLowerCase().includes(q);
    });
  }, [filter, cat]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter commands — label, id, chord, words from the explanation…"
          aria-label="Filter commands"
          className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-surface-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-accent-600/60 focus:outline-none"
        />
        <span className="font-mono text-[10px] text-slate-500">{rows.length} / {COMMANDS.length + DYNAMIC_ROWS.length}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {(["all", ...CATEGORIES] as const).map((c) => (
          <button key={c} onClick={() => setCat(c)}
            className={["rounded-full border px-2 py-0.5 text-[10px] font-medium", cat === c ? "border-accent-500/60 bg-accent-500/15 text-accent-300" : "border-slate-700 text-slate-400 hover:text-slate-200"].join(" ")}>
            {c === "all" ? "All" : c}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-slate-500">
        Every row here is also a row of the Ctrl+K palette and of the menus — same id, same code. Rows marked <em>dynamic</em> are generated at runtime (saved universes, server workspaces, recent files).
      </p>

      <div className="flex flex-col gap-2">
        {rows.map((c) => {
          const doc = commandDoc(c.id);
          const bound = cmds?.byId(c.id);
          const dynamic = c.id.endsWith(":");
          return (
            <EntryCard
              key={c.id}
              id={domId(c.id)}
              kind="command"
              kindLabel={dynamic ? "dynamic" : c.category}
              title={<>{c.label}{bound?.active && <span className="ml-2 text-accent-400">✓ on</span>}</>}
              meta={<>
                <span className="text-slate-600">{c.id}</span>
                {c.shortcut && <kbd className="ml-2 rounded border border-slate-700 px-1 text-[10px] text-slate-400">{c.shortcut}</kbd>}
              </>}
              summary={doc?.summary ?? c.detail}
              highlighted={anchor === c.id}
              actions={<>
                {!dynamic && bound && (
                  <button onClick={() => bound.run()} disabled={!bound.enabled || Boolean(c.arg)} className={ACTION_BTN}
                    title={c.arg ? "Takes an argument — run it from the palette (Ctrl+K)" : bound.enabled ? "Run this command now" : `Disabled now — ${doc?.enabledWhen ?? "needs the live backend"}`}>
                    ▶ Run
                  </button>
                )}
                {c.arg && <button onClick={() => links.run("help.palette")} className={GHOST_BTN}>Open in the palette…</button>}
                {doc?.guide && <button onClick={() => links.open(`help:guides:${doc.guide}`)} className={GHOST_BTN}>Guide: {doc.guide}</button>}
              </>}
            >
              {doc ? (
                <div className="mt-2 grid gap-2 md:grid-cols-[1fr_18rem]">
                  <Markdown source={doc.details} handlers={links} />
                  <div className="rounded-md border border-slate-800/80 bg-surface-950/60 p-2">
                    <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Example</div>
                    <Markdown source={doc.example} handlers={links} />
                    {doc.enabledWhen && <div className="mt-2 text-[10px] text-slate-500"><span className="font-semibold text-slate-400">Enabled when:</span> {doc.enabledWhen}</div>}
                    {doc.related && doc.related.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {doc.related.map((r) => (
                          <button key={r} onClick={() => links.open(r.startsWith("help:") ? r : `help:commands:${r}`)} className="rounded border border-slate-700 px-1.5 py-px text-[10px] text-slate-400 hover:text-slate-200">
                            {r.replace(/^help:/, "")}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-[11px] text-rose-400">No documentation entry for this command (the commandDocs lock should have caught this).</p>
              )}
            </EntryCard>
          );
        })}
      </div>
    </div>
  );
}
