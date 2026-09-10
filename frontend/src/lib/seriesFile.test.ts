import { describe, expect, it } from "vitest";
import { SERIES_FILE_SCHEMA, parseSeriesBundle, seriesFilename } from "./seriesFile";
import { classifyBundle } from "./snapshotFile";

const bundle = {
  schema: SERIES_FILE_SCHEMA,
  series: { id: "abc123", spec: { name: "SPY 15 min", ticker: "SPY", lanes: [{ id: "a" }, { id: "b" }] }, frames: [{}, {}, {}] },
};

describe("parseSeriesBundle", () => {
  it("summarizes a valid envelope", () => {
    const p = parseSeriesBundle(bundle);
    expect(p.ok).toBe(true);
    if (p.ok) expect(p.summary).toEqual({ schema: SERIES_FILE_SCHEMA, id: "abc123", name: "SPY 15 min", ticker: "SPY", frames: 3, lanes: 2 });
  });
  it("refuses the wrong family, major or shape", () => {
    expect(parseSeriesBundle(null)).toMatchObject({ ok: false, error: "not a JSON object" });
    expect(parseSeriesBundle({})).toMatchObject({ ok: false });
    expect(parseSeriesBundle({ schema: "volfit-snapshot/1" })).toMatchObject({ ok: false, error: expect.stringContaining("not a series file") });
    expect(parseSeriesBundle({ schema: "volfit-series/2", series: bundle.series })).toMatchObject({ ok: false, error: expect.stringContaining("unsupported") });
    expect(parseSeriesBundle({ schema: SERIES_FILE_SCHEMA })).toMatchObject({ ok: false, error: expect.stringContaining("no series document") });
    expect(parseSeriesBundle({ schema: SERIES_FILE_SCHEMA, series: { spec: {} } })).toMatchObject({ ok: false, error: expect.stringContaining("no id") });
  });
});

describe("classifyBundle routes series files", () => {
  it("recognizes the series family beside workspace and snapshot", () => {
    expect(classifyBundle(bundle)).toBe("series");
    expect(classifyBundle({ schema: "volfit-snapshot/1" })).toBe("snapshot");
    expect(classifyBundle({ schema: "volfit-workspace/1" })).toBe("workspace");
    expect(classifyBundle({ schema: "other/1" })).toBeNull();
  });
});

describe("seriesFilename", () => {
  it("builds a tidy name from the ticker, the series name and the stamp", () => {
    expect(seriesFilename("SPY", "SPY 2026-08-19 · 15 min", "2026-09-10T15:12:07Z")).toBe(
      "spy_spy-2026-08-19-15-min_20260910_1512.volfit-series.json",
    );
    expect(seriesFilename("", "", "")).toBe("series_series.volfit-series.json");
  });
});
