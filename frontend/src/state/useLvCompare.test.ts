// useLvCompare: the Compare tab's fetch hook under the two kinds of change.
// HARD (chip / ticker) aborts and refetches with the sheets dimmed; SOFT (the
// session's view version, bumped on every live spot tick) never aborts a
// build in flight, coalesces into one trailing refetch after it lands, waits
// out the throttle, lands silently and keeps the same object for an identical
// payload — the 2026-09-08 live finding (a streaming feed starved the twin).
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { lvCompareFixture } from "../lib/lvCompare.fixture";

const apiPost = vi.fn();
vi.mock("./api", () => ({
  api: { post: (...args: unknown[]) => apiPost(...args) },
  ApiError: class ApiError extends Error {
    constructor(public status: number, public statusText: string, public body: string) {
      super(`API ${status}`);
    }
  },
}));

import { SOFT_REFRESH_MIN_MS, useLvCompare } from "./useLvCompare";
import type { LvCompareResponse, LvTInterp } from "./useLvCompare";

interface Call { resolve: (v: LvCompareResponse) => void; reject: (e: unknown) => void; signal: AbortSignal; body: unknown }
let calls: Call[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  calls = [];
  apiPost.mockReset();
  apiPost.mockImplementation((_path: string, opts: { signal: AbortSignal; body: unknown }) =>
    new Promise<LvCompareResponse>((resolve, reject) => {
      calls.push({ resolve, reject, signal: opts.signal, body: opts.body });
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
});

const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
const land = async (i: number, payload = lvCompareFixture()) => {
  await act(async () => { calls[i].resolve(payload); await Promise.resolve(); await Promise.resolve(); });
};

function mount(reloadKey = 0, tInterp: LvTInterp = "smooth") {
  return renderHook(
    (p: { reloadKey: number; tInterp: LvTInterp }) => useLvCompare("ALPHA", true, p.reloadKey, "mid", p.tInterp),
    { initialProps: { reloadKey, tInterp } },
  );
}

describe("useLvCompare", () => {
  it("first load: loading until the build lands, with the chip in the body", async () => {
    const h = mount();
    expect(h.result.current.loading).toBe(true);
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(calls[0].body).toEqual({ fitMode: "mid", tInterp: "smooth", tails: "model" });
    await land(0);
    expect(h.result.current.loading).toBe(false);
    expect(h.result.current.data?.ticker).toBe("ALPHA");
  });

  it("a view-version bump never aborts the build in flight; the bumps coalesce into one trailing silent refetch", async () => {
    const h = mount();
    h.rerender({ reloadKey: 1, tInterp: "smooth" });
    h.rerender({ reloadKey: 2, tInterp: "smooth" });
    h.rerender({ reloadKey: 3, tInterp: "smooth" });
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(calls[0].signal.aborted).toBe(false);
    await land(0);
    expect(h.result.current.data).not.toBeNull();
    // The trailing refetch waits out the throttle, then runs SILENTLY.
    expect(apiPost).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(SOFT_REFRESH_MIN_MS); });
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(h.result.current.updating).toBe(true);
    expect(h.result.current.refreshing).toBe(false);
    expect(h.result.current.loading).toBe(false);
    await land(1);
    expect(h.result.current.updating).toBe(false);
    // No further bump queued: nothing else fires.
    await act(async () => { vi.advanceTimersByTime(10 * SOFT_REFRESH_MIN_MS); });
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it("an identical payload keeps the same object (no repaint); a changed one replaces it", async () => {
    const h = mount();
    await land(0);
    const first = h.result.current.data;
    h.rerender({ reloadKey: 1, tInterp: "smooth" });
    await act(async () => { vi.advanceTimersByTime(SOFT_REFRESH_MIN_MS); });
    await land(1);
    expect(h.result.current.data).toBe(first);
    h.rerender({ reloadKey: 2, tInterp: "smooth" });
    await act(async () => { vi.advanceTimersByTime(SOFT_REFRESH_MIN_MS); });
    await land(2, lvCompareFixture({ roundTripBp: 99 }));
    expect(h.result.current.data).not.toBe(first);
    expect(h.result.current.data?.roundTripBp).toBe(99);
  });

  it("a chip change aborts the build in flight and refetches at once, dimming the sheets on screen", async () => {
    const h = mount();
    await land(0);
    h.rerender({ reloadKey: 0, tInterp: "buckets" });
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(calls[1].body).toEqual({ fitMode: "mid", tInterp: "buckets", tails: "model" });
    expect(h.result.current.refreshing).toBe(true);
    expect(h.result.current.data?.tInterp).toBe("smooth"); // the previous twin stays up, dimmed
    // Another chip change while that build runs: the stale one is aborted.
    h.rerender({ reloadKey: 0, tInterp: "smooth" });
    expect(calls[1].signal.aborted).toBe(true);
    expect(apiPost).toHaveBeenCalledTimes(3);
    await land(2);
    expect(h.result.current.refreshing).toBe(false);
  });

  it("a failed silent refresh keeps the sheets; a failed hard fetch surfaces the error", async () => {
    const h = mount();
    await land(0);
    h.rerender({ reloadKey: 1, tInterp: "smooth" });
    await act(async () => { vi.advanceTimersByTime(SOFT_REFRESH_MIN_MS); });
    await act(async () => { calls[1].reject(new Error("boom")); await Promise.resolve(); await Promise.resolve(); });
    expect(h.result.current.data).not.toBeNull();
    expect(h.result.current.error).toBeNull();
    h.rerender({ reloadKey: 1, tInterp: "buckets" });
    await act(async () => { calls[2].reject(new Error("no fit")); await Promise.resolve(); await Promise.resolve(); });
    expect(h.result.current.data).toBeNull();
    expect(h.result.current.error).toBe("no fit");
  });

  it("does nothing while disabled, and unmounting aborts the build", async () => {
    const off = renderHook(() => useLvCompare("ALPHA", false, 0));
    expect(apiPost).not.toHaveBeenCalled();
    off.unmount();
    const h = mount();
    expect(apiPost).toHaveBeenCalledTimes(1);
    h.unmount();
    expect(calls[0].signal.aborted).toBe(true);
    await flush();
  });
});
