// Series lens shell locks (SERIES ARC S4 + S5): the live-only empty state,
// the "no series yet" state with its New series… entry, the picker listing
// the ticker's series (newest first, "name · mode · n frames"), the stage
// composition once a document is in, and the five stage tabs (Surface ·
// Term · Lanes lit in S5, the Surface stage's Sheets | Difference toggle).
// The data hooks (state/useSeries) and the playback / frame / strip /
// evidence / filter pieces are stubbed so the shell renders on its own; no
// WorkbenchProvider is mounted (view memory falls back to local state, the
// node scope is the mocked session).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SeriesViewer from "./SeriesViewer";
import type { SeriesDoc, SeriesSummary } from "../lib/seriesTypes";

let source: "live" | "mock" = "live";
// The scoped session the lens reads (ticker · expiry · source · fit mode);
// the rest of the module stays real for the node-scope / workbench imports.
vi.mock("../state/smileSession", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/smileSession")>()),
  useSmileSession: () => ({ ticker: "SPY", expiry: "2026-12-18", source, fitMode: "mid", universe: null }),
}));

interface ListState {
  series: SeriesSummary[]; loading: boolean; loaded: boolean; error: string | null; refresh: () => void;
}
const emptyList = (): ListState => ({ series: [], loading: false, loaded: true, error: null, refresh: vi.fn() });
let listState: ListState = emptyList();
let docState: { doc: SeriesDoc | null; loading: boolean; error: string | null; refresh: () => void } =
  { doc: null, loading: false, error: null, refresh: vi.fn() };
vi.mock("../state/useSeries", () => ({
  useSeriesList: () => listState,
  useSeriesDoc: () => docState,
  useSeriesStatus: () => null,
  isSeriesActive: () => false,
  seriesErrorMessage: (e: unknown) => String(e),
  fetchPresets: vi.fn(() => Promise.resolve([])),
  estimateSeries: vi.fn(), createSeries: vi.fn(), importSeries: vi.fn(), startSeries: vi.fn(),
  resumeSeries: vi.fn(), pauseSeries: vi.fn(), cancelSeries: vi.fn(), deleteSeries: vi.fn(),
}));

// Agent B's pieces: trivial stubs (their own tests lock them).
const update = vi.fn();
vi.mock("../state/useSeriesPlayback", () => ({
  useSeriesPlayback: () => ({ playback: { index: 0, playing: false, speed: 1, loop: false }, update, act: vi.fn() }),
}));
vi.mock("../state/useSeriesFrames", () => ({
  useSeriesFrames: () => ({ frame: null, loading: false, peek: () => null }),
}));
vi.mock("../state/useSeriesStrip", () => ({ useSeriesStrip: () => ({ strip: null }) }));
vi.mock("../state/useSeriesEvidence", () => ({ useSeriesEvidence: () => ({ evidence: null }) }));
vi.mock("../state/useSeriesLaneFilter", () => ({
  useSeriesLaneFilterIndexes: () => ({ index: {}, loaded: true }),
  useSeriesLaneFilterIndex: () => ({ expiries: [] }),
  useSeriesLaneFilter: () => ({ steps: [], frameIdx: [] }),
}));
vi.mock("../lib/seriesPlayback", () => ({ keyAction: () => null }));
vi.mock("../lib/seriesLanes", () => ({ laneStyle: () => ({ colour: "#7dd3fc", dash: "" }) }));
vi.mock("../components/series/TransportBar", () => ({ default: () => <div data-testid="transport" /> }));
vi.mock("../components/series/Filmstrip", () => ({ default: () => <div data-testid="filmstrip" /> }));
vi.mock("../components/series/SmileStage", () => ({ default: () => <div data-testid="smile-stage" /> }));
// The S5 stages (agent C's Surface / Term, the Lanes evidence): stubs that
// echo the props the switch hands them.
vi.mock("../components/series/SurfaceStage", () => ({
  default: (p: { mode: string; ticker: string; seriesId: string }) => (
    <div data-testid="surface-stage" data-mode={p.mode} data-ticker={p.ticker} data-series={p.seriesId} />
  ),
}));
vi.mock("../components/series/TermStage", () => ({
  default: (p: { expiry: string | null }) => <div data-testid="term-stage" data-expiry={p.expiry ?? ""} />,
}));
vi.mock("../components/series/LanesStage", () => ({
  default: (p: { seriesId: string; epoch: string; index: number }) => (
    <div data-testid="lanes-stage" data-series={p.seriesId} data-epoch={p.epoch} data-index={p.index} />
  ),
}));

function summary(over: Partial<SeriesSummary> = {}): SeriesSummary {
  return {
    id: "s1", name: "SPY 15 min ×20", ticker: "SPY", source: "massive", mode: "historical", status: "done",
    createdTs: "2026-09-10T14:00:00", nFrames: 20, nFramesReady: 20, nLanes: 2, ...over,
  };
}

function doc(): SeriesDoc {
  const lane = (id: string, production: boolean) => ({
    id, name: id, family: "lqd" as const, colour: null, fitMode: null, patchFit: {}, patchOptions: {}, production, seed: "cold" as const,
  });
  return {
    id: "s1", createdTs: "2026-09-10T14:00:00", updatedTs: "2026-09-10T14:10:00",
    spec: {
      name: "SPY 15 min ×20", ticker: "SPY", mode: "historical",
      clock: { step: "15m", count: 2, sessionOnly: true, timeOfDay: "15:45", tz: "America/New_York", warmupFrames: 0 },
      ladder: { policy: "pinned", expiries: ["2026-12-18"] }, fitMode: "mid", lanes: [lane("lqd_free", true), lane("lqd_prior", false)], note: "",
    },
    baseFit: {}, baseOptions: {},
    progress: { status: "done", framesTotal: 2, framesReady: 2, fitsTotal: 4, fitsDone: 4, current: null, error: null, startedTs: null, updatedTs: null },
    frames: [
      { idx: 0, ts: "2026-09-10T13:45:00", snapshotId: 1, spot: 500.1, quoteKind: "quotes", nQuotes: 120, expiries: ["2026-12-18"], warmup: false, status: "ready", error: null, harvestedTs: null },
      { idx: 1, ts: "2026-09-10T14:00:00", snapshotId: 2, spot: 501.4, quoteKind: "quotes", nQuotes: 118, expiries: ["2026-12-18"], warmup: false, status: "ready", error: null, harvestedTs: null },
    ],
  };
}

