// Help ▸ Glossary (HELP CENTER ARC, H4): the vocabulary (lib/help/glossary),
// alphabetical with a letter rail and a filter; each entry links its related
// terms, guides / settings and documentation. Deep link `glossary:<id>`.
import { useCallback, useMemo, useState } from "react";
import { GLOSSARY } from "../../lib/help/glossary";
import { Markdown } from "../../lib/help/markdown";
import { useHelp } from "../../state/help";
import { useHelpLinks } from "./useHelpLinks";
import { EntryCard, GHOST_BTN, useAnchorFlash } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

const domId = (id: string) => `help-gl-${id}`;

export default function GlossaryPage({ anchor }: HelpPageProps) {
  const help = useHelp();
  const links = useHelpLinks();
  const [filter, setFilter] = useState("");
  useAnchorFlash(anchor, useCallback((a: string) => domId(a), []));
  const q = filter.trim().toLowerCase();
  const entries = useMemo(
    () => [...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term)).filter((g) => !q || `${g.term} ${g.short} ${g.long}`.toLowerCase().includes(q)),
    [q],
  );
  const letters = useMemo(() => Array.from(new Set(entries.map((g) => g.term[0].toUpperCase()))), [entries]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter glossary" placeholder="Filter terms…"
          className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-surface-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-accent-600/60 focus:outline-none" />
        <span className="font-mono text-[10px] text-slate-500">{entries.length} / {GLOSSARY.length}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {letters.map((l) => (
          <button key={l} onClick={() => document.getElementById(`help-gl-letter-${l}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="h-6 w-6 rounded border border-slate-700 font-mono text-[10px] text-slate-400 hover:border-accent-600/60 hover:text-accent-300">{l}</button>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {entries.map((g, i) => {
          const letter = g.term[0].toUpperCase();
          const first = i === 0 || entries[i - 1].term[0].toUpperCase() !== letter;
          return (
            <div key={g.id}>
              {first && <h3 id={`help-gl-letter-${letter}`} className="mb-1 mt-3 scroll-mt-4 font-mono text-[11px] font-semibold text-slate-500">{letter}</h3>}
              <EntryCard id={domId(g.id)} kind="glossary" title={g.term} summary={g.short} highlighted={anchor === g.id}
                actions={<>
                  {g.related?.map((r) => <button key={r} onClick={() => help.navigate({ page: "glossary", anchor: r })} className={GHOST_BTN}>{GLOSSARY.find((x) => x.id === r)?.term ?? r}</button>)}
                  {g.links?.map((l) => <button key={l} onClick={() => links.open(l.startsWith("help:") || l.startsWith("cmd:") ? l : `help:docs:${l}`)} className={GHOST_BTN}>{l.startsWith("help:") ? l.slice(5) : l.startsWith("cmd:") ? `▶ ${l.slice(4)}` : `📄 ${l}`}</button>)}
                </>}>
                <Markdown source={g.long} handlers={links} className="mt-1" />
              </EntryCard>
            </div>
          );
        })}
      </div>
      {entries.length === 0 && <p className="text-xs text-slate-500">No term matches “{filter}”.</p>}
    </div>
  );
}
