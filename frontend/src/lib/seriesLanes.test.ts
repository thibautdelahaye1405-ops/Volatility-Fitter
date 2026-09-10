// Locks the lane presentation helpers of the Series lens (roadmap §3.4).
import { describe, expect, it } from "vitest";
import { MODEL_COLORS } from "./modelColor";
import {
  LANE_DASHES,
  LV_COLOUR,
  familyColour,
  laneCurve,
  laneLabel,
  laneSlice,
  laneStyle,
  nearestExpiry,
  productionLane,
  sliceMetric,
  stageAxisMode,
  visibleLanes,
} from "./seriesLanes";
import type { FramePayload, LaneSpec } from "./seriesTypes";

const lane = (id: string, patch: Partial<LaneSpec> = {}): LaneSpec => ({
  id, name: id.toUpperCase(), family: "lqd", colour: null, fitMode: null,
  patchFit: {}, patchOptions: {}, production: false, seed: "cold", ...patch,
});

const frame: FramePayload = {
  seriesId: "s", idx: 3, ts: "2026-09-08T15:45:00", quoteKind: "quotes", spot: 100,
  expiries: ["2026-10-16", "2026-09-18", "2026-12-18"],
  forwards: {}, market: {},
  lanes: {
    a: {
      laneId: "a", status: "done", surface: null, term: [], metrics: {},
      slices: [
        { expiry: "2026-09-18", t: 0.03, forward: 100, k: [-0.1, 0, 0.1], iv: [0.25, 0.2, NaN], atmVol: 0.2, skew: null, curvature: null, metrics: { rmsBp: 4.5, fitMs: "x" } },
      ],
    },
  },
};

describe("laneStyle / laneLabel", () => {
  it("family colours from the Compare palette, orange for Local Vol", () => {
    expect(familyColour("lqd")).toBe(MODEL_COLORS.lqd);
    expect(familyColour("svi")).toBe(MODEL_COLORS.svi);
    expect(familyColour("sigmoid")).toBe(MODEL_COLORS.sigmoid);
    expect(familyColour("lv")).toBe(LV_COLOUR);
    expect(LV_COLOUR).not.toBe(MODEL_COLORS.essvi);
  });
  it("the lane's own colour wins; dashes cycle by ordinal", () => {
    expect(laneStyle(lane("a", { colour: "#123456" }), 0)).toEqual({ colour: "#123456", dash: "" });
    expect(laneStyle(lane("a", { colour: "  " }), 1)).toEqual({ colour: MODEL_COLORS.lqd, dash: "6 3" });
    expect(laneStyle(lane("a"), 2).dash).toBe("2 2");
    expect(laneStyle(lane("a"), 3).dash).toBe("8 3 2 3");
    expect(laneStyle(lane("a"), 4).dash).toBe("");
    expect(LANE_DASHES.length).toBe(4);
  });
  it("labels: the name, else the family and the id", () => {
    expect(laneLabel(lane("a", { name: "LQD free" }))).toBe("LQD free");
    expect(laneLabel(lane("a", { name: "", family: "lv" }))).toBe("Local Vol · a");
  });
});

describe("laneCurve / laneSlice / sliceMetric", () => {
  it("zips k / iv into chart points, dropping non-finite pairs", () => {
    expect(laneCurve(frame, "a", "2026-09-18")).toEqual([{ k: -0.1, vol: 0.25 }, { k: 0, vol: 0.2 }]);
  });
  it("is empty for an unknown lane or expiry", () => {
    expect(laneCurve(frame, "zz", "2026-09-18")).toEqual([]);
    expect(laneCurve(frame, "a", "2027-01-01")).toEqual([]);
    expect(laneSlice(frame, "a", "2027-01-01")).toBeNull();
  });
  it("reads a numeric metric, null otherwise", () => {
    const s = laneSlice(frame, "a", "2026-09-18");
    expect(sliceMetric(s, "rmsBp")).toBe(4.5);
    expect(sliceMetric(s, "fitMs")).toBeNull();
    expect(sliceMetric(s, "nope")).toBeNull();
    expect(sliceMetric(null, "rmsBp")).toBeNull();
  });
});

describe("nearestExpiry", () => {
  it("the wanted expiry when carried, else the nearest later, else the last", () => {
    expect(nearestExpiry(frame, "2026-10-16")).toBe("2026-10-16");
    expect(nearestExpiry(frame, "2026-09-25")).toBe("2026-10-16");
    expect(nearestExpiry(frame, "2027-03-01")).toBe("2026-12-18");
  });
  it("the first expiry when nothing is wanted; null on an empty frame", () => {
    expect(nearestExpiry(frame, null)).toBe("2026-09-18");
    expect(nearestExpiry({ ...frame, expiries: [] }, "2026-09-18")).toBeNull();
  });
});

describe("productionLane / visibleLanes", () => {
  it("the starred lane, else the first, else null", () => {
    const lanes = [lane("a"), lane("b", { production: true })];
    expect(productionLane(lanes)?.id).toBe("b");
    expect(productionLane([lane("a"), lane("b")])?.id).toBe("a");
    expect(productionLane([])).toBeNull();
  });
  it("visible lanes keep their ordinal among ALL lanes", () => {
    const lanes = [lane("a"), lane("b"), lane("c")];
    expect(visibleLanes(lanes, new Set(["b"]))).toEqual([
      { lane: lanes[0], ordinal: 0 },
      { lane: lanes[2], ordinal: 2 },
    ]);
  });
});

describe("stageAxisMode", () => {
  it("maps the lens words onto the chart's modes, log-moneyness by default", () => {
    expect(stageAxisMode("k")).toBe("logmoneyness");
    expect(stageAxisMode("logmoneyness")).toBe("logmoneyness");
    expect(stageAxisMode("strike")).toBe("strike");
    expect(stageAxisMode("fixed")).toBe("strike");
    expect(stageAxisMode("K/F")).toBe("pctatm");
    expect(stageAxisMode("delta")).toBe("delta");
    expect(stageAxisMode("normalized")).toBe("normalized");
    expect(stageAxisMode("bogus")).toBe("logmoneyness");
    expect(stageAxisMode(null)).toBe("logmoneyness");
  });
});
