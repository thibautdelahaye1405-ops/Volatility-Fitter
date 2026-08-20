// Prior-persistence evidence helpers (V3.9 item 8).
import { describe, expect, it } from "vitest";
import {
  ageDaysFromTs,
  decayAt,
  decayCurve,
  formatAge,
  shapeInnovationSeries,
  sourceLabel,
} from "./priorEvidence";
import type { InnovationPoint } from "./priorEvidence";

describe("decayCurve / decayAt", () => {
  it("halves every H days: φ(0)=1, φ(H)=1/2, φ(2H)=1/4", () => {
    expect(decayAt(5, 0)).toBe(1);
    expect(decayAt(5, 5)).toBeCloseTo(0.5, 12);
    expect(decayAt(5, 10)).toBeCloseTo(0.25, 12);
    const pts = decayCurve(5, 20, 5); // dt = 0, 5, 10, 15, 20
    expect(pts.map((p) => p.dt)).toEqual([0, 5, 10, 15, 20]);
    expect(pts[0].phi).toBe(1);
    expect(pts[1].phi).toBeCloseTo(0.5, 12);
    expect(pts[4].phi).toBeCloseTo(1 / 16, 12);
  });

  it("null half-life is the random walk: φ ≡ 1 over the whole horizon", () => {
    expect(decayAt(null, 42)).toBe(1);
    const pts = decayCurve(null);
    expect(pts.every((p) => p.phi === 1)).toBe(true);
    expect(pts[pts.length - 1].dt).toBe(10); // the random-walk display horizon
  });

  it("default horizon shows four half-lives", () => {
    const pts = decayCurve(3);
    expect(pts[pts.length - 1].dt).toBe(12);
    expect(pts[pts.length - 1].phi).toBeCloseTo(1 / 16, 12);
  });
});

describe("age formatting", () => {
  it("formats days at/above one day, hours below, em-dash when unknown", () => {
    expect(formatAge(3)).toBe("3.0 d");
    expect(formatAge(1.25)).toBe("1.3 d");
    expect(formatAge(0.5)).toBe("12.0 h");
    expect(formatAge(null)).toBe("—");
    expect(formatAge(undefined)).toBe("—");
  });

  it("ages a UTC-naive backend stamp as UTC and clamps at zero", () => {
    const now = Date.parse("2026-06-10T20:00:00Z");
    expect(ageDaysFromTs("2026-06-07T20:00:00", now)).toBeCloseTo(3, 12);
    expect(ageDaysFromTs("2026-06-09T08:00:00Z", now)).toBeCloseTo(1.5, 12);
    expect(ageDaysFromTs("2026-06-12T00:00:00", now)).toBe(0); // future ⇒ 0
    expect(ageDaysFromTs(null, now)).toBeNull();
    expect(ageDaysFromTs("not-a-date", now)).toBeNull();
  });
});

describe("shapeInnovationSeries", () => {
  const points: InnovationPoint[] = [
    { day: "2026-06-09", expiry: "2026-12-18", innovationBp: -12.5 },
    { day: "2026-06-08", expiry: "2026-09-18", innovationBp: 4.0 },
    { day: "2026-06-09", expiry: "2026-09-18", innovationBp: 8.0 },
    { day: "2026-06-10", expiry: "2026-09-18", innovationBp: -30.0 },
  ];

  it("groups per expiry over the sorted day axis, |bp|, null gaps", () => {
    const shaped = shapeInnovationSeries(points);
    expect(shaped.days).toEqual(["2026-06-08", "2026-06-09", "2026-06-10"]);
    expect(shaped.series.map((s) => s.expiry)).toEqual(["2026-09-18", "2026-12-18"]);
    expect(shaped.series[0].values).toEqual([4.0, 8.0, 30.0]); // abs of −30
    expect(shaped.series[1].values).toEqual([null, 12.5, null]); // day gaps stay null
    expect(shaped.maxAbsBp).toBe(30.0);
  });

  it("is empty-safe", () => {
    const shaped = shapeInnovationSeries([]);
    expect(shaped.days).toEqual([]);
    expect(shaped.series).toEqual([]);
    expect(shaped.maxAbsBp).toBe(0);
  });
});

describe("sourceLabel", () => {
  it("maps the provenance tiers to short chips", () => {
    expect(sourceLabel("active_transported")).toBe("active");
    expect(sourceLabel("nearest_expiry_transported")).toBe("nearest");
    expect(sourceLabel("today_bootstrap")).toBe("bootstrap");
    expect(sourceLabel("saved")).toBe("saved");
    expect(sourceLabel(null)).toBe("none");
    expect(sourceLabel(undefined)).toBe("none");
  });
});
