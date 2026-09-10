// Locks the filmstrip's pure scale helpers (roadmap §3.4).
import { describe, expect, it } from "vitest";
import { fracOf, nearestIndex, sparkPath, valueAt, xOf, yOf, yScale } from "./filmstrip";

describe("x axis (frame-index-linear)", () => {
  it("spreads n frames over the width, a single frame in the middle", () => {
    expect(xOf(0, 5, 100)).toBe(0);
    expect(xOf(4, 5, 100)).toBe(100);
    expect(xOf(2, 5, 100)).toBe(50);
    expect(xOf(0, 1, 100)).toBe(50);
    expect(fracOf(9, 5)).toBe(1);
  });
  it("nearestIndex inverts xOf and clamps", () => {
    for (let i = 0; i < 7; i++) expect(nearestIndex(xOf(i, 7, 300), 7, 300)).toBe(i);
    expect(nearestIndex(-40, 7, 300)).toBe(0);
    expect(nearestIndex(900, 7, 300)).toBe(6);
    expect(nearestIndex(30, 1, 300)).toBe(0);
    expect(nearestIndex(30, 7, 0)).toBe(0);
  });
});

describe("y scale", () => {
  it("pads the finite extent and ignores nulls / NaN", () => {
    const s = yScale([1, null, 3, NaN, 2], 0.1);
    expect(s.lo).toBeCloseTo(0.8);
    expect(s.hi).toBeCloseTo(3.2);
  });
  it("a flat row gets a band around its level; no values give the unit interval", () => {
    const flat = yScale([2, 2, 2]);
    expect(flat.lo).toBeCloseTo(1.9);
    expect(flat.hi).toBeCloseTo(2.1);
    expect(yScale([0, 0])).toEqual({ lo: -0.5, hi: 0.5 });
    expect(yScale([null, null])).toEqual({ lo: 0, hi: 1 });
  });
  it("yOf puts lo at the bottom and hi at the top", () => {
    const s = { lo: 0, hi: 10 };
    expect(yOf(0, s, 20)).toBe(20);
    expect(yOf(10, s, 20)).toBe(0);
    expect(yOf(5, s, 20)).toBe(10);
    expect(yOf(3, { lo: 1, hi: 1 }, 20)).toBe(10);
  });
});

describe("sparkPath", () => {
  it("draws one run per stretch of finite values (no bridging across nulls)", () => {
    const d = sparkPath([0, 10, null, 5, 5], { lo: 0, hi: 10 }, 100, 20);
    expect(d).toBe("M0.0,20.0L25.0,0.0M75.0,10.0L100.0,10.0");
  });
  it("is empty without values", () => {
    expect(sparkPath([], { lo: 0, hi: 1 }, 100, 20)).toBe("");
    expect(sparkPath([null, undefined], { lo: 0, hi: 1 }, 100, 20)).toBe("");
  });
  it("valueAt reads a finite value, null otherwise", () => {
    expect(valueAt([1, null, NaN], 0)).toBe(1);
    expect(valueAt([1, null, NaN], 1)).toBeNull();
    expect(valueAt([1, null, NaN], 2)).toBeNull();
    expect(valueAt(undefined, 0)).toBeNull();
  });
});
