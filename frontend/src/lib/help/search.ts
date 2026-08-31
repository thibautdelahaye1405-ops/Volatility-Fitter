// Help corpus search (HELP CENTER ARC, H4): ONE index over every help corpus
// — commands, settings, glossary, tips, guides, documentation catalog, what's
// new, shortcuts — ranked by a BM25-style score with field boosts (title ≫
// summary ≫ body), plus a snippet. It powers the Help Center search box and
// the local tier of Ask @Vol-Fitter (instant, offline, deterministic); the
// Claude tier receives the top cards as grounding. PURE (no React) and
// vitest-locked: the obvious queries rank the obvious card first.
import { COMMAND_DOCS } from "./commandDocs";
import { SETTING_DOCS } from "./settingsDocs";
import { GLOSSARY } from "./glossary";
import { TIPS } from "./tips";
import { GUIDES } from "./guides";
import { DOCS_CATALOG } from "./docsCatalog";
import { WHATS_NEW } from "./whatsNew";
import { SHORTCUT_GROUPS } from "../shortcuts";
import { COMMANDS } from "../commands";

export type CardKind = "command" | "setting" | "glossary" | "tip" | "guide" | "doc" | "whatsnew" | "shortcut";

/** One searchable unit; `link` is a Help Center deep link ("settings:haircut"). */
export interface HelpCard {
  id: string;
  kind: CardKind;
  title: string;
  /** One-line description shown under the title. */
  summary: string;
  /** Full text (Markdown) used for ranking and the Claude grounding. */
  text: string;
  link: string;
  /** For commands: the registry id (Run button); for tips: the action. */
  command?: string;
  commandArg?: string;
}

export interface SearchHit {
  card: HelpCard;
  score: number;
  snippet: string;
}

const KIND_LABEL: Record<CardKind, string> = {
  command: "Command", setting: "Setting", glossary: "Glossary", tip: "Tip",
  guide: "Guide", doc: "Document", whatsnew: "What's new", shortcut: "Shortcut",
};
export const cardKindLabel = (k: CardKind): string => KIND_LABEL[k];

/** Build the corpus (memoised: the content is static). */
let CORPUS: HelpCard[] | null = null;
export function helpCorpus(): HelpCard[] {
  if (CORPUS) return CORPUS;
  const labelOf = new Map<string, string>(COMMANDS.map((c) => [c.id, c.label]));
  const cards: HelpCard[] = [];
  for (const d of COMMAND_DOCS) {
    const label = labelOf.get(d.id) ?? d.id;
    cards.push({ id: `command:${d.id}`, kind: "command", title: label, summary: d.summary,
      text: `${label}\n${d.summary}\n${d.details}\n${d.example}\n${d.enabledWhen ?? ""}`, link: `commands:${d.id}`, command: d.id });
  }
  for (const s of SETTING_DOCS) {
    cards.push({ id: `setting:${s.key}`, kind: "setting", title: `${s.label} (${s.key})`, summary: s.summary,
      text: `${s.label} ${s.key}\n${s.summary}\n${s.details}\n${s.example}\n${s.activation ?? ""}`, link: `settings:${s.key}` });
  }
  for (const g of GLOSSARY) {
    cards.push({ id: `glossary:${g.id}`, kind: "glossary", title: g.term, summary: g.short, text: `${g.term}\n${g.short}\n${g.long}`, link: `glossary:${g.id}` });
  }
  for (const t of TIPS) {
    cards.push({ id: `tip:${t.id}`, kind: "tip", title: t.title, summary: firstSentence(t.body), text: `${t.title}\n${t.body}`,
      link: `tips:${t.id}`, command: t.action?.command, commandArg: t.action?.arg });
  }
  for (const g of GUIDES) {
    cards.push({ id: `guide:${g.id}`, kind: "guide", title: g.title, summary: g.summary, text: `${g.title}\n${g.summary}\n${g.body}`, link: `guides:${g.id}` });
  }
  for (const d of DOCS_CATALOG) {
    cards.push({ id: `doc:${d.id}`, kind: "doc", title: d.title, summary: d.abstract, text: `${d.title}\n${d.topic}\n${d.abstract}`, link: `docs:${d.id}` });
  }
  for (const w of WHATS_NEW) {
    cards.push({ id: `whatsnew:${w.date}:${w.title}`, kind: "whatsnew", title: `${w.title} (${w.date})`, summary: w.items[0] ?? "",
      text: `${w.title}\n${w.items.join("\n")}`, link: `whatsnew:${w.date}` });
  }
  for (const g of SHORTCUT_GROUPS) {
    for (const s of g.items) {
      cards.push({ id: `shortcut:${g.title}:${s.keys}`, kind: "shortcut", title: `${s.keys} — ${g.title}`, summary: s.label,
        text: `${s.keys}\n${s.label}\n${g.title}`, link: `shortcuts:${s.keys}` });
    }
  }
  CORPUS = cards;
  return cards;
}

