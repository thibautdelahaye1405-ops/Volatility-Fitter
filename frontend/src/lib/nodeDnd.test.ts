// Node drag-and-drop routing (UI SHELL v2 wave 3, C5).
import { describe, expect, it } from "vitest";
import { DEFAULT_PULSE, NODE_MIME, decodeNodeDrag, encodeNodeDrag, isNodeDrag, routeNodeDrop } from "./nodeDnd";

const node = { ticker: "SPY", expiry: "2026-12-18" };

describe("payload", () => {
  it("round-trips through the dataTransfer string and rejects junk", () => {
    expect(decodeNodeDrag(encodeNodeDrag(node))).toEqual(node);
    expect(decodeNodeDrag("")).toBeNull();
    expect(decodeNodeDrag(null)).toBeNull();
    expect(decodeNodeDrag("{not json")).toBeNull();
    expect(decodeNodeDrag(JSON.stringify({ ticker: "", expiry: "x" }))).toBeNull();
    expect(decodeNodeDrag(JSON.stringify({ ticker: "SPY" }))).toBeNull();
  });

  it("gates dragover on the node MIME type", () => {
    expect(isNodeDrag([NODE_MIME, "text/plain"])).toBe(true);
    expect(isNodeDrag(["Files"])).toBe(false);
    expect(isNodeDrag(undefined)).toBe(false);
  });
});

describe("routeNodeDrop", () => {
  it("canvas: lights the designation in calibrations mode, pulses in manual what-if", () => {
    expect(routeNodeDrop("canvas", node, { manual: false })).toEqual({ type: "light", ...node, key: "SPY|2026-12-18" });
    expect(routeNodeDrop("canvas", node, { manual: true })).toEqual({ type: "pulse", ...node, key: "SPY|2026-12-18", dAtmVol: DEFAULT_PULSE });
    expect(DEFAULT_PULSE).toBe(0.01);
  });

  it("tab strip: opens a pinned tab; split zones: open in the next group (row) / a new lower group (column)", () => {
    expect(routeNodeDrop("tabstrip", node, { manual: true })).toEqual({ type: "openTab", ...node, pinned: true });
    expect(routeNodeDrop("split", node, { manual: false })).toEqual({ type: "openSplit", ...node, direction: "row" });
    expect(routeNodeDrop("splitDown", node, { manual: false })).toEqual({ type: "openSplit", ...node, direction: "column" });
  });
});
