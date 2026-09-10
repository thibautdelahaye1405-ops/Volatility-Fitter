// Locks for the Lanes stage's pure helpers (SERIES ARC S5): strip → overlay
// series (frame-position x, NaN gaps, lane colour + dash, label dedupe), the
// playhead line + markers, the frame-index cursor of the filter ring, the
// evidence formatting and the best-lane rule of the table.
import { describe, expect, it } from "vitest";
import {
  bestLane,
  cursorStepIndex,
  EVIDENCE_COLUMNS,
  EVIDENCE_METRICS,
  fmtEvidence,
  formatMetric,
  metricLabel,
  metricValues,
  PLAYHEAD_LABEL,
  playheadLine,
  playheadMarker,
  stripSeries,
} from "./seriesEvidence";
import type { LaneEvidence, LaneSpec, StripPayload } from "./seriesTypes";

const lane = (id: string, over: Partial<LaneSpec> = {}): LaneSpec => ({
  id, name: id, family: "lqd", colour: null, fitMode: null, patchFit: {}, patchOptions: {}, production: false, seed: "cold", ...over,
});

const strip: StripPayload = {
  seriesId: "s1",
  idx: [0, 1, 2],
  ts: ["2026-09-10T13:45:00", "2026-09-10T14:00:00", "2026-09-10T14:15:00"],
  spot: [500, 501, 502],
  atmVol: { a: [0.2, 0.21, 0.22], b: [0.19, null, 0.2] },
  lanes: {
    a: { rmsBp: [4, 5, 6], skew: [-0.1, -0.11, -0.12] },
    b: { rmsBp: [3, null, 2], skew: [-0.2, -0.2, -0.2] },
  },
};

const style = (l: LaneSpec, ordinal: number) => ({ colour: `c${l.id}`, dash: ordinal === 0 ? "" : "6 3" });

describe("stripSeries", () => {
  it("draws one series per lane with frame-position x, NaN gaps, colour and ordinal dash", () => {
    const s = stripSeries(strip, "rmsBp", [{ lane: lane("a"), ordinal: 0 }, { lane: lane("b"), ordinal: 1 }], style);
    expect(s.map((x) => x.label)).toEqual(["a", "b"]);
    expect(s[0].xs).toEqual([0, 1, 2]);
    expect(s[0].ys).toEqual([4, 5, 6]);
    expect(s[0].color).toBe("ca");
    expect(s[0].dash).toBeUndefined();
    expect(s[1].dash).toBe("6 3");
    expect(Number.isNaN(s[1].ys[1])).toBe(true);
  });

  it("reads the ATM vol beside the metrics and yields NaN for an absent lane", () => {
    const s = stripSeries(strip, "atmVol", [{ lane: lane("b"), ordinal: 1 }, { lane: lane("zz"), ordinal: 2 }], style);
    expect(s[0].ys[0]).toBe(0.19);
    expect(Number.isNaN(s[0].ys[1])).toBe(true);
    expect(s[1].ys.every(Number.isNaN)).toBe(true);
    expect(metricValues(strip, "skew", "a")).toEqual([-0.1, -0.11, -0.12]);
  });

  it("disambiguates two lanes sharing a name by their id", () => {
    const s = stripSeries(strip, "rmsBp", [{ lane: lane("a", { name: "LQD" }), ordinal: 0 }, { lane: lane("b", { name: "LQD" }), ordinal: 1 }], style);
    expect(s.map((x) => x.label)).toEqual(["LQD (a)", "LQD (b)"]);
  });
});

