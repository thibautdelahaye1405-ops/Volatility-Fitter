// Walkthrough locks (HELP CENTER ARC): twelve steps in the ratified order,
// every anchor declared and labelled, every Try-it action a registry
// command, bodies short and in the house style.
import { describe, expect, it } from "vitest";
import { COMMANDS } from "../commands";
import { TOUR_ANCHORS, TOUR_STEPS } from "./walkthrough";

const ORDER = ["brand", "menu.file", "menu.options", "menu.universe", "center", "activity", "nodes", "tabs", "main", "menu.view", "status", "menu.help"];
const ids = new Set<string>(COMMANDS.map((c) => c.id));

describe("walkthrough", () => {
  it("has exactly twelve steps in the ratified anchor order", () => {
    expect(TOUR_STEPS.map((s) => s.anchor)).toEqual(ORDER);
    expect(new Set(TOUR_STEPS.map((s) => s.id)).size).toBe(12);
  });

  it("declares and labels every anchor it uses (and the menu.layout one)", () => {
    for (const s of TOUR_STEPS) expect(TOUR_ANCHORS[s.anchor], s.anchor).toBeTruthy();
    for (const a of Object.keys(TOUR_ANCHORS)) expect((TOUR_ANCHORS as Record<string, string>)[a].trim()).not.toBe("");
    expect(Object.keys(TOUR_ANCHORS)).toContain("menu.layout");
  });

  it("keeps bodies short, titles tight and actions runnable", () => {
    for (const s of TOUR_STEPS) {
      expect(s.title.split(/\s+/).length, s.id).toBeLessThanOrEqual(6);
      expect(s.body.length, s.id).toBeLessThan(700);
      expect(s.body, s.id).not.toMatch(/\b(honest|honestly|audit|promise|claim)\b/i);
      if (s.action) {
        expect(ids.has(s.action.command), `${s.id}: ${s.action.command}`).toBe(true);
        expect(s.action.command, s.id).not.toBe("file.new");
      }
    }
  });
});
