// Help ▸ Documentation (HELP CENTER ARC, H4): the shipped documentation set
// — the technical notes (Markdown editions rendered IN the app, PDFs opened in
// a tab), the book, the LQD paper, the handoff pack — as a catalog
// (lib/help/docsCatalog) cross-checked against what THIS install has
// (GET /help/docs: the .exe may ship without Docs/). Deep link `docs:<id>`
// opens a document; the reader renders GET /help/docs/{id} through the
// Markdown renderer with an outline rail.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, FileText } from "lucide-react";
import { API_BASE_URL, api } from "../../state/api";
import { useWorkflowContext } from "../../state/workflowContext";
import { useHelp } from "../../state/help";
import { DOCS_CATALOG } from "../../lib/help/docsCatalog";
import type { DocEntry, DocKind } from "../../lib/help/types";
import { Markdown, headingSlug, parseBlocks } from "../../lib/help/markdown";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, EntryCard, GHOST_BTN, useAnchorFlash } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

interface CatalogEntry { id: string; root: string; name: string; kind: "md" | "pdf" }
interface Catalog { available: boolean; root: string | null; entries: CatalogEntry[] }
interface DocText { id: string; root: string; name: string; title: string; markdown: string }

const KIND_LABEL: Record<DocKind, string> = { note: "note", supplement: "supplement", paper: "paper", book: "book", handoff: "handoff", guide: "guide" };
const domId = (id: string) => `help-doc-${id}`;
const fileUrl = (root: string, name: string) => `${API_BASE_URL}/help/files/${encodeURIComponent(root)}/${encodeURIComponent(name)}`;

function useCatalog(live: boolean): Catalog | null {
  const [cat, setCat] = useState<Catalog | null>(null);
  useEffect(() => {
    if (!live) { setCat(null); return; }
    let cancelled = false;
    api.get<Catalog>("/help/docs").then((c) => { if (!cancelled) setCat(c); }).catch(() => { if (!cancelled) setCat({ available: false, root: null, entries: [] }); });
    return () => { cancelled = true; };
  }, [live]);
  return cat;
}