describe("playhead", () => {
  const series = stripSeries(strip, "rmsBp", [{ lane: lane("a"), ordinal: 0 }, { lane: lane("b"), ordinal: 1 }], style);

  it("spans the lanes' finite y-extent as a vertical dashed two-point series", () => {
    const line = playheadLine(1, series);
    expect(line).not.toBeNull();
    expect(line?.label).toBe(PLAYHEAD_LABEL);
    expect(line?.xs).toEqual([1, 1]);
    expect(line?.ys).toEqual([2, 6]);
    expect(line?.dash).toBe("3 3");
    expect(playheadLine(0, [{ label: "x", xs: [0], ys: [Number.NaN], color: "#fff" }])).toBeNull();
  });

  it("opens a flat extent so the line has a height", () => {
    const line = playheadLine(0, [{ label: "x", xs: [0, 1], ys: [5, 5], color: "#fff" }]);
    expect(line?.ys[0]).toBeLessThan(5);
    expect(line?.ys[1]).toBeGreaterThan(5);
  });

  it("marks every lane's value at the playhead, skipping missing fits and the playhead line", () => {
    const withLine = [...series, playheadLine(1, series)!];
    const m = playheadMarker(1, withLine, (v) => `${v.toFixed(1)} bp`);
    expect(m).toEqual([{ x: 1, y: 5, label: "a · 5.0 bp", color: "ca" }]);
    expect(playheadMarker(2, series).length).toBe(2);
    expect(playheadMarker(7, series)).toEqual([]);
  });
});

describe("cursorStepIndex (frame-index matching)", () => {
  const frameIdx = [0, 2, null, 5, 9];

  it("returns the step committed on the playhead frame", () => {
    expect(cursorStepIndex(frameIdx, 2)).toBe(1);
    expect(cursorStepIndex(frameIdx, 9)).toBe(4);
  });

  it("falls back to the last step at or before the frame, null before the ring", () => {
    expect(cursorStepIndex(frameIdx, 4)).toBe(1);
    expect(cursorStepIndex(frameIdx, 7)).toBe(3);
    expect(cursorStepIndex(frameIdx, 100)).toBe(4);
    expect(cursorStepIndex([3, 4], 1)).toBeNull();
    expect(cursorStepIndex([], 0)).toBeNull();
    expect(cursorStepIndex([null, null], 0)).toBeNull();
  });
});

describe("labels and formatting", () => {
  it("names every metric of the chip row", () => {
    expect(EVIDENCE_METRICS.map(metricLabel)).toEqual([
      "rms bp", "max err bp", "pull ATM bp", "ζ ATM", "fit ms", "ATM σ", "skew", "curvature",
    ]);
  });

  it("formats the ATM vol as a percentage and the rest at their precision", () => {
    expect(formatMetric("atmVol", 0.2034)).toBe("20.3%");
    expect(formatMetric("rmsBp", 4.26)).toBe("4.3");
    expect(formatMetric("fitMs", 12.7)).toBe("13");
    expect(formatMetric("skew", null)).toBe("—");
    expect(fmtEvidence(1.234, 2)).toBe("1.23");
    expect(fmtEvidence(null, 1)).toBe("—");
    expect(fmtEvidence(Number.NaN, 1)).toBe("—");
  });
});

describe("bestLane", () => {
  const ev = (over: Partial<LaneEvidence>): LaneEvidence => ({
    nFrames: 3, nFailed: 0, meanRmsBp: null, meanMaxIvBp: null, worstFrame: null, roughnessAtmBp: null,
    roughnessSkew: null, meanPullAtmBp: null, meanAbsPullAtmBp: null, meanFitMs: null, zetaAtmStd: null, ...over,
  });
  const rms = EVIDENCE_COLUMNS.find((c) => c.key === "meanRmsBp")!;
  const zeta = EVIDENCE_COLUMNS.find((c) => c.key === "zetaAtmStd")!;

  it("picks the lowest value, ignoring nulls, and needs two finite rows", () => {
    const evidence = { a: ev({ meanRmsBp: 5 }), b: ev({ meanRmsBp: 3 }), c: ev({ meanRmsBp: null }) };
    expect(bestLane(evidence, ["a", "b", "c"], rms)).toBe("b");
    expect(bestLane(evidence, ["a", "c"], rms)).toBeNull();
    expect(bestLane(evidence, ["zz", "a"], rms)).toBeNull();
  });

  it("scores the ζ std by its distance to 1", () => {
    const evidence = { a: ev({ zetaAtmStd: 0.4 }), b: ev({ zetaAtmStd: 1.2 }), c: ev({ zetaAtmStd: 2 }) };
    expect(bestLane(evidence, ["a", "b", "c"], zeta)).toBe("b");
  });
});
