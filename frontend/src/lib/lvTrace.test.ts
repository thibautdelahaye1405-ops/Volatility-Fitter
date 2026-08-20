// Pacer / scrubber pure logic for the LV calibration replay (V3.5 item 13).
import { describe, expect, it } from "vitest";
import {
  clampFrame,
  costSparkPoints,
  initialPlayback,
  rmsBarHeights,
  scrubTo,
  tickPlayback,
  togglePlay,
  traceMaxRms,
} from "./lvTrace";

describe("initialPlayback (epoch re-key)", () => {
  it("auto-plays a fresh multi-frame trace from frame 0", () => {
    expect(initialPlayback(10, false)).toEqual({ index: 0, playing: true });
  });
  it("reduced motion short-circuits to the FINAL frame, paused", () => {
    expect(initialPlayback(10, true)).toEqual({ index: 9, playing: false });
  });
  it("degenerate traces (≤1 frame) land on the last frame, paused", () => {
    expect(initialPlayback(1, false)).toEqual({ index: 0, playing: false });
    expect(initialPlayback(0, false)).toEqual({ index: 0, playing: false });
  });
});

describe("tickPlayback (the pacer)", () => {
  it("advances one frame per tick and stops AT the terminal frame", () => {
    let p = initialPlayback(3, false);
    p = tickPlayback(p, 3);
    expect(p).toEqual({ index: 1, playing: true });
    p = tickPlayback(p, 3);
    expect(p).toEqual({ index: 2, playing: false }); // terminal: absorbing
    p = tickPlayback(p, 3);
    expect(p).toEqual({ index: 2, playing: false }); // never wraps / re-gates
  });
  it("a full replay visits every frame exactly once", () => {
    const seen: number[] = [];
    let p = initialPlayback(5, false);
    seen.push(p.index);
    while (p.playing) {
      p = tickPlayback(p, 5);
      seen.push(p.index);
    }
    expect(seen).toEqual([0, 1, 2, 3, 4]);
  });
});

describe("scrubTo / togglePlay (the scrubber)", () => {
  it("scrubbing pauses and clamps into [0, n-1]", () => {
    expect(scrubTo(2, 5)).toEqual({ index: 2, playing: false });
    expect(scrubTo(99, 5)).toEqual({ index: 4, playing: false });
    expect(scrubTo(-3, 5)).toEqual({ index: 0, playing: false });
  });
  it("play at the terminal frame RESTARTS the replay; pause holds the frame", () => {
    expect(togglePlay({ index: 4, playing: false }, 5)).toEqual({ index: 0, playing: true });
    expect(togglePlay({ index: 2, playing: false }, 5)).toEqual({ index: 2, playing: true });
    expect(togglePlay({ index: 2, playing: true }, 5)).toEqual({ index: 2, playing: false });
    expect(togglePlay({ index: 0, playing: false }, 1)).toEqual({ index: 0, playing: false });
  });
  it("clampFrame is safe on empty traces", () => {
    expect(clampFrame(3, 0)).toBe(0);
  });
});

describe("frames → display state", () => {
  const frames = [
    { expiryRms: [4, 2, 1] },
    { expiryRms: [2, 1, 0.5] },
    { expiryRms: [1, 0.5, 0.25] },
  ];
  it("bars use the STABLE trace-wide max so they descend over the replay", () => {
    const max = traceMaxRms(frames);
    expect(max).toBe(4);
    expect(rmsBarHeights(frames[0].expiryRms, max)).toEqual([1, 0.5, 0.25]);
    expect(rmsBarHeights(frames[2].expiryRms, max)).toEqual([0.25, 0.125, 0.0625]);
  });
  it("a zero max yields zero bars, never NaN", () => {
    expect(rmsBarHeights([0, 0], 0)).toEqual([0, 0]);
  });
  it("the cost sparkline traces left→right up to the current frame", () => {
    const costs = [100, 10, 1];
    expect(costSparkPoints(costs, 0, 100, 30)).toBe(""); // a single point draws nothing
    const half = costSparkPoints(costs, 1, 100, 30).split(" ");
    expect(half).toHaveLength(2);
    const full = costSparkPoints(costs, 2, 100, 30).split(" ");
    expect(full).toHaveLength(3);
    // Log-scaled, monotone costs: y descends... i.e. pixel y INCREASES (SVG).
    const ys = full.map((p) => Number(p.split(",")[1]));
    expect(ys[0]).toBeLessThan(ys[1]);
    expect(ys[1]).toBeLessThan(ys[2]);
    // x spans the full width regardless of the scrub position.
    expect(full[2].split(",")[0]).toBe("100.0");
  });
});
