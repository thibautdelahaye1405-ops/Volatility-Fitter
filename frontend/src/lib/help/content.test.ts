// Help corpus integrity locks (HELP CENTER ARC): glossary, tips, guides, the
// documentation catalog and What's new — unique ids, complete coverage of the
// GuideId union, resolvable cross-links, house style.
import { describe, expect, it } from "vitest";
import { COMMANDS } from "../commands";
import { GLOSSARY } from "./glossary";
import { TIPS } from "./tips";
import { GUIDES, guide, guideForLens } from "./guides";
import { DOCS_CATALOG, docEntry } from "./docsCatalog";
import { WHATS_NEW } from "./whatsNew";
import { parseHelpLink } from "./pages";
import { SETTING_DOCS } from "./settingsDocs";
import type { GuideId } from "./types";

const BANNED = /\b(honest|honestly|audit|promise|claim)\b/i;
const commandIds = new Set<string>(COMMANDS.map((c) => c.id));
const glossaryIds = new Set(GLOSSARY.map((g) => g.id));
const docIds = new Set(DOCS_CATALOG.map((d) => d.id));
const settingKeys = new Set(SETTING_DOCS.map((s) => s.key));
const GUIDE_IDS: GuideId[] = ["getting-started", "workbench", "universe", "data-sources", "workflow", "graph", "forwards", "parametric", "localvol", "quality", "options", "priors", "filter", "files"];

/** A help: link must parse and its anchor must exist in the target corpus. */
function expectLinkResolves(link: string, where: string) {
  const l = parseHelpLink(link);
  expect(l, `${where}: ${link}`).not.toBeNull();
  if (!l?.anchor) return;
  const ok: Record<string, boolean> = {
    glossary: glossaryIds.has(l.anchor),
    settings: settingKeys.has(l.anchor),
    guides: (GUIDE_IDS as string[]).includes(l.anchor),
    commands: commandIds.has(l.anchor) || l.anchor.includes(":"),
    docs: docIds.has(l.anchor),
    tips: TIPS.some((t) => t.id === l.anchor),
  };
  if (l.page in ok) expect(ok[l.page], `${where}: ${link} anchor not found`).toBe(true);
}

describe("glossary", () => {
  it("has unique kebab-case ids, the core vocabulary, and resolvable links", () => {
    expect(new Set(GLOSSARY.map((g) => g.id)).size).toBe(GLOSSARY.length);
    expect(GLOSSARY.length).toBeGreaterThanOrEqual(45);
    for (const g of GLOSSARY) {
      expect(g.id, g.term).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
      expect(g.short.trim(), g.id).not.toBe("");
      expect(g.long.trim().length, g.id).toBeGreaterThan(40);
      expect(`${g.short} ${g.long}`, g.id).not.toMatch(BANNED);
      for (const r of g.related ?? []) expect(glossaryIds.has(r), `${g.id}: related ${r}`).toBe(true);
      for (const l of g.links ?? []) {
        if (l.startsWith("help:")) expectLinkResolves(l, `glossary ${g.id}`);
        else if (l.startsWith("cmd:")) expect(commandIds.has(l.slice(4).split("?")[0]), `${g.id}: ${l}`).toBe(true);
        else expect(docIds.has(l), `${g.id}: doc ${l}`).toBe(true);
      }
    }
    for (const must of ["lit-dark", "smile", "slice", "node", "prior"]) expect(glossaryIds.has(must), must).toBe(true);
  });
});

describe("tips", () => {
  it("has unique ids, valid scopes/levels and runnable actions", () => {
    expect(new Set(TIPS.map((t) => t.id)).size).toBe(TIPS.length);
    expect(TIPS.length).toBeGreaterThanOrEqual(24);
    for (const t of TIPS) {
      expect(["shell", "graph", "forwards", "parametric", "localvol", "quality"], t.id).toContain(t.scope);
      expect(["basic", "pro"], t.id).toContain(t.level);
      expect(t.body, t.id).not.toMatch(BANNED);
      if (t.action) {
        expect(commandIds.has(t.action.command), `${t.id}: ${t.action.command}`).toBe(true);
        if (t.action.command === "help.open") expectLinkResolves(t.action.arg ?? "", `tip ${t.id}`);
      }
    }
  });
});

describe("guides", () => {
  it("covers every GuideId once, maps every lens, and links resolve", () => {
    expect(GUIDES.map((g) => g.id).sort()).toEqual([...GUIDE_IDS].sort());
    for (const lens of ["graph", "forwards", "parametric", "localvol", "quality"] as const) {
      expect(guideForLens(lens)).toBe(lens);
      expect(guide(guideForLens(lens)).lens).toBe(lens);
    }
    for (const g of GUIDES) {
      expect(g.body.split("\n").length, g.id).toBeGreaterThan(20);
      expect(g.body, g.id).toMatch(/^## /m);
      expect(`${g.summary}\n${g.body}`, g.id).not.toMatch(BANNED);
      for (const m of g.body.matchAll(/\]\((help:[^)]+)\)/g)) expectLinkResolves(m[1], `guide ${g.id}`);
      for (const m of g.body.matchAll(/\]\(cmd:([^)?]+)/g)) expect(commandIds.has(m[1]), `${g.id}: cmd ${m[1]}`).toBe(true);
    }
  });
});

describe("docs catalog", () => {
  it("has unique ids, a file per entry, allow-listed roots and resolvable relations", () => {
    expect(new Set(DOCS_CATALOG.map((d) => d.id)).size).toBe(DOCS_CATALOG.length);
    const roots = new Set(["notes-md", "handoff", "docs", "notes-pdf", "book", "paper"]);
    for (const d of DOCS_CATALOG) {
      expect(d.markdown || d.pdf, `${d.id}: no file`).toBeTruthy();
      if (d.markdown) { expect(roots.has(d.markdown.root), d.id).toBe(true); expect(d.markdown.name, d.id).toMatch(/\.md$/); }
      if (d.pdf) { expect(roots.has(d.pdf.root), d.id).toBe(true); expect(d.pdf.name, d.id).toMatch(/\.pdf$/); }
      expect(d.abstract.trim().length, d.id).toBeGreaterThan(20);
      for (const r of d.related ?? []) {
        if (r.startsWith("help:")) expectLinkResolves(r, `doc ${d.id}`);
        else expect(docIds.has(r), `${d.id}: related ${r}`).toBe(true);
      }
    }
    expect(docEntry("00_system_overview")?.markdown?.root).toBe("notes-md");
    expect(DOCS_CATALOG.some((d) => d.kind === "book")).toBe(true);
    expect(DOCS_CATALOG.some((d) => d.kind === "paper")).toBe(true);
  });
});

describe("what's new", () => {
  it("is newest-first with ISO dates and non-empty bullets", () => {
    expect(WHATS_NEW.length).toBeGreaterThanOrEqual(8);
    for (let i = 1; i < WHATS_NEW.length; i++) expect(WHATS_NEW[i - 1].date >= WHATS_NEW[i].date, `${WHATS_NEW[i].title}`).toBe(true);
    for (const w of WHATS_NEW) {
      expect(w.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(w.items.length).toBeGreaterThan(0);
      expect(w.items.join(" ")).not.toMatch(BANNED);
    }
    expect(WHATS_NEW.some((w) => /help center/i.test(w.title))).toBe(true); // the Help Center release is in the log
  });
});
