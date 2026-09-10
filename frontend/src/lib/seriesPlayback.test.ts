// Locks the Series lens's pure playback logic (roadmap §3.4): a series never
// autoplays, the terminal frame absorbs unless loop, stepping / scrubbing
// pauses, the keyboard vocabulary, the prefetch order and the gap markers.
import { describe, expect, it } from "vitest";
import {
  BASE_FRAME_MS,
  SPEEDS,
  applyAction,
  clampIndex,
  formatFrameInstant,
  frameDwellMs,
  initialPlayback,
  keyAction,
  parseInstantMs,
  prefetchWindow,
  scrubTo,
  sessionGaps,
  tickPlayback,
} from "./seriesPlayback";
import type { SeriesPlayback } from "./seriesPlayback";

const at = (index: number, patch: Partial<SeriesPlayback> = {}): SeriesPlayback => ({
  ...initialPlayback(), index, ...patch,
});

describe("initialPlayback / clampIndex / frameDwellMs", () => {
  it("starts at frame 0, PAUSED, 1×, no loop", () => {
    expect(initialPlayback()).toEqual({ index: 0, playing: false, speed: 1, loop: false });
  });
  it("clamps into [0, n-1] and reads an empty series / NaN as 0", () => {
    expect(clampIndex(5, 3)).toBe(2);
    expect(clampIndex(-2, 3)).toBe(0);
    expect(clampIndex(1.6, 3)).toBe(2);
    expect(clampIndex(4, 0)).toBe(0);
    expect(clampIndex(NaN, 3)).toBe(0);
  });
  it("dwell = 500 ms / speed over the speed menu; a bad speed reads as 1×", () => {
    expect(SPEEDS).toEqual([0.25, 0.5, 1, 2, 4, 8]);
    expect(frameDwellMs(1)).toBe(BASE_FRAME_MS);
    expect(frameDwellMs(8)).toBe(62.5);
    expect(frameDwellMs(0.25)).toBe(2000);
    expect(frameDwellMs(0)).toBe(BASE_FRAME_MS);
    expect(frameDwellMs(NaN)).toBe(BASE_FRAME_MS);
  });
});

describe("tickPlayback", () => {
  it("advances a playing series by one frame", () => {
    expect(tickPlayback(at(3, { playing: true }), 10)).toEqual(at(4, { playing: true }));
  });
  it("the last frame is absorbing without loop: playing stops, the index stays", () => {
    expect(tickPlayback(at(9, { playing: true }), 10)).toEqual(at(9, { playing: false }));
  });
  it("wraps to 0 at the last frame with loop, still playing", () => {
    expect(tickPlayback(at(9, { playing: true, loop: true }), 10)).toEqual(at(0, { playing: true, loop: true }));
  });
  it("a paused series is only re-clamped; a ≤1-frame series cannot play", () => {
    expect(tickPlayback(at(12), 10)).toEqual(at(9));
    expect(tickPlayback(at(0, { playing: true }), 1)).toEqual(at(0, { playing: false }));
  });
});

describe("scrubTo / applyAction", () => {
  it("scrubbing pauses and clamps", () => {
    expect(scrubTo(at(2, { playing: true }), 40, 10)).toEqual(at(9, { playing: false }));
  });
  it("toggle: play ↔ pause; play at the end without loop restarts from 0", () => {
    expect(applyAction(at(2), "toggle", 10)).toEqual(at(2, { playing: true }));
    expect(applyAction(at(2, { playing: true }), "toggle", 10)).toEqual(at(2, { playing: false }));
    expect(applyAction(at(9), "toggle", 10)).toEqual(at(0, { playing: true }));
    expect(applyAction(at(9, { loop: true }), "toggle", 10)).toEqual(at(9, { playing: true, loop: true }));
    expect(applyAction(at(0), "toggle", 1)).toEqual(at(0, { playing: false }));
  });
  it("stepping pauses and clamps: ±1, ±10, first, last", () => {
    const p = at(5, { playing: true });
    expect(applyAction(p, "next", 10)).toEqual(at(6));
    expect(applyAction(p, "prev", 10)).toEqual(at(4));
    expect(applyAction(p, "next10", 10)).toEqual(at(9));
    expect(applyAction(p, "prev10", 10)).toEqual(at(0));
    expect(applyAction(p, "first", 10)).toEqual(at(0));
    expect(applyAction(p, "last", 10)).toEqual(at(9));
  });
  it("loop toggles without pausing", () => {
    expect(applyAction(at(5, { playing: true }), "loop", 10)).toEqual(at(5, { playing: true, loop: true }));
    expect(applyAction(at(5, { loop: true }), "loop", 10)).toEqual(at(5, { loop: false }));
  });
});

