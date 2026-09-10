// Locks the Series frame LRU and the prefetch planner (roadmap §3.4).
import { describe, expect, it } from "vitest";
import { DEFAULT_CAPACITY, FrameCache, frameKey, planPrefetch } from "./seriesFrameCache";

describe("FrameCache", () => {
  it("keys are series|idx|lanes", () => {
    expect(frameKey("s1", 7, "a,b")).toBe("s1|7|a,b");
  });

  it("get / peek / has / set with the default capacity of 48", () => {
    const c = new FrameCache<number>();
    expect(c.capacity).toBe(DEFAULT_CAPACITY);
    c.set("a", 1);
    expect(c.has("a")).toBe(true);
    expect(c.get("a")).toBe(1);
    expect(c.peek("a")).toBe(1);
    expect(c.get("zz")).toBeUndefined();
    expect(c.size).toBe(1);
  });

  it("evicts the least recently USED entry; get bumps, peek does not", () => {
    const c = new FrameCache<number>(3);
    c.set("a", 1);
    c.set("b", 2);
    c.set("c", 3);
    c.get("a"); // a becomes the newest
    c.set("d", 4); // evicts b
    expect(c.has("b")).toBe(false);
    expect(c.has("a")).toBe(true);
    c.peek("c"); // no bump
    c.set("e", 5); // evicts c (the oldest untouched)
    expect(c.has("c")).toBe(false);
    expect([...["a", "d", "e"]].every((k) => c.has(k))).toBe(true);
  });

  it("re-setting a key replaces the value and refreshes it; clear empties", () => {
    const c = new FrameCache<number>(2);
    c.set("a", 1);
    c.set("b", 2);
    c.set("a", 10);
    c.set("c", 3); // evicts b, not a
    expect(c.peek("a")).toBe(10);
    expect(c.has("b")).toBe(false);
    c.clear();
    expect(c.size).toBe(0);
  });
});

describe("planPrefetch", () => {
  const keyOf = (i: number) => `s|${i}|x`;

  it("takes the first uncached, not-in-flight indices up to the free slots", () => {
    const c = new FrameCache<number>();
    c.set(keyOf(6), 1);
    const inFlight = new Set<string>([keyOf(7)]);
    expect(planPrefetch(c, keyOf, [6, 7, 8, 9, 10], inFlight, 2)).toEqual([8]);
    expect(planPrefetch(c, keyOf, [6, 7, 8, 9, 10], new Set(), 2)).toEqual([7, 8]);
  });

  it("plans nothing when the pipe is full or everything is known", () => {
    const c = new FrameCache<number>();
    expect(planPrefetch(c, keyOf, [1, 2, 3], new Set([keyOf(9), keyOf(8)]), 2)).toEqual([]);
    c.set(keyOf(1), 1);
    c.set(keyOf(2), 2);
    expect(planPrefetch(c, keyOf, [1, 2], new Set(), 2)).toEqual([]);
  });

  it("never plans the same index twice", () => {
    const c = new FrameCache<number>();
    expect(planPrefetch(c, keyOf, [4, 4, 5], new Set(), 3)).toEqual([4, 5]);
  });
});
