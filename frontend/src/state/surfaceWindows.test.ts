// state/surfaceWindows: meshes under one key crop and rescale together; keys
// are independent; a keyless mesh keeps a local copy; the shared set falls
// back to the defaults until written.
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_WINDOWS, resetSurfaceWindows, useSurfaceWindows } from "./surfaceWindows";

beforeEach(resetSurfaceWindows);

describe("useSurfaceWindows", () => {
  it("shares the windows and the time mode between hooks on the same key", () => {
    const a = renderHook(() => useSurfaceWindows("localvol:compare"));
    const b = renderHook(() => useSurfaceWindows("localvol:compare"));
    expect(a.result.current[0]).toEqual(DEFAULT_WINDOWS);
    act(() => a.result.current[1]({ t: { range: [0.5, 1], key: "t" } }));
    expect(b.result.current[0].t).toEqual({ range: [0.5, 1], key: "t" });
    act(() => b.result.current[1]({ timeMode: "linear" }));
    expect(a.result.current[0].timeMode).toBe("linear");
    expect(a.result.current[0].t).toEqual({ range: [0.5, 1], key: "t" }); // a patch keeps the rest
  });

  it("keeps keys apart and a keyless hook local", () => {
    const shared = renderHook(() => useSurfaceWindows("parametric:surface"));
    const other = renderHook(() => useSurfaceWindows("localvol:lv"));
    const local = renderHook(() => useSurfaceWindows(undefined));
    act(() => shared.result.current[1]({ k: { range: [-0.2, 0.2], key: "k" } }));
    expect(other.result.current[0].k).toBeNull();
    expect(local.result.current[0].k).toBeNull();
    act(() => local.result.current[1]({ k: { range: [-1, 1], key: "k" } }));
    expect(local.result.current[0].k).toEqual({ range: [-1, 1], key: "k" });
    expect(shared.result.current[0].k).toEqual({ range: [-0.2, 0.2], key: "k" });
  });
});
