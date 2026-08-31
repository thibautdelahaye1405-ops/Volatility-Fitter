// Help Center page registry (HELP CENTER ARC, H1): the nav order, labels and
// blurbs of the ten pages, and the deep-link grammar shared by the registry
// command `help.open <page>[:<anchor>]`, the Markdown `help:` link scheme and
// the palette. PURE DATA (icons are lucide names resolved by the UI) so the
// parser is vitest-testable without React.
import type { HelpLink, HelpPageId } from "./types";

export interface HelpPageDef {
  id: HelpPageId;
  label: string;
  /** lucide-react icon name (components/help/HelpCenter resolves it). */
  icon: string;
  /** One line under the label in the nav / on the Welcome page. */
  blurb: string;
  /** Rendered as its own nav group start (a divider above). */
  groupStart?: boolean;
}

export const HELP_PAGES: readonly HelpPageDef[] = [
  { id: "welcome", label: "Welcome", icon: "Sparkles", blurb: "Start here — what VolFit is and the four-step workflow" },
  { id: "guides", label: "Guides", icon: "BookOpen", blurb: "One guide per lens and per workflow, with examples" },
  { id: "commands", label: "Command reference", icon: "Terminal", blurb: "Every command: what it does, when it is enabled, an example", groupStart: true },
  { id: "settings", label: "Settings reference", icon: "SlidersHorizontal", blurb: "Every Fit / Options / Market field: type, default, range, effect" },
  { id: "shortcuts", label: "Keyboard shortcuts", icon: "Keyboard", blurb: "The chord table, searchable" },
  { id: "glossary", label: "Glossary", icon: "BookA", blurb: "The vocabulary — smile, slice, node, lit / dark, handle, ζ …" },
  { id: "tips", label: "Tips & tricks", icon: "Lightbulb", blurb: "Curated tips with Try-it actions" },
  { id: "docs", label: "Documentation", icon: "Library", blurb: "The technical notes, the book and the LQD paper, in-app", groupStart: true },
  { id: "ask", label: "Ask @Vol-Fitter", icon: "MessageCircleQuestion", blurb: "Ask a question — answered from the help corpus (and Claude when configured)" },
  { id: "whatsnew", label: "What's new", icon: "Megaphone", blurb: "Release notes in plain language", groupStart: true },
];

export const HELP_PAGE_IDS: readonly HelpPageId[] = HELP_PAGES.map((p) => p.id);

export function isHelpPageId(v: unknown): v is HelpPageId {
  return typeof v === "string" && (HELP_PAGE_IDS as readonly string[]).includes(v);
}

export function helpPageDef(id: HelpPageId): HelpPageDef {
  const d = HELP_PAGES.find((p) => p.id === id);
  if (!d) throw new Error(`unknown help page ${id}`);
  return d;
}

/** Parse a deep link — "settings:gridXNodes", "help:guides:graph", "docs" —
 *  into {page, anchor}; null when the page is unknown. Anchors may contain
 *  ":" themselves (dynamic command ids such as "universe.load:SPX"), so only
 *  the first separator splits. */
export function parseHelpLink(raw: string | undefined | null): HelpLink | null {
  if (!raw) return null;
  let s = raw.trim();
  if (s.startsWith("help:")) s = s.slice(5);
  const i = s.indexOf(":");
  const page = i < 0 ? s : s.slice(0, i);
  const anchor = i < 0 ? "" : s.slice(i + 1).trim();
  if (!isHelpPageId(page)) return null;
  return anchor ? { page, anchor } : { page };
}

/** Inverse of parseHelpLink (no "help:" prefix). */
export function formatHelpLink(link: HelpLink): string {
  return link.anchor ? `${link.page}:${link.anchor}` : link.page;
}

/** The `cmd:` action scheme of help Markdown: "cmd:calibrate.both",
 *  "cmd:help.open?settings:gridXNodes" → {command, arg}. */
export function parseCommandLink(raw: string): { command: string; arg?: string } | null {
  if (!raw.startsWith("cmd:")) return null;
  const s = raw.slice(4);
  const q = s.indexOf("?");
  if (q < 0) return s ? { command: s } : null;
  const command = s.slice(0, q);
  const arg = decodeURIComponent(s.slice(q + 1));
  return command ? { command, arg } : null;
}