function Reader({ entry, onBack }: { entry: DocEntry; onBack: () => void }) {
  const links = useHelpLinks();
  const [doc, setDoc] = useState<DocText | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setDoc(null); setError(null);
    if (!entry.markdown) return;
    let cancelled = false;
    api.get<DocText>(`/help/docs/${encodeURIComponent(entry.id)}`).then((d) => { if (!cancelled) setDoc(d); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [entry]);
  const outline = useMemo(() => (doc ? parseBlocks(doc.markdown).filter((b) => b.t === "h" && b.level === 2).map((b) => (b as { text: string }).text) : []), [doc]);
  return (
    <div className="grid gap-5 md:grid-cols-[1fr_15rem]">
      <article className="min-w-0">
        <button onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300"><ArrowLeft size={11} /> Documentation</button>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-slate-100">{entry.title}</h2>
          <span className="rounded border border-slate-700 px-1.5 py-px text-[9px] uppercase tracking-wider text-slate-400">{KIND_LABEL[entry.kind]}{entry.number ? ` · No. ${entry.number}` : ""}</span>
          {entry.pdf && <a href={fileUrl(entry.pdf.root, entry.pdf.name)} target="_blank" rel="noopener noreferrer" className={`${ACTION_BTN} inline-flex items-center gap-1`}><ExternalLink size={11} /> Open the PDF</a>}
        </div>
        <p className="mt-1 text-xs text-slate-400">{entry.abstract}</p>
        {!entry.markdown && <p className="mt-3 rounded-md border border-slate-800 bg-surface-800/40 p-3 text-xs text-slate-400">This document ships as a PDF only — open it in a new tab with the button above.</p>}
        {entry.markdown && !doc && !error && <p className="mt-3 text-xs text-slate-500">Loading…</p>}
        {error && <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-300">The backend could not serve this document ({error}). It needs the repository's Docs/ folder next to the backend (or VOLFIT_DOCS_ROOT).</p>}
        {doc && <Markdown source={doc.markdown} handlers={links} className="mt-3" />}
      </article>
      <aside className="flex flex-col gap-3 md:sticky md:top-0 md:self-start">
        {outline.length > 0 && (
          <div className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Sections</div>
            <ul className="mt-1.5 flex max-h-[50vh] flex-col gap-1 overflow-y-auto">
              {outline.map((h) => <li key={h}><button onClick={() => document.getElementById(headingSlug(h))?.scrollIntoView({ behavior: "smooth", block: "start" })} className="text-left text-[11px] text-slate-400 hover:text-accent-300">{h.replace(/[*`$]/g, "")}</button></li>)}
            </ul>
          </div>
        )}
        {entry.related && entry.related.length > 0 && (
          <div className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Related</div>
            <ul className="mt-1.5 flex flex-col gap-1">
              {entry.related.map((r) => <li key={r}><button onClick={() => links.open(r.startsWith("help:") ? r : `help:docs:${r}`)} className="text-left text-[11px] text-accent-400 hover:text-accent-300">{r.replace(/^help:/, "")}</button></li>)}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}

export default function DocsBrowser({ anchor }: HelpPageProps) {
  const help = useHelp();
  const { live } = useWorkflowContext();
  const catalog = useCatalog(live);
  const [filter, setFilter] = useState("");
  useAnchorFlash(anchor, useCallback((a: string) => domId(a), []));
  const entry = anchor ? DOCS_CATALOG.find((d) => d.id === anchor) : undefined;
  if (entry) return <Reader entry={entry} onBack={() => help.navigate({ page: "docs" })} />;

  const have = new Set((catalog?.entries ?? []).map((e) => `${e.root}/${e.name}`));
  const present = (d: DocEntry) => catalog === null ? null : Boolean((d.markdown && have.has(`${d.markdown.root}/${d.markdown.name}`)) || (d.pdf && have.has(`${d.pdf.root}/${d.pdf.name}`)));
  const q = filter.trim().toLowerCase();
  const rows = DOCS_CATALOG.filter((d) => !q || `${d.title} ${d.topic} ${d.abstract} ${d.number ?? ""}`.toLowerCase().includes(q));
  const kinds: DocKind[] = ["note", "supplement", "book", "paper", "handoff", "guide"];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter documentation" placeholder="Filter documents — topic, number, words from the abstract…"
          className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-surface-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-accent-600/60 focus:outline-none" />
        <span className="font-mono text-[10px] text-slate-500">{rows.length} / {DOCS_CATALOG.length}</span>
      </div>
      {!live && <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">The backend is offline — documents open once it is running. The catalog below is the full set; the in-app guides (Help ▸ Guides) do not need the backend.</p>}
      {live && catalog && !catalog.available && <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">This install ships without the Docs/ folder — documents open from a source checkout (or set VOLFIT_DOCS_ROOT on the server).</p>}
      {kinds.map((k) => {
        const group = rows.filter((d) => d.kind === k);
        if (group.length === 0) return null;
        return (
          <section key={k} className="flex flex-col gap-2">
            <h3 className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{KIND_LABEL[k]}s <span className="font-normal text-slate-600">· {group.length}</span></h3>
            {group.map((d) => {
              const ok = present(d);
              return (
                <EntryCard key={d.id} id={domId(d.id)} kind="doc" kindLabel={d.number ? `No. ${d.number}` : d.topic} title={d.title} summary={d.abstract} highlighted={anchor === d.id}
                  meta={ok === false ? <span className="text-amber-400">not on this install</span> : ok === true ? <span className="text-emerald-400">available</span> : undefined}
                  actions={<>
                    {d.markdown && <button onClick={() => help.navigate({ page: "docs", anchor: d.id })} className={`${ACTION_BTN} inline-flex items-center gap-1`}><FileText size={11} /> Read in-app</button>}
                    {d.pdf && <a href={fileUrl(d.pdf.root, d.pdf.name)} target="_blank" rel="noopener noreferrer" className={`${GHOST_BTN} inline-flex items-center gap-1`}><ExternalLink size={11} /> PDF</a>}
                    {!d.markdown && !d.pdf && <span className="text-[10px] text-slate-500">no file</span>}
                  </>} />
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
