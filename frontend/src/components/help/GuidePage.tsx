// Help ▸ Guides (HELP CENTER ARC, H4): one guide per lens and per workflow
// (lib/help/guides). Without an anchor: the index (cards). With an anchor
// (`guides:<id>` — F1 lands here): the guide itself, with a "Read more" rail
// of related links and a heading outline built from the Markdown.
import { useMemo } from "react";
import { ArrowLeft } from "lucide-react";
import { GUIDES, guide } from "../../lib/help/guides";
import type { GuideId } from "../../lib/help/types";
import { Markdown, headingSlug, parseBlocks } from "../../lib/help/markdown";
import { useHelp } from "../../state/help";
import { useHelpLinks } from "./useHelpLinks";
import { EntryCard, GHOST_BTN } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

export default function GuidePage({ anchor }: HelpPageProps) {
  const help = useHelp();
  const links = useHelpLinks();
  const g = anchor ? GUIDES.find((x) => x.id === (anchor as GuideId)) : undefined;
  const outline = useMemo(
    () => (g ? parseBlocks(g.body).filter((b) => b.t === "h" && b.level === 2).map((b) => (b as { text: string }).text) : []),
    [g],
  );

  if (!g) {
    return (
      <div className="flex flex-col gap-2">
        {anchor && <p className="text-xs text-rose-400">No guide named “{anchor}”. Pick one below.</p>}
        <p className="text-[11px] text-slate-500">F1 opens the guide of the lens or dialog in front of you. Each guide names the real controls, walks a first use, explains the badges and numbers, and links the settings it depends on.</p>
        <div className="grid gap-2 md:grid-cols-2">
          {GUIDES.map((x) => (
            <EntryCard key={x.id} id={`help-guide-${x.id}`} kind="guide" kindLabel={x.lens ?? "workflow"} title={x.title} summary={x.summary}
              actions={<button onClick={() => help.navigate({ page: "guides", anchor: x.id })} className={GHOST_BTN}>Open the guide</button>} />
          ))}
        </div>
      </div>
    );
  }

  const gg = guide(g.id);
  return (
    <div className="grid gap-5 md:grid-cols-[1fr_15rem]">
      <article className="min-w-0">
        <button onClick={() => help.navigate({ page: "guides" })} className="mb-2 inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300">
          <ArrowLeft size={11} /> All guides
        </button>
        <h2 className="text-lg font-semibold text-slate-100">{gg.title}</h2>
        <p className="mt-1 text-xs text-slate-400">{gg.summary}</p>
        <Markdown source={gg.body} handlers={links} className="mt-3" />
      </article>
      <aside className="flex flex-col gap-3 md:sticky md:top-0 md:self-start">
        {outline.length > 0 && (
          <div className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">On this page</div>
            <ul className="mt-1.5 flex flex-col gap-1">
              {outline.map((h) => (
                <li key={h}>
                  <button onClick={() => document.getElementById(headingSlug(h))?.scrollIntoView({ behavior: "smooth", block: "start" })}
                    className="text-left text-[11px] text-slate-400 hover:text-accent-300">{h.replace(/[*`]/g, "")}</button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {gg.lens && (
          <button onClick={() => links.run(`lens.${gg.lens}`)} className={GHOST_BTN}>Switch to the {gg.title.replace(/ lens$/i, "")} lens</button>
        )}
        {gg.related && gg.related.length > 0 && (
          <div className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Read more</div>
            <ul className="mt-1.5 flex flex-col gap-1">
              {gg.related.map((r) => (
                <li key={r}>
                  <button onClick={() => links.open(r.startsWith("help:") || r.startsWith("cmd:") ? r : `help:docs:${r}`)} className="text-left text-[11px] text-accent-400 hover:text-accent-300">
                    {r.replace(/^help:/, "").replace(/^cmd:/, "▶ ")}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