describe("keyAction", () => {
  const k = (key: string, shiftKey = false) => keyAction({ key, shiftKey });
  it("maps the transport vocabulary", () => {
    expect(k(" ")).toBe("toggle");
    expect(k("ArrowRight")).toBe("next");
    expect(k("ArrowRight", true)).toBe("next10");
    expect(k("ArrowLeft")).toBe("prev");
    expect(k("ArrowLeft", true)).toBe("prev10");
    expect(k("Home")).toBe("first");
    expect(k("End")).toBe("last");
    expect(k("l")).toBe("loop");
    expect(k("L")).toBe("loop");
  });
  it("ignores anything else", () => {
    expect(k("Enter")).toBeNull();
    expect(k("a")).toBeNull();
    expect(k("ArrowUp")).toBeNull();
  });
});

describe("prefetchWindow", () => {
  it("ahead in the play direction nearest first, then behind, never the index", () => {
    expect(prefetchWindow(5, 100, 1, 3)).toEqual([6, 7, 8, 4, 3, 2]);
    expect(prefetchWindow(5, 100, -1, 3)).toEqual([4, 3, 2, 6, 7, 8]);
  });
  it("stays within bounds", () => {
    expect(prefetchWindow(1, 4, -1, 3)).toEqual([0, 2, 3]);
    expect(prefetchWindow(0, 1, 1)).toEqual([]);
    expect(prefetchWindow(0, 0, 1)).toEqual([]);
  });
  it("defaults to a radius of 24", () => {
    const w = prefetchWindow(50, 200, 1);
    expect(w.length).toBe(48);
    expect(w[0]).toBe(51);
    expect(w[23]).toBe(74);
    expect(w[24]).toBe(49);
    expect(w[47]).toBe(26);
  });
});

describe("sessionGaps / instants", () => {
  it("naive stamps read as UTC", () => {
    expect(parseInstantMs("2026-09-08T15:45:00")).toBe(Date.UTC(2026, 8, 8, 15, 45));
    expect(parseInstantMs("2026-09-08T15:45:00Z")).toBe(Date.UTC(2026, 8, 8, 15, 45));
  });
  it("flags the frames after a gap over twice the median spacing", () => {
    const ts = [
      "2026-09-08T15:30:00", "2026-09-08T15:45:00", "2026-09-08T16:00:00",
      "2026-09-09T13:30:00", "2026-09-09T13:45:00", "2026-09-09T14:00:00",
    ];
    expect(sessionGaps(ts)).toEqual([3]);
  });
  it("a regular series has no gaps; fewer than three instants never do", () => {
    expect(sessionGaps(["2026-09-08T15:30:00", "2026-09-08T15:45:00", "2026-09-08T16:00:00"])).toEqual([]);
    expect(sessionGaps(["2026-09-08T15:30:00", "2026-09-09T15:45:00"])).toEqual([]);
    expect(sessionGaps([])).toEqual([]);
  });
  it("formats the readout instant straight off the stamp", () => {
    expect(formatFrameInstant("2026-09-08T15:45:00")).toBe("2026-09-08 15:45 UTC");
    expect(formatFrameInstant(null)).toBe("—");
    expect(formatFrameInstant("2026")).toBe("—");
  });
});
