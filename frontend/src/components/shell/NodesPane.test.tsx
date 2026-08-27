// Nodes pane keyboard navigation (UI SHELL v2 wave 3, C1): one tab stop, a
// roving focused row driven by lib/treeNav — ↑/↓/←/→, Enter / Shift+Enter,
// type-ahead, L, Tab → filter box. The session / workbench / lit / quality
// hooks are mocked; the pure key algebra is locked in treeNav.test.ts.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NodesPane from "./NodesPane";

const openNode = vi.fn();
const toggleNode = vi.fn();
const openDialog = vi.fn();

vi.mock("../../state/smileSession", () => ({
  useSmileSession: () => ({
    source: "live",
    universe: {
      asOf: "x",
      tickers: ["AAPL", "SPY"],
      expiries: {
        AAPL: [{ expiry: "2026-12-18", t: 0.31 }, { expiry: "2027-03-19", t: 0.56 }],
        SPY: [{ expiry: "2026-12-18", t: 0.31 }],
      },
    },
  }),
}));
vi.mock("../../state/workbench", () => ({
  useWorkbench: () => ({
    tabs: [], activeTab: null, layout: { nodesWidth: 260 }, nodesFocusSeq: 0, openNode, openDialog,
  }),
}));
vi.mock("../../state/litMap", () => ({
  useLitMap: () => ({
    nodes: [{ ticker: "AAPL", expiry: "2026-12-18", lit: true }],
    litOf: () => true,
    toggleNode,
    setTicker: vi.fn(),
  }),
}));
vi.mock("../../state/qualityContext", () => ({ useQualityReport: () => ({ nodeOf: () => undefined }) }));
vi.mock("../../state/expiryFormat", () => ({ useExpiryFormat: () => ({ format: "dmy" }) }));

const tree = () => screen.getByRole("tree");
const focusedId = () => tree().getAttribute("aria-activedescendant");
const key = (k: string, mods: Record<string, boolean> = {}) => fireEvent.keyDown(tree(), { key: k, ...mods });

beforeEach(() => {
  openNode.mockClear();
  toggleNode.mockClear();
});
afterEach(cleanup);

describe("NodesPane keyboard navigation", () => {
  it("is one tab stop whose focus row defaults to the first group and moves with the arrows", () => {
    render(<NodesPane />);
    expect(tree().getAttribute("tabindex")).toBe("0");
    expect(focusedId()).toBe("nodes-row-g_AAPL");
    key("ArrowDown");
    expect(focusedId()).toBe("nodes-row-AAPL_2026_12_18");
    key("End");
    expect(focusedId()).toBe("nodes-row-SPY_2026_12_18");
    key("ArrowLeft");
    expect(focusedId()).toBe("nodes-row-g_SPY");
  });

  it("← collapses a group (its rows leave the tree) and → expands it again", () => {
    render(<NodesPane />);
    expect(screen.getAllByRole("treeitem")).toHaveLength(5);
    key("ArrowLeft"); // AAPL group focused → collapse
    expect(screen.getAllByRole("treeitem")).toHaveLength(3);
    key("ArrowRight");
    expect(screen.getAllByRole("treeitem")).toHaveLength(5);
    key("ArrowRight"); // enters the group
    expect(focusedId()).toBe("nodes-row-AAPL_2026_12_18");
  });

  it("Enter previews, Shift+Enter pins, L toggles lit/dark, Tab focuses the filter", () => {
    render(<NodesPane />);
    key("ArrowDown");
    key("Enter");
    expect(openNode).toHaveBeenLastCalledWith({ ticker: "AAPL", expiry: "2026-12-18" }, { preview: true });
    key("Enter", { shiftKey: true });
    expect(openNode).toHaveBeenLastCalledWith({ ticker: "AAPL", expiry: "2026-12-18" }, { preview: false });
    key("l");
    expect(toggleNode).toHaveBeenCalledWith("AAPL", "2026-12-18");
    key("Tab");
    expect(document.activeElement).toBe(screen.getByLabelText("Filter nodes"));
  });

  it("type-ahead jumps to the next ticker starting with the letters (chained within the window)", () => {
    const now = vi.spyOn(Date, "now");
    render(<NodesPane />);
    now.mockReturnValue(1_000);
    key("s");
    expect(focusedId()).toBe("nodes-row-g_SPY");
    now.mockReturnValue(1_100); // "sa" — still a prefix search, no such ticker
    key("a");
    expect(focusedId()).toBe("nodes-row-g_SPY");
    now.mockReturnValue(10_000); // window elapsed → fresh "a"
    key("a");
    expect(focusedId()).toBe("nodes-row-g_AAPL");
    now.mockRestore();
  });

  it("outlines the focused row only while the tree has focus", () => {
    render(<NodesPane />);
    const row = document.getElementById("nodes-row-g_AAPL")!.firstElementChild as HTMLElement;
    expect(row.className).not.toContain("ring-1");
    fireEvent.focus(tree());
    expect(row.className).toContain("ring-1");
    fireEvent.blur(tree());
    expect(row.className).not.toContain("ring-1");
  });
});
