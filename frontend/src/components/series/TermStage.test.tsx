// The Series lens's Term stage: the production lane feeds the chart, the
// other visible lanes ride its lanes slot (listed in the chart legend), the
// footer legend reads each lane's ATM / var-swap at the shown expiry (rolled
// forward when the tab's expiry has left the ladder), plus the empty states
// and the loading veil. jsdom has no ResizeObserver, so the chart's plot
// stays unmeasured — the legends are what this locks.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import TermStage from "./TermStage";
import type { FramePayload, LaneFrameDoc, LaneSpec, TermPointDoc } from "../../lib/seriesTypes";

beforeAll(() => {
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(cleanup);

const term = (level: number): TermPointDoc[] => [
  { expiry: "2026-09-18", t: 0.03, atmVol: level + 0.05, varSwapVol: level + 0.06 },
  { expiry: "2026-10-16", t: 0.1, atmVol: level, varSwapVol: null },
  { expiry: "2026-12-18", t: 0.28, atmVol: level - 0.01, varSwapVol: level },
];
const laneDoc = (laneId: string, rows: TermPointDoc[]): LaneFrameDoc =>
  ({ laneId, slices: [], surface: null, term: rows, metrics: {}, status: "done" });
const spec = (id: string, patch: Partial<LaneSpec> = {}): LaneSpec => ({
  id, name: id.toUpperCase(), family: "lqd", colour: null, fitMode: null,
  patchFit: {}, patchOptions: {}, production: false, seed: "cold", ...patch,
});
const frame: FramePayload = {
  seriesId: "S1", idx: 0, ts: "2026-09-08T15:45:00", quoteKind: "quotes", spot: 100,
  expiries: ["2026-09-18", "2026-10-16", "2026-12-18"], forwards: {}, market: {},
  lanes: { a: laneDoc("a", term(0.2)), b: laneDoc("b", term(0.22)), c: laneDoc("c", []) },
};
const lanes = [spec("a", { production: true }), spec("b"), spec("c")];

const stage = (over: Partial<Parameters<typeof TermStage>[0]> = {}) => (
  <TermStage frame={frame} lanes={lanes} hidden={new Set()} expiry="2026-10-16" loading={false} {...over} />
);

describe("TermStage", () => {
  it("draws the chart with the other lane in its legend and the footer readout at the shown expiry", () => {
    render(stage());
    expect(screen.getByTestId("series-term-stage").getAttribute("data-expiry")).toBe("2026-10-16");
    // The chart's own legend lists lane B (the production lane is the fit line).
    expect(document.querySelectorAll("[data-lane-legend]").length).toBe(1);
    expect(document.querySelector('[data-lane-legend="b"]')).toBeTruthy();
    // The footer legend: every visible lane, ATM (and VS when the lane carries one).
    const rows = screen.getByTestId("series-lane-legend").querySelectorAll("[data-lane-row]");
    expect([...rows].map((r) => r.getAttribute("data-lane-row"))).toEqual(["a", "b", "c"]);
    expect(rows[0].textContent).toContain("ATM 20.0%");
    expect(rows[0].textContent).not.toContain("VS");
    expect(rows[1].textContent).toContain("ATM 22.0%");
    expect(rows[2].textContent).toContain("—");
  });
  it("rolls the expiry forward when the tab's has left the ladder; a hidden lane is not listed", () => {
    render(stage({ expiry: "2026-10-01", hidden: new Set(["b"]) }));
    expect(screen.getByTestId("series-term-stage").getAttribute("data-expiry")).toBe("2026-10-16");
    expect(document.querySelectorAll("[data-lane-legend]").length).toBe(0);
    const rows = screen.getByTestId("series-lane-legend").querySelectorAll("[data-lane-row]");
    expect([...rows].map((r) => r.getAttribute("data-lane-row"))).toEqual(["a", "c"]);
    expect(rows[0].textContent).toContain("ATM 20.0%"); // the rolled-to 10-16 rung: ATM only, no var-swap vol
    expect(rows[0].textContent).not.toContain("VS");
  });
  it("empty states: no frame · no term structure for the production lane", () => {
    const { unmount } = render(stage({ frame: null }));
    expect(screen.getByTestId("series-stage-empty").textContent).toBe("no frame");
    unmount();
    render(stage({ frame: { ...frame, lanes: { ...frame.lanes, a: laneDoc("a", []) } } }));
    expect(screen.getByTestId("series-stage-empty").textContent).toBe("no term structure at this frame");
  });
  it("keeps the last drawn frame under the veil while the next one loads", () => {
    const { rerender } = render(stage());
    rerender(stage({ frame: null, loading: true }));
    expect(screen.getByTestId("series-term-stage")).toBeTruthy();
    expect(screen.getByTestId("series-stage-loading")).toBeTruthy();
  });
});