/** Reset the memoised corpus (tests). */
export function resetHelpCorpus(): void { CORPUS = null; }

export function firstSentence(md: string): string {
  const s = md.replace(/[*`#>]/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").trim();
  const m = /^(.+?[.!?])(\s|$)/.exec(s);
  return (m ? m[1] : s).slice(0, 180);
}

// ---------------------------------------------------------------------------
// Ranking — BM25 over unigrams with field boosts; camelCase keys split so
// "grid x nodes" and "gridXNodes" both hit.
// ---------------------------------------------------------------------------

const STOP = new Set(["the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "it", "for", "with", "how", "do", "i", "what", "does", "my", "can", "at", "by", "be", "as"]);

export function tokenize(s: string): string[] {
  return s
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z])([A-Z][a-z])/g, "$1 $2")
    .toLowerCase()
    .split(/[^a-z0-9σζκηλνα±]+/)
    .filter((t) => t.length > 1 && !STOP.has(t))
    .map(stem);
}

/** Light suffix stemming (-ation/-tion/-ing/-ate/-er/-ed, then plurals) —
 *  enough for help text: calibrate ~ calibration ~ calibrating → "calibr",
 *  nodes → node, settings ~ setting → "sett", boxes → box, series → sery. */
function stem(t: string): string {
  if (t.length <= 4) return t;
  const s = t.replace(/(ations?|tions?|ings?|ates?|ers?|ed)$/, "");
  if (s !== t) return s;
  if (/ies$/.test(t)) return t.slice(0, -3) + "y";
  if (/(ss|x|z|ch|sh)es$/.test(t)) return t.slice(0, -2);
  if (/[^s]s$/.test(t)) return t.slice(0, -1);
  return t;
}

interface Indexed {
  card: HelpCard;
  tf: Map<string, number>;
  len: number;
}

let INDEX: { docs: Indexed[]; df: Map<string, number>; avg: number } | null = null;

function buildIndex() {
  if (INDEX) return INDEX;
  const docs: Indexed[] = [];
  const df = new Map<string, number>();
  let total = 0;
  for (const card of helpCorpus()) {
    const tf = new Map<string, number>();
    const add = (text: string, w: number) => {
      for (const t of tokenize(text)) tf.set(t, (tf.get(t) ?? 0) + w);
    };
    add(card.title, 6);
    add(card.id.split(":").slice(1).join(" "), 4);
    add(card.summary, 3);
    add(card.text, 1);
    const len = Array.from(tf.values()).reduce((a, b) => a + b, 0);
    total += len;
    for (const t of tf.keys()) df.set(t, (df.get(t) ?? 0) + 1);
    docs.push({ card, tf, len });
  }
  INDEX = { docs, df, avg: total / Math.max(1, docs.length) };
  return INDEX;
}

const K1 = 1.4, B = 0.6;

/** Rank the corpus for a query; empty query → []. `kinds` filters. */
export function searchHelp(query: string, opts: { limit?: number; kinds?: CardKind[] } = {}): SearchHit[] {
  const q = tokenize(query);
  if (q.length === 0) return [];
  const { docs, df, avg } = buildIndex();
  const N = docs.length;
  const hits: SearchHit[] = [];
  const lowerQ = query.trim().toLowerCase();
  for (const d of docs) {
    if (opts.kinds && !opts.kinds.includes(d.card.kind)) continue;
    let score = 0;
    let matched = 0;
    for (const t of q) {
      const f = d.tf.get(t);
      if (!f) continue;
      matched++;
      const n = df.get(t) ?? 0;
      const idf = Math.log(1 + (N - n + 0.5) / (n + 0.5));
      score += idf * ((f * (K1 + 1)) / (f + K1 * (1 - B + (B * d.len) / avg)));
    }
    if (matched === 0) continue;
    // All terms present → bonus; exact title / key phrase → bonus.
    if (matched === q.length) score *= 1.5;
    const title = d.card.title.toLowerCase();
    if (title === lowerQ || d.card.id.toLowerCase().endsWith(`:${lowerQ}`)) score *= 3;
    else if (title.includes(lowerQ)) score *= 1.6;
    hits.push({ card: d.card, score, snippet: snippetFor(d.card, q) });
  }
  hits.sort((a, b) => b.score - a.score || a.card.title.localeCompare(b.card.title));
  return hits.slice(0, opts.limit ?? 20);
}

/** The sentence of the card text with the most query terms (plain text). */
export function snippetFor(card: HelpCard, q: string[]): string {
  const plain = card.text.replace(/[*`#>]/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  const sentences = plain.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter(Boolean);
  let best = sentences[0] ?? "";
  let bestN = -1;
  for (const s of sentences) {
    const toks = new Set(tokenize(s));
    const n = q.filter((t) => toks.has(t)).length;
    if (n > bestN) { bestN = n; best = s; }
  }
  return best.length > 220 ? best.slice(0, 217) + "…" : best;
}

/** Tests / hot reload. */
export function resetHelpIndex(): void { INDEX = null; CORPUS = null; }
