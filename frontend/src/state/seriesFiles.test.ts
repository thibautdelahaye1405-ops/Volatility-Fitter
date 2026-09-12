// state/seriesFiles: Export remembers the file it saved, the next Open
// picker starts in that file's directory (startIn = its handle, the series
// picker id), Reopen uses the stored handle without a picker, an entry
// without a handle falls back to the picker, and the list survives a
// module reload through localStorage. The File System Access API is stubbed
// on window (jsdom has none): the stubs record the options they received.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const exportSeriesFile = vi.fn();
const importSeriesFile = vi.fn();
const notifySeriesChanged = vi.fn();
vi.mock("./useSeries", () => ({
  exportSeriesFile: (...a: unknown[]) => exportSeriesFile(...a),
  importSeriesFile: (...a: unknown[]) => importSeriesFile(...a),
  notifySeriesChanged: () => notifySeriesChanged(),
}));

type Handle = FileSystemFileHandle & { text: string };
const bundleFor = (id: string, ticker = "NVDA", frames = 2) =>
  ({ schema: "volfit-series/1", savedAt: "2026-09-12T14:52:00", series: { id, spec: { name: "s", ticker, lanes: [] }, frames: Array(frames).fill({}) } });

function fakeHandle(name: string, text = ""): Handle {
  const h = {
    kind: "file", name, text,
    queryPermission: async () => "granted" as PermissionState,
    createWritable: async () => ({ write: async (t: string) => { h.text = t; }, close: async () => undefined }),
    getFile: async () => ({ text: async () => h.text }),
  };
  return h as unknown as Handle;
}

const saveCalls: unknown[] = [];
const openCalls: unknown[] = [];
let nextSave: Handle | null = null;
let nextOpen: Handle | null = null;

async function load() {
  vi.resetModules();
  return import("./seriesFiles");
}

beforeEach(() => {
  localStorage.clear();
  saveCalls.length = 0;
  openCalls.length = 0;
  exportSeriesFile.mockReset();
  importSeriesFile.mockReset();
  notifySeriesChanged.mockReset();
  const w = window as unknown as Record<string, unknown>;
  w.showSaveFilePicker = async (o: unknown) => { saveCalls.push(o); if (nextSave === null) throw Object.assign(new Error("cancel"), { name: "AbortError" }); return nextSave; };
  w.showOpenFilePicker = async (o: unknown) => { openCalls.push(o); if (nextOpen === null) throw Object.assign(new Error("cancel"), { name: "AbortError" }); return [nextOpen]; };
});
afterEach(() => {
  const w = window as unknown as Record<string, unknown>;
  delete w.showSaveFilePicker;
  delete w.showOpenFilePicker;
});

describe("Export remembers the file, Open starts there and proposes it", () => {
  it("saves through the picker, records the file at the head, and the next open picker starts in its directory", async () => {
    const mod = await load();
    mod.forgetSeriesFiles();
    exportSeriesFile.mockResolvedValue(bundleFor("abc"));
    const saved = fakeHandle("nvda_s_20260912_1452.volfit-series.json");
    nextSave = saved;
    const doc = { id: "abc", spec: { ticker: "NVDA", name: "s", lanes: [] }, frames: [{}, {}] } as never;
    const name = await mod.exportSeries("abc", doc);
    expect(name).toBe(saved.name);
    expect(saved.text).toContain('"volfit-series/1"');
    expect(saveCalls[0]).toMatchObject({ id: "volfit-series", suggestedName: expect.stringMatching(/\.volfit-series\.json$/) });
    expect(mod.seriesRecentNow()[0]).toMatchObject({ name: saved.name, id: "abc", ticker: "NVDA", frames: 2 });
    expect(await mod.lastSeriesHandle()).toBe(saved);

    // The next Open: the picker starts in the saved file's directory.
    const picked = fakeHandle("other.volfit-series.json", JSON.stringify(bundleFor("def", "SPY", 3)));
    nextOpen = picked;
    importSeriesFile.mockResolvedValue({ id: "def", spec: { ticker: "SPY" }, frames: [{}, {}, {}] });
    const res = await mod.openSeriesPicker();
    expect(openCalls[0]).toMatchObject({ id: "volfit-series", startIn: saved, multiple: false });
    expect(res).toEqual({ id: "def", name: picked.name, ticker: "SPY", frames: 3 });
    expect(notifySeriesChanged).toHaveBeenCalledTimes(1);
    expect(mod.seriesRecentNow().map((e) => e.name)).toEqual([picked.name, saved.name]);
  });

  it("reopens the latest file through its handle without a picker; an entry without a handle picks instead", async () => {
    const mod = await load();
    mod.forgetSeriesFiles();
    const h = fakeHandle("kept.volfit-series.json", JSON.stringify(bundleFor("k1")));
    mod.rememberSeriesFile({ name: h.name, at: 1, id: "k1", ticker: "NVDA", frames: 2 }, h);
    importSeriesFile.mockResolvedValue({ id: "k1", spec: { ticker: "NVDA" }, frames: [{}, {}] });
    const res = await mod.openSeriesRecent(mod.seriesRecentNow()[0]);
    expect(res?.id).toBe("k1");
    expect(openCalls).toHaveLength(0);

    mod.rememberSeriesFile({ name: "downloaded.volfit-series.json", at: 2, id: "d1", ticker: "SPY", frames: 1 }, null);
    nextOpen = null; // the picker is cancelled
    const viaPicker = await mod.openSeriesRecent(mod.seriesRecentNow()[0]);
    expect(viaPicker).toBeNull();
    expect(openCalls).toHaveLength(1); // no handle → the picker, started in the last handled file's directory
    expect(openCalls[0]).toMatchObject({ startIn: h });
  });

  it("refuses a file that is not a series bundle and persists the list across a reload", async () => {
    const mod = await load();
    mod.forgetSeriesFiles();
    nextOpen = fakeHandle("desk.json", JSON.stringify({ schema: "volfit-workspace/1" }));
    await expect(mod.openSeriesPicker()).rejects.toThrow(/not a series file/);
    expect(importSeriesFile).not.toHaveBeenCalled();
    mod.rememberSeriesFile({ name: "a.volfit-series.json", at: 3, id: "a", ticker: "NVDA", frames: 4 }, null);
    const again = await load();
    expect(again.seriesRecentNow()).toEqual([{ name: "a.volfit-series.json", at: 3, id: "a", ticker: "NVDA", frames: 4 }]);
  });
});
