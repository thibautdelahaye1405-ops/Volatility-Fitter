// Lanes stage locks (SERIES ARC S5): the metric chips drive the overlay
// chart (one series per VISIBLE lane + the playhead line, a marker per lane
// at the playhead), the evidence table shows one row per visible lane with
// the best value lit and the worst frame scrubbing the transport, the
// roughness caption, and the filter panel — its lane select limited to the
// lanes with a ring, the cursor at the step committed on the playhead frame
// (matched by frame index). The hooks and the two charts are stubbed.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LanesStage from "./LanesStage";
import type { EvidencePayload, LaneSpec, StripPayload } from "../../lib/seriesTypes";

vi.mock("../OverlayCurvesChart", () => ({
  default: (p: { series: { label: string }[]; markers?: { label: string }[]; yLabel: string }) => (
    <div
      data-testid="overlay-chart"
      data-series={p.series.map((s) => s.label).join("|")}
      data-markers={(p.markers ?? []).map((m) => m.label).join("|")}
      data-ylabel={p.yLabel}
    />
  ),
}));
vi.mock("../FilterTimeline", () => ({
  FilterTimeline: (p: { steps: unknown[]; handle: number; cursor?: number | null }) => (
    <div data-testid="filter-timeline" data-steps={p.steps.length} data-handle={p.handle} data-cursor={p.cursor ?? ""} />
  ),
}));

let evidence: EvidencePayload | null = null;
vi.mock("../../state/useSeriesEvidence", () => ({ useSeriesEvidence: () => ({ evidence }) }));

let ringIndex: Record<string, string[]> = {};
const laneFilter = vi.fn((_s: string | null, laneId: string | null, expiry: string | null) => ({
  steps: laneId === "lqd_prior_filter" && expiry !== null ? [{ ts: 1 }, { ts: 2 }, { ts: 3 }] : [],
  frameIdx: laneId === "lqd_prior_filter" && expiry !== null ? [0, 1, 2] : [],
}));
vi.mock("../../state/useSeriesLaneFilter", () => ({
  useSeriesLaneFilterIndexes: () => ({ index: ringIndex, loaded: true }),
  useSeriesLaneFilter: (s: string | null, l: string | null, e: string | null) => laneFilter(s, l, e),
}));

const lane = (id: string, production = false): LaneSpec => ({
  id, name: id, family: "lqd", colour: null, fitMode: null, patchFit: {}, patchOptions: {}, production, seed: "cold",
});
const lanes = [lane("lqd_free", true), lane("lqd_prior_filter")];

const strip: StripPayload = {
  seriesId: "s1",
  idx: [0, 1, 2],
  ts: ["2026-09-10T13:45:00", "2026-09-10T14:00:00", "2026-09-10T14:15:00"],
  spot: [500, 501, 502],
  atmVol: { lqd_free: [0.2, 0.21, 0.22], lqd_prior_filter: [0.2, 0.205, 0.21] },
  lanes: {
    lqd_free: { rmsBp: [4, 5, 6], skew: [-0.1, -0.11, -0.12] },
    lqd_prior_filter: { rmsBp: [5, null, 7], skew: [-0.1, -0.1, -0.1] },
  },
};

const evidenceFixture = (): EvidencePayload => ({
  seriesId: "s1",
  expiry: "2026-12-18",
  lanes: {
    lqd_free: {
      nFrames: 3, nFailed: 0, meanRmsBp: 5, meanMaxIvBp: 12, worstFrame: { idx: 2, ts: "2026-09-10T14:15:00", rmsBp: 6 },
      roughnessAtmBp: 100, roughnessSkew: 0.01, meanPullAtmBp: 0, meanAbsPullAtmBp: 0, meanFitMs: 20, zetaAtmStd: null,
    },
    lqd_prior_filter: {
      nFrames: 3, nFailed: 1, meanRmsBp: 6, meanMaxIvBp: 14, worstFrame: { idx: 0, ts: "2026-09-10T13:45:00", rmsBp: 7 },
      roughnessAtmBp: 50, roughnessSkew: 0, meanPullAtmBp: -3, meanAbsPullAtmBp: 3, meanFitMs: 25, zetaAtmStd: 1.1,
    },
  },
});

const frames = strip.ts.map((ts, i) => ({
  idx: i, ts, snapshotId: i, spot: strip.spot[i], quoteKind: "quotes", nQuotes: 100, expiries: ["2026-12-18"],
  warmup: false, status: "ready" as const, error: null, harvestedTs: null,
}));

