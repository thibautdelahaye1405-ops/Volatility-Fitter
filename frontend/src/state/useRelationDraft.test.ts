// The relation draft (GRAPH ERGONOMICS ARC, E2): rows on screen resolve
// draft → active → auto; every edit is an undo step and stages the draft
// through a debounced PUT; flip applies the one-factor identities; reset
// stages an empty draft and re-reads the auto relations.
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MessageEdgeRow } from "./useMessageEdges";

const apiGet = vi.fn();
const apiPut = vi.fn();
vi.mock("./api", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    put: (...args: unknown[]) => apiPut(...args),
  },
}));

import { DRAFT_PUT_DEBOUNCE_MS, useRelationDraft } from "./useRelationDraft";

const ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-10-16",
  targetTicker: "SPY", targetExpiry: "2026-07-17",
  messagePrecision: 1700, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "explicit", relationSemantics: null,
};
const AUTO: MessageEdgeRow = { ...ROW, betaAtmVol: 1.5, betaSkew: 1.5, betaCurv: 1.5, precisionRule: "calendar_distance" };
const KEY = "SPY|2026-10-16>SPY|2026-07-17";

function mockSlots(draft: MessageEdgeRow[] | null, active: MessageEdgeRow[] | null) {
  apiGet.mockImplementation((path: string) => {
    if (path === "/graph/config/messages")
      return Promise.resolve({
        draft: draft === null ? null : { name: "d", version: 2, rows: draft },
        active: active === null ? null : { name: "d", version: 1, rows: active },
      });
    if (path === "/graph/edges/messages/auto") return Promise.resolve({ edges: [AUTO] });
    return Promise.reject(new Error(`unexpected ${path}`));
  });
  apiPut.mockImplementation((_path: string, opts: { body: { edges: MessageEdgeRow[] } }) =>
    Promise.resolve({ edges: opts.body.edges }),
  );
}

beforeEach(() => {
  apiGet.mockReset();
  apiPut.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("useRelationDraft", () => {
  it("resolves the rows on screen draft → active → auto", async () => {
    mockSlots([ROW], [AUTO]);
    const { result } = renderHook(() => useRelationDraft({ enabled: true }));
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.source).toBe("draft");
    expect(result.current.rows[0]?.betaAtmVol).toBe(2);

    mockSlots([], [AUTO]);
    const r2 = renderHook(() => useRelationDraft({ enabled: true }));
    await waitFor(() => expect(r2.result.current.source).toBe("active"));

    mockSlots(null, null);
    const r3 = renderHook(() => useRelationDraft({ enabled: true }));
    await waitFor(() => expect(r3.result.current.rows).toHaveLength(1));
    expect(r3.result.current.source).toBe("auto");
    expect(r3.result.current.rows[0]?.precisionRule).toBe("calendar_distance");
  });

  it("stays idle when disabled (smooth field)", () => {
    mockSlots([ROW], null);
    const { result } = renderHook(() => useRelationDraft({ enabled: false }));
    expect(result.current.rows).toEqual([]);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("an edit lands at once, undoes / redoes, and stages the draft after the debounce", async () => {
    mockSlots([ROW], [ROW]);
    const onPersisted = vi.fn();
    const { result } = renderHook(() => useRelationDraft({ enabled: true, onPersisted }));
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    vi.useFakeTimers();

    act(() => result.current.update(KEY, { betaAtmVol: 1.25 }));
    expect(result.current.rows[0]?.betaAtmVol).toBe(1.25);
    expect(result.current.saving).toBe(true);
    expect(result.current.canUndo).toBe(true);
    expect(apiPut).not.toHaveBeenCalled(); // debounced

    act(() => result.current.undo());
    expect(result.current.rows[0]?.betaAtmVol).toBe(2);
    expect(result.current.canRedo).toBe(true);
    act(() => result.current.redo());
    expect(result.current.rows[0]?.betaAtmVol).toBe(1.25);

    await act(async () => {
      vi.advanceTimersByTime(DRAFT_PUT_DEBOUNCE_MS + 10);
      await Promise.resolve();
    });
    // Latest wins: ONE PUT with the final rows.
    expect(apiPut).toHaveBeenCalledTimes(1);
    const body = apiPut.mock.calls[0]?.[1] as { body: { edges: MessageEdgeRow[] } };
    expect(body.body.edges[0]?.betaAtmVol).toBe(1.25);
    vi.useRealTimers();
    await waitFor(() => expect(onPersisted).toHaveBeenCalled());
    expect(result.current.saving).toBe(false);
    expect(result.current.source).toBe("draft");
  });

  it("add replaces a same-key row, remove drops it, flip applies 1/β and p·β²", async () => {
    mockSlots([ROW], [ROW]);
    const { result } = renderHook(() => useRelationDraft({ enabled: true }));
    await waitFor(() => expect(result.current.rows).toHaveLength(1));

    act(() => result.current.add({ ...ROW, betaAtmVol: 3 }));
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.byKey(KEY)?.betaAtmVol).toBe(3);

    let nk: string | null = null;
    act(() => {
      nk = result.current.flip(KEY);
    });
    expect(nk).toBe("SPY|2026-07-17>SPY|2026-10-16");
    const flipped = result.current.byKey("SPY|2026-07-17>SPY|2026-10-16");
    expect(flipped?.betaAtmVol).toBeCloseTo(1 / 3, 12);
    expect(flipped?.messagePrecision).toBeCloseTo(1700 * 9, 6);

    act(() => result.current.remove("SPY|2026-07-17>SPY|2026-10-16"));
    expect(result.current.rows).toHaveLength(0);
  });

  it("resetAuto stages an empty draft and re-reads the auto relations", async () => {
    mockSlots([ROW], [ROW]);
    const { result } = renderHook(() => useRelationDraft({ enabled: true }));
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      await result.current.resetAuto();
    });
    expect(apiPut).toHaveBeenCalledWith("/graph/edges/messages", { body: { edges: [] } });
    expect(result.current.source).toBe("auto");
    expect(result.current.rows[0]?.precisionRule).toBe("calendar_distance");
    expect(result.current.canUndo).toBe(true);
  });
});
