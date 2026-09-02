// Nodes pane keyboard navigation (UI SHELL v2 wave 3, C1): one tab stop, a
// roving focused row driven by lib/treeNav — ↑/↓/←/→, Enter / Shift+Enter,
// type-ahead, L, Tab → filter box. The session / workbench / lit / quality
// hooks are mocked; the pure key algebra is locked in treeNav.test.ts.
// Also the per-node effective as-of column (NodeAsOfCell): exact rows plain,
// an inexact row amber with a "≠ as-of" pill on its ticker group.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NodesPane from "./NodesPane";
import { asOfAge, asOfClock, asOfTitle } from "./NodeAsOfCell";

const openNode = vi.fn();
const toggleNode = vi.fn();
const openDialog = vi.fn();

interface Rung {
  expiry: string;
  t: number;
  effectiveAsOf?: string | null;
  dataSource?: string | null;
  asOfExact?: boolean | null;
}
interface Universe {
  asOf: string;
  tickers: string[];
  expiries: Record<string, Rung[]>;
  defaultSource?: string;
  tickerSources?: Record<string, string>;
}

const baseUniverse: Universe = {
  asOf: "x",
  tickers: ["AAPL", "SPY"],
  expiries: {
    AAPL: [{ expiry: "2026-12-18", t: 0.31 }, { expiry: "2027-03-19", t: 0.56 }],
    SPY: [{ expiry: "2026-12-18", t: 0.31 }],
  },
};
// Swapped per test (read lazily at render time by the mocked hook).
let universeFixture: Universe = baseUniverse;

vi.mock("../../state/smileSession", () => ({
  useSmileSession: () => ({ source: "live", universe: universeFixture }),
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
afterEach(() => {
  cleanup();
  universeFixture = baseUniverse;
});

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

describe("NodesPane per-node effective as-of", () => {
  it("shows HH:MM (UTC) of the chain serving each node; exact rows stay plain, unfetched rows show —", () => {
    universeFixture = {
      ...baseUniverse,
      expiries: {
        AAPL: [{ expiry: "2026-12-18", t: 0.31, effectiveAsOf: "2026-06-10T14:30:00", dataSource: "yahoo", asOfExact: true }],
        SPY: [{ expiry: "2026-12-18", t: 0.31 }],
      },
    };
    render(<NodesPane />);
    const cell = screen.getByText("14:30");
    expect(cell.className).not.toContain("amber");
    expect(cell.getAttribute("title")).toContain("2026-06-10T14:30:00 UTC · yahoo");
    expect(screen.getByText("—").getAttribute("title")).toContain("press Fetch");
    expect(screen.queryByText("≠ as-of")).toBeNull();
  });

  it("flags an inexact node amber and pins a ≠ as-of pill on its ticker group only", () => {
    universeFixture = {
      ...baseUniverse,
      expiries: {
        AAPL: [{ expiry: "2026-12-18", t: 0.31, effectiveAsOf: "2026-06-10T14:30:00", dataSource: "yahoo", asOfExact: true }],
        SPY: [{ expiry: "2026-12-18", t: 0.31, effectiveAsOf: "2026-06-09T20:00:00", dataSource: "file", asOfExact: false }],
      },
    };
    render(<NodesPane />);
    const inexact = screen.getByText("20:00");
    expect(inexact.className).toContain("text-amber-400");
    expect(inexact.getAttribute("title")).toContain("≠ as-of");
    expect(screen.getByText("14:30").className).not.toContain("amber");
    expect(screen.getAllByText("≠ as-of")).toHaveLength(1);
    expect(document.getElementById("nodes-row-g_SPY")!.textContent).toContain("≠ as-of");
    expect(document.getElementById("nodes-row-g_AAPL")!.textContent).not.toContain("≠ as-of");
  });

  it("formats the clock, the age and the tooltip from a UTC-naive stamp", () => {
    expect(asOfClock("2026-06-10T14:30:00")).toBe("14:30");
    expect(asOfClock(null)).toBe("—");
    const now = Date.UTC(2026, 5, 10, 16, 30);
    expect(asOfAge("2026-06-10T16:26:00", now)).toBe("4m");
    expect(asOfAge("2026-06-10T03:00:00", now)).toBe("13.5h");
    expect(asOfAge("2026-06-07T11:42:00", now)).toBe("3.2d"); // 76.8 h
    expect(asOfAge("garbage", now)).toBe("");
    expect(asOfTitle({ effectiveAsOf: "2026-06-10T16:26:00", dataSource: "massive", asOfExact: true }, now))
      .toBe("effective as-of · 2026-06-10T16:26:00 UTC · massive · 4m");
    expect(asOfTitle({ effectiveAsOf: null, dataSource: null, asOfExact: null }, now)).toContain("press Fetch");
  });
});

describe("NodesPane per-ticker source pill", () => {
  it("badges a ticker pinned to another source than the universe's, and nothing otherwise", () => {
    universeFixture = {
      ...baseUniverse,
      defaultSource: "cboe",
      tickerSources: { AAPL: "bloomberg", SPY: "cboe" }, // SPY's pin IS the default: no pill
    };
    render(<NodesPane />);
    const pills = screen.getAllByTestId("ticker-source-pill");
    expect(pills).toHaveLength(1);
    expect(pills[0].textContent).toBe("BBG");
    expect(pills[0].getAttribute("title")).toBe("Pinned to Bloomberg");
    expect(document.getElementById("nodes-row-g_AAPL")!.textContent).toContain("BBG");
    expect(document.getElementById("nodes-row-g_SPY")!.textContent).not.toContain("CBOE");
  });

  it("shows no pill when nothing is pinned", () => {
    render(<NodesPane />);
    expect(screen.queryByTestId("ticker-source-pill")).toBeNull();
  });
});