function mount(over: Partial<Parameters<typeof LanesStage>[0]> = {}) {
  const onScrub = vi.fn();
  render(
    <LanesStage
      seriesId="s1" frame={null} frames={frames} index={1} strip={strip} lanes={lanes} hidden={new Set()}
      expiry="2026-12-18" epoch="s1|done" onScrub={onScrub} {...over}
    />,
  );
  return onScrub;
}

afterEach(() => {
  cleanup();
  evidence = null;
  ringIndex = {};
  laneFilter.mockClear();
});

describe("LanesStage", () => {
  it("charts the chosen metric for every visible lane with the playhead line and markers", () => {
    mount();
    const chart = screen.getByTestId("overlay-chart");
    expect(chart.getAttribute("data-series")).toBe("lqd_free|lqd_prior_filter|playhead");
    expect(chart.getAttribute("data-ylabel")).toBe("rms bp");
    // Frame 1: the filter lane has no fit there → one marker only.
    expect(chart.getAttribute("data-markers")).toBe("lqd_free · 5.0");
    fireEvent.click(screen.getByRole("button", { name: "ATM σ" }));
    expect(screen.getByTestId("overlay-chart").getAttribute("data-ylabel")).toBe("ATM σ");
    expect(screen.getByTestId("overlay-chart").getAttribute("data-markers")).toBe("lqd_free · 21.0%|lqd_prior_filter · 20.5%");
    expect(screen.getByRole("button", { name: "ATM σ" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("drops a hidden lane from the chart and the table", () => {
    evidence = evidenceFixture();
    mount({ hidden: new Set(["lqd_prior_filter"]) });
    expect(screen.getByTestId("overlay-chart").getAttribute("data-series")).toBe("lqd_free|playhead");
    expect(screen.queryByText("lqd_prior_filter")).toBeNull();
  });

  it("shows the evidence rows, lights the best lane per column and scrubs on the worst frame", () => {
    evidence = evidenceFixture();
    const onScrub = mount();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain("lqd_free");
    expect(rows[0].textContent).toContain("★");
    expect(rows[1].textContent).toContain("1 failed");
    // Best per column: rms → lqd_free (5 < 6); roughness ATM → the filter lane (50 < 100).
    const rmsCells = document.querySelectorAll("[data-col=meanRmsBp]");
    expect(rmsCells[0].className).toContain("text-emerald-300");
    expect(rmsCells[1].className).not.toContain("text-emerald-300");
    const roughCells = document.querySelectorAll("[data-col=roughnessAtmBp]");
    expect(roughCells[0].className).not.toContain("text-emerald-300");
    expect(roughCells[1].className).toContain("text-emerald-300");
    // ζ std: only one finite row → nothing lit.
    const zetaCells = document.querySelectorAll("[data-col=zetaAtmStd]");
    expect(zetaCells[1].textContent).toBe("1.10");
    expect(zetaCells[1].className).not.toContain("text-emerald-300");
    expect(screen.getByTestId("roughness-caption").textContent).toContain("frame-to-frame move");
    fireEvent.click(screen.getByTestId("worst-frame-2"));
    expect(onScrub).toHaveBeenCalledWith(2);
  });

  it("hides the filter panel when no lane keeps a ring", () => {
    mount();
    expect(screen.queryByTestId("lanes-filter-panel")).toBeNull();
  });

  it("charts the filter lane's ring with the cursor at the playhead frame's step", () => {
    ringIndex = { lqd_prior_filter: ["2026-12-18", "2027-01-15"] };
    mount({ index: 2 });
    const laneSelect = screen.getByLabelText("Filter lane") as HTMLSelectElement;
    expect(Array.from(laneSelect.options).map((o) => o.value)).toEqual(["lqd_prior_filter"]);
    expect((screen.getByLabelText("Ring expiry") as HTMLSelectElement).value).toBe("2026-12-18");
    const tl = screen.getByTestId("filter-timeline");
    expect(tl.getAttribute("data-steps")).toBe("3");
    expect(tl.getAttribute("data-cursor")).toBe("2");
    expect(tl.getAttribute("data-handle")).toBe("0");
    fireEvent.change(screen.getByLabelText("Filter handle"), { target: { value: "1" } });
    expect(screen.getByTestId("filter-timeline").getAttribute("data-handle")).toBe("1");
    fireEvent.change(screen.getByLabelText("Ring expiry"), { target: { value: "2027-01-15" } });
    expect(laneFilter).toHaveBeenLastCalledWith("s1", "lqd_prior_filter", "2027-01-15");
  });
});
