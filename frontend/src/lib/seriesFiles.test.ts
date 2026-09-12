// The Series lens's file memory (lib/seriesFiles): the recent list's
// algebra — head insert with dedup by name, the cap, a lenient restore, the
// latest file, the labels.
import { describe, expect, it } from "vitest";
import {
  SERIES_RECENT_MAX, latestSeriesFile, pushSeriesRecent, restoreSeriesRecent, seriesFileLabel, seriesHandleKey,
  shortFileName,
} from "./seriesFiles";
import type { SeriesRecentEntry } from "./seriesFiles";

const entry = (name: string, at = 1, over: Partial<SeriesRecentEntry> = {}): SeriesRecentEntry => ({
  name, at, id: `id-${name}`, ticker: "NVDA", frames: 10, ...over,
});

describe("pushSeriesRecent", () => {
  it("inserts at the head, moves a re-saved file to the head, caps the list", () => {
    let list = pushSeriesRecent([], entry("a.volfit-series.json", 1));
    list = pushSeriesRecent(list, entry("b.volfit-series.json", 2));
    expect(list.map((e) => e.name)).toEqual(["b.volfit-series.json", "a.volfit-series.json"]);
    list = pushSeriesRecent(list, entry("a.volfit-series.json", 3, { frames: 12 }));
    expect(list.map((e) => e.name)).toEqual(["a.volfit-series.json", "b.volfit-series.json"]);
    expect(list[0].at).toBe(3);
    expect(list[0].frames).toBe(12);
    for (let i = 0; i < SERIES_RECENT_MAX + 3; i++) list = pushSeriesRecent(list, entry(`f${i}.json`, 10 + i));
    expect(list).toHaveLength(SERIES_RECENT_MAX);
    expect(list[0].name).toBe(`f${SERIES_RECENT_MAX + 2}.json`);
  });
});

describe("restoreSeriesRecent", () => {
  it("keeps well-formed rows, fills optional fields, drops the rest", () => {
    const raw = [
      { name: "a.json", at: 5, id: "x", ticker: "SPY", frames: 3 },
      { name: "b.json", id: "y" },
      { name: "", id: "z" },
      { id: "no-name" },
      { name: "c.json" },
      "junk",
      null,
    ];
    const list = restoreSeriesRecent(raw);
    expect(list).toEqual([
      { name: "a.json", at: 5, id: "x", ticker: "SPY", frames: 3 },
      { name: "b.json", at: 0, id: "y", ticker: "", frames: 0 },
    ]);
    expect(restoreSeriesRecent("nope")).toEqual([]);
    expect(restoreSeriesRecent(null)).toEqual([]);
  });
});

describe("latest, labels and keys", () => {
  it("proposes the head entry as the latest", () => {
    expect(latestSeriesFile([])).toBeNull();
    const list = pushSeriesRecent([entry("old.json", 1)], entry("new.json", 2));
    expect(latestSeriesFile(list)?.name).toBe("new.json");
  });
  it("labels a file with its ticker and frame count", () => {
    expect(seriesFileLabel(entry("a.json", 1, { frames: 1 }))).toBe("a.json · NVDA · 1 frame");
    expect(seriesFileLabel(entry("a.json", 1, { ticker: "", frames: 4 }))).toBe("a.json · ? · 4 frames");
  });
  it("keys a file's handle beside the workspace handles", () => {
    expect(seriesHandleKey("a.volfit-series.json")).toBe("series:a.volfit-series.json");
  });
  it("shortens a file name for a button: the series suffix dropped, the middle elided", () => {
    expect(shortFileName("nvda_x.volfit-series.json")).toBe("nvda_x");
    expect(shortFileName("desk.json")).toBe("desk");
    const long = "nvda_5-min-x10-with-a-very-long-name_20260912_1452.volfit-series.json";
    const short = shortFileName(long, 28);
    expect(short).toHaveLength(28);
    expect(short.startsWith("nvda_5-min-x10")).toBe(true);
    expect(short.endsWith("_1452")).toBe(true);
    expect(short).toContain("…");
  });
});
