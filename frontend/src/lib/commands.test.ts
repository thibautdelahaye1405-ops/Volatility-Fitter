// Command registry locks (UI SHELL v2 wave 3, C4): ids unique; every chord
// a command advertises is documented in lib/shortcuts.ts (so the palette,
// the menus and Help ▸ Shortcuts agree); every menu-row id the shell renders
// resolves to a definition.
import { describe, expect, it } from "vitest";
import { COMMANDS as REGISTRY, DYNAMIC, commandDef, fuzzyScore } from "./commands";
import type { CommandDef } from "./commands";
import { SHORTCUT_GROUPS } from "./shortcuts";

const COMMANDS: readonly CommandDef[] = REGISTRY;
const documented = SHORTCUT_GROUPS.flatMap((g) => g.items.map((s) => s.keys));

/** A chord is documented when a keys string contains it, or a "… range" covers it. */
function isDocumented(chord: string): boolean {
  if (documented.some((k) => k.includes(chord))) return true;
  const m = /^(\w+)\+(\d)$/.exec(chord); // e.g. Alt+3 ⊂ "Alt+1 … Alt+5"
  if (!m) return false;
  return documented.some((k) => {
    const r = new RegExp(`^${m[1]}\\+(\\d) … ${m[1]}\\+(\\d)$`).exec(k);
    return r !== null && Number(r[1]) <= Number(m[2]) && Number(m[2]) <= Number(r[2]);
  });
}

describe("command registry", () => {
  it("has unique ids and non-empty labels / categories", () => {
    const ids = COMMANDS.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const c of COMMANDS) {
      expect(c.label.trim()).not.toBe("");
      expect(c.category.trim()).not.toBe("");
    }
  });

  it("documents every advertised chord in lib/shortcuts.ts", () => {
    const missing = COMMANDS.filter((c) => c.shortcut && !isDocumented(c.shortcut)).map((c) => `${c.id}: ${c.shortcut}`);
    expect(missing).toEqual([]);
  });

  it("keeps dynamic id prefixes disjoint from static ids", () => {
    for (const prefix of Object.values(DYNAMIC)) {
      expect(COMMANDS.some((c) => c.id.startsWith(prefix))).toBe(false);
    }
  });

  it("resolves every menu-row id the shell renders", () => {
    for (const id of [
      "file.new", "file.open", "file.save", "file.saveAs", "universe.manage", "help.shortcuts",
      "help.api", "help.report", "help.about", "layout.nodesPane", "layout.aside", "layout.statusBar",
      "layout.zen", "layout.rememberView", "layout.reset", "tab.closeAll", "options.open",
    ] as const) {
      expect(commandDef(id).id).toBe(id);
    }
  });

  it("fuzzy-scores subsequences, favouring runs and early hits", () => {
    expect(fuzzyScore("save workspace as", "sws")).toBeGreaterThan(0);
    expect(fuzzyScore("save workspace as", "xyz")).toBe(0);
    expect(fuzzyScore("calibrate", "cal")).toBeGreaterThan(fuzzyScore("calibrate", "cbt"));
    expect(fuzzyScore("anything", "")).toBe(1);
  });
});
