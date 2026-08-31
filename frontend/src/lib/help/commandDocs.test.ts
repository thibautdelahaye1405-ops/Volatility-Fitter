// Command documentation locks (HELP CENTER ARC): every registry command and
// every dynamic prefix has a doc; every doc names a real id; summaries are
// one sentence; examples exist; `related` and `guide` resolve; and the house
// style holds (no audit / defensive vocabulary).
import { describe, expect, it } from "vitest";
import { COMMANDS, DYNAMIC } from "../commands";
import { COMMAND_DOCS, commandDoc } from "./commandDocs";
import { GUIDES } from "./guides";
import { parseHelpLink } from "./pages";

const registryIds = new Set<string>([...COMMANDS.map((c) => c.id), ...Object.values(DYNAMIC)]);
const docIds = new Set(COMMAND_DOCS.map((d) => d.id));
const guideIds = new Set(GUIDES.map((g) => g.id));
const BANNED = /\b(honest|honestly|audit|promise|claim)\b/i;

describe("command docs", () => {
  it("documents every registry command and dynamic prefix exactly once", () => {
    const missing = [...registryIds].filter((id) => !docIds.has(id));
    expect(missing, `undocumented commands: ${missing.join(", ")}`).toEqual([]);
    const unknown = [...docIds].filter((id) => !registryIds.has(id));
    expect(unknown, `docs for unknown commands: ${unknown.join(", ")}`).toEqual([]);
    expect(docIds.size).toBe(COMMAND_DOCS.length);
  });

  it("has a one-sentence summary, details and an example everywhere", () => {
    for (const d of COMMAND_DOCS) {
      expect(d.summary.trim(), d.id).not.toBe("");
      expect(d.summary.trim().split(/(?<=[.!?])\s+(?=[A-Z])/).length, `${d.id}: summary is one sentence`).toBe(1);
      expect(d.details.trim().length, d.id).toBeGreaterThan(40);
      expect(d.example.trim().length, d.id).toBeGreaterThan(20);
    }
  });

  it("resolves related ids, guides and deep links", () => {
    for (const d of COMMAND_DOCS) {
      if (d.guide) expect(guideIds.has(d.guide), `${d.id}: guide ${d.guide}`).toBe(true);
      for (const r of d.related ?? []) {
        if (r.startsWith("help:")) expect(parseHelpLink(r), `${d.id}: link ${r}`).not.toBeNull();
        else expect(registryIds.has(r), `${d.id}: related ${r}`).toBe(true);
      }
      for (const m of `${d.details}\n${d.example}`.matchAll(/\]\((help:[^)]+|cmd:[^)?]+)/g)) {
        if (m[1].startsWith("help:")) expect(parseHelpLink(m[1]), `${d.id}: ${m[1]}`).not.toBeNull();
        else expect(registryIds.has(m[1].slice(4)), `${d.id}: ${m[1]}`).toBe(true);
      }
    }
  });

  it("keeps the house style", () => {
    for (const d of COMMAND_DOCS) expect(`${d.summary} ${d.details} ${d.example}`, d.id).not.toMatch(BANNED);
  });

  it("looks up dynamic runtime ids through their prefix", () => {
    expect(commandDoc("calibrate.both")?.id).toBe("calibrate.both");
    expect(commandDoc(`${DYNAMIC.universeLoad}US tech`)?.id).toBe(DYNAMIC.universeLoad);
    expect(commandDoc("nope.nothing")).toBeUndefined();
  });
});
