// Help Center page registry + deep-link grammar locks (HELP CENTER ARC).
import { describe, expect, it } from "vitest";
import { HELP_PAGES, HELP_PAGE_IDS, formatHelpLink, helpPageDef, isHelpPageId, parseCommandLink, parseHelpLink } from "./pages";

describe("help pages", () => {
  it("lists ten unique pages with labels, icons and blurbs", () => {
    expect(HELP_PAGES.length).toBe(10);
    expect(new Set(HELP_PAGE_IDS).size).toBe(HELP_PAGE_IDS.length);
    for (const p of HELP_PAGES) {
      expect(p.label.trim()).not.toBe("");
      expect(p.icon.trim()).not.toBe("");
      expect(p.blurb.trim()).not.toBe("");
    }
    expect(HELP_PAGES[0].id).toBe("welcome");
    expect(helpPageDef("ask").label).toBe("Ask @Vol-Fitter");
    expect(() => helpPageDef("nope" as never)).toThrow();
  });

  it("parses deep links with and without the help: prefix, keeping colons inside anchors", () => {
    expect(parseHelpLink("settings:gridXNodes")).toEqual({ page: "settings", anchor: "gridXNodes" });
    expect(parseHelpLink("help:guides:graph")).toEqual({ page: "guides", anchor: "graph" });
    expect(parseHelpLink("docs")).toEqual({ page: "docs" });
    expect(parseHelpLink("commands:universe.load:SPX")).toEqual({ page: "commands", anchor: "universe.load:SPX" });
    expect(parseHelpLink(" whatsnew : 2026-08-31 ".replace(/ /g, ""))).toEqual({ page: "whatsnew", anchor: "2026-08-31" });
    expect(parseHelpLink("nowhere:x")).toBeNull();
    expect(parseHelpLink("")).toBeNull();
    expect(parseHelpLink(undefined)).toBeNull();
    expect(isHelpPageId("tips")).toBe(true);
    expect(isHelpPageId("Tips")).toBe(false);
  });

  it("formats links back and round-trips", () => {
    for (const raw of ["settings:haircut", "guides", "commands:tab.split"]) {
      expect(formatHelpLink(parseHelpLink(raw)!)).toBe(raw);
    }
  });

  it("parses cmd: action links with an optional argument", () => {
    expect(parseCommandLink("cmd:calibrate.both")).toEqual({ command: "calibrate.both" });
    expect(parseCommandLink("cmd:help.open?settings:gridXNodes")).toEqual({ command: "help.open", arg: "settings:gridXNodes" });
    expect(parseCommandLink("cmd:universe.saveAs?my%20desk")).toEqual({ command: "universe.saveAs", arg: "my desk" });
    expect(parseCommandLink("help:docs")).toBeNull();
    expect(parseCommandLink("cmd:")).toBeNull();
  });
});