afterEach(() => {
  cleanup();
  source = "live";
  listState = emptyList();
  docState = { doc: null, loading: false, error: null, refresh: vi.fn() };
  update.mockReset();
});

describe("SeriesViewer", () => {
  it("asks for the live server with a store when the session is mock", () => {
    source = "mock";
    render(<SeriesViewer />);
    expect(screen.getByText(/live server with a store/)).toBeTruthy();
    expect(screen.queryByLabelText("Series")).toBeNull();
  });

  it("renders the no-series state with the New series entry", () => {
    render(<SeriesViewer />);
    expect(screen.getByText(/No series for SPY yet/)).toBeTruthy();
    expect(screen.getAllByText("New series…").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("transport")).toBeNull();
  });

  it("names the missing store when the backend answers 409", () => {
    listState = { ...emptyList(), error: "series need a store: start the app with VOLFIT_DB set" };
    render(<SeriesViewer />);
    expect(screen.getByText(/live server with a store/)).toBeTruthy();
  });

  it("lists the ticker's series in the picker and composes the stage once the document is in", () => {
    listState = { ...emptyList(), series: [summary(), summary({ id: "s0", name: "SPY daily ×5", mode: "import", nFrames: 5 })] };
    docState = { doc: doc(), loading: false, error: null, refresh: vi.fn() };
    render(<SeriesViewer />);
    const picker = screen.getByLabelText("Series") as HTMLSelectElement;
    expect(picker.options[0].textContent).toBe("SPY 15 min ×20 · historical · 20 frames");
    expect(picker.options[1].textContent).toBe("SPY daily ×5 · import · 5 frames");
    // The newest is selected: its document composes the stage.
    expect(screen.getByTestId("smile-stage")).toBeTruthy();
    expect(screen.getByTestId("filmstrip")).toBeTruthy();
    expect(screen.getByTestId("transport")).toBeTruthy();
    // Lane chips: the production lane is starred, the other is not.
    expect(screen.getByText("lqd_free").textContent).toContain("★");
    expect(screen.getByText("lqd_prior").textContent).not.toContain("★");
    expect(screen.getByTestId("series-status").textContent).toContain("frames 2/2");
  });

  it("switches to the Frames stage and jumps on a row click", () => {
    listState = { ...emptyList(), series: [summary()] };
    docState = { doc: doc(), loading: false, error: null, refresh: vi.fn() };
    render(<SeriesViewer />);
    fireEvent.click(screen.getByRole("tab", { name: "Frames" }));
    expect(screen.getByTestId("frames-table")).toBeTruthy();
    fireEvent.click(screen.getByText("501.40"));
    expect(update).toHaveBeenCalledWith({ index: 1 });
  });

  it("lights the Surface · Term · Lanes tabs and switches the stage on each (S5)", () => {
    listState = { ...emptyList(), series: [summary()] };
    docState = { doc: doc(), loading: false, error: null, refresh: vi.fn() };
    render(<SeriesViewer />);
    for (const name of ["Surface", "Term", "Lanes"]) {
      const tab = screen.getByRole("tab", { name }) as HTMLButtonElement;
      expect(tab.disabled).toBe(false);
      expect(tab.getAttribute("title")).toBeNull();
    }
    // Surface: the stage mounts with the Sheets | Difference toggle in the control row.
    fireEvent.click(screen.getByRole("tab", { name: "Surface" }));
    const surface = screen.getByTestId("surface-stage");
    expect(surface.getAttribute("data-mode")).toBe("sheets");
    expect(surface.getAttribute("data-ticker")).toBe("SPY");
    expect(surface.getAttribute("data-series")).toBe("s1");
    expect(screen.getByRole("tab", { name: "Surface" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Difference" }));
    expect(screen.getByTestId("surface-stage").getAttribute("data-mode")).toBe("difference");
    expect(screen.getByRole("button", { name: "Difference" }).getAttribute("aria-pressed")).toBe("true");
    // Term: the toggle leaves with the Surface stage; the stage gets the shown expiry.
    fireEvent.click(screen.getByRole("tab", { name: "Term" }));
    expect(screen.getByTestId("term-stage").getAttribute("data-expiry")).toBe("2026-12-18");
    expect(screen.queryByRole("button", { name: "Difference" })).toBeNull();
    // Lanes: the evidence stage gets the series id, the playhead and the caches' epoch.
    fireEvent.click(screen.getByRole("tab", { name: "Lanes" }));
    const lanes = screen.getByTestId("lanes-stage");
    expect(lanes.getAttribute("data-series")).toBe("s1");
    expect(lanes.getAttribute("data-index")).toBe("0");
    expect(lanes.getAttribute("data-epoch")).toContain("s1|");
    expect(screen.queryByTestId("smile-stage")).toBeNull();
    // And back to the Smile stage.
    fireEvent.click(screen.getByRole("tab", { name: "Smile" }));
    expect(screen.getByTestId("smile-stage")).toBeTruthy();
  });
});
