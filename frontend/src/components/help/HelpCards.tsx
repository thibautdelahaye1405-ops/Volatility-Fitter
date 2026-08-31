// Shared card grammar of the Help Center (HELP CENTER ARC, H4): the entry
// card (title · kind chip · summary · actions), the kind chip, an
// "anchor" highlight hook (scroll + flash the deep-linked entry), and the
// search results list every page shares through the nav-rail search box.
import { useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { cardKindLabel, searchHelp } from "../../lib/help/search";
import type { CardKind, SearchHit } from "../../lib/help/search";
import { parseHelpLink } from "../../lib/help/pages";
import type { HelpLink } from "../../lib/help/types";

const KIND_TONE: Record<CardKind, string> = {
  command: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  setting: "border-violet-500/40 bg-violet-500/10 text-violet-300",
  glossary: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  tip: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  guide: "border-accent-500/40 bg-accent-500/10 text-accent-300",
  doc: "border-slate-500/40 bg-slate-500/10 text-slate-300",
  whatsnew: "border-pink-500/40 bg-pink-500/10 text-pink-300",
  shortcut: "border-teal-500/40 bg-teal-500/10 text-teal-300",
};

export function KindChip({ kind, label }: { kind: CardKind; label?: string }) {
  return (
    <span className={["rounded border px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider", KIND_TONE[kind]].join(" ")}>
      {label ?? cardKindLabel(kind)}
    </span>
  );
}

/** Scroll the deep-linked entry into view and flash it once. */
export function useAnchorFlash(anchor: string | undefined, idOf: (anchor: string) => string) {
  useEffect(() => {
    if (!anchor) return;
    const el = document.getElementById(idOf(anchor));
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    el.classList.add("help-flash");
    const t = window.setTimeout(() => el.classList.remove("help-flash"), 1600);
    return () => window.clearTimeout(t);
  }, [anchor, idOf]);
}

export function EntryCard({
  id, title, kind, kindLabel, summary, meta, children, highlighted = false, actions,
}: {
  id: string;
  title: ReactNode;
  kind: CardKind;
  kindLabel?: string;
  summary?: ReactNode;
  /** Right-aligned muted line (a shortcut, a default…). */
  meta?: ReactNode;
  children?: ReactNode;
  highlighted?: boolean;
  actions?: ReactNode;
}) {
  return (
    <article
      id={id}
      className={[
        "scroll-mt-4 rounded-lg border bg-surface-800/40 p-3 transition-colors",
        highlighted ? "border-accent-500/60 ring-1 ring-accent-500/30" : "border-slate-800",
      ].join(" ")}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13px] font-semibold text-slate-100">{title}</h4>
        <KindChip kind={kind} label={kindLabel} />
        {meta && <span className="ml-auto font-mono text-[10px] text-slate-500">{meta}</span>}
      </header>
      {summary && <p className="mt-1 text-xs text-slate-400">{summary}</p>}
      {children}
      {actions && <div className="mt-2 flex flex-wrap items-center gap-2">{actions}</div>}
    </article>
  );
}

export const ACTION_BTN = "rounded-md border border-accent-600/50 bg-accent-600/10 px-2 py-0.5 text-[11px] font-medium text-accent-300 hover:bg-accent-600/20 disabled:cursor-not-allowed disabled:opacity-40";
export const GHOST_BTN = "rounded-md border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 hover:border-slate-600 hover:text-slate-100";

/** Ranked results for the nav-rail query (every kind), grouped by kind order. */
export function SearchResults({ query, onOpen }: { query: string; onOpen: (link: HelpLink) => void }) {
  const hits = useMemo(() => searchHelp(query, { limit: 40 }), [query]);
  const listRef = useRef<HTMLDivElement | null>(null);
  if (hits.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-800 p-6 text-center text-xs text-slate-500">
        Nothing matches “{query.trim()}”. Try a command name (calibrate), a setting (haircut, gridXNodes), a
        concept (lit, prior, calendar) or a chord (Ctrl+K).
      </div>
    );
  }
  return (
    <div ref={listRef} className="flex flex-col gap-2" role="list" aria-label="Search results">
      {hits.map((h: SearchHit) => {
        const link = parseHelpLink(h.card.link);
        return (
          <button
            key={h.card.id}
            role="listitem"
            onClick={() => link && onOpen(link)}
            className="rounded-lg border border-slate-800 bg-surface-800/40 p-3 text-left transition-colors hover:border-accent-600/50 hover:bg-surface-800/70"
          >
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-slate-100">{h.card.title}</span>
              <KindChip kind={h.card.kind} />
              <span className="ml-auto font-mono text-[10px] text-slate-600">{h.score.toFixed(1)}</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{h.snippet}</p>
          </button>
        );
      })}
    </div>
  );
}
