// Help search locks (HELP CENTER ARC): the corpus covers every kind, the
// tokenizer splits camelCase keys, and the obvious queries rank the obvious
// card first — the local tier of Ask @Vol-Fitter depends on it.
import { beforeAll, describe, expect, it } from "vitest";
import { helpCorpus, resetHelpIndex, searchHelp, snippetFor, tokenize } from "./search";

describe("help search", () => {
  beforeAll(() => resetHelpIndex());

  it("builds a corpus with every kind and unique ids", () => {
    const cards = helpCorpus();
    const kinds = new Set(cards.map((c) => c.kind));
    for (const k of ["command", "setting", "glossary", "tip", "guide", "doc", "whatsnew", "shortcut"]) expect(kinds.has(k as never)).toBe(true);
    expect(new Set(cards.map((c) => c.id)).size).toBe(cards.length);
    for (const c of cards) {
      expect(c.title.trim()).not.toBe("");
      expect(c.link.trim()).not.toBe("");
    }
  });

  it("tokenizes camelCase keys and drops stop words", () => {
    // "gridXNodes" → grid · x · nodes; single letters drop, "nodes" stems to "node".
    expect(tokenize("gridXNodes")).toEqual(["grid", "node"]);
    const toks = tokenize("How do I calibrate the surface?");
    expect(toks).not.toContain("how");
    expect(toks).not.toContain("the");
    expect(toks.length).toBe(2);
  });

  it("ranks the exact setting key first", () => {
    expect(searchHelp("gridXNodes")[0]?.card.id).toBe("setting:gridXNodes");
    expect(searchHelp("haircut")[0]?.card.kind === "setting" || searchHelp("haircut")[0]?.card.id.includes("haircut")).toBe(true);
  });

  it("ranks the command for a verb query", () => {
    const top = searchHelp("calibrate local vol only").slice(0, 3).map((h) => h.card.id);
    expect(top).toContain("command:calibrate.lv");
    expect(searchHelp("command palette")[0]?.card.id).toMatch(/palette|shortcut/);
  });

  it("finds glossary and guide cards for concept queries", () => {
    const kinds = searchHelp("lit dark node", { limit: 8 }).map((h) => h.card.kind);
    expect(kinds).toContain("glossary");
    expect(searchHelp("graph", { kinds: ["guide"] })[0]?.card.id).toBe("guide:graph");
  });

  it("returns nothing for an empty query and respects the limit", () => {
    expect(searchHelp("   ")).toEqual([]);
    expect(searchHelp("fit", { limit: 3 }).length).toBeLessThanOrEqual(3);
  });

  it("snippets the sentence with the most query terms", () => {
    const card = { id: "x", kind: "tip" as const, title: "T", summary: "", link: "tips:x", text: "First sentence here. The split editor shows two tabs side by side. Last." };
    expect(snippetFor(card, tokenize("split editor"))).toBe("The split editor shows two tabs side by side.");
  });
});
