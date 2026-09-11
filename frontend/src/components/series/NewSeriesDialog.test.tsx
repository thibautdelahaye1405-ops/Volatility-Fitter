// New series… dialog: the Start flow around the creation warnings
// (2026-09-11 — a filter lane known unusable at intraday cadence had
// started silently and stalled a series at 8/10). Locks: a Start without an
// Estimate whose creation carries warnings stops on the draft (warnings
// shown, "Start anyway", no job started); the second click starts it; a
// warning-free creation starts at once; an Estimate that already showed the
// warnings lets Start go straight through; an edit after the stop discards
// the draft. The frame budget field rides the spec.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NewSeriesDialog from "./NewSeriesDialog";
import type { LaneSpec, SeriesEstimate } from "../../lib/seriesTypes";

const presets: LaneSpec[] = [
  { id: "lqd_free", name: "LQD-24 free", family: "lqd", colour: null, fitMode: null, patchFit: {}, patchOptions: {}, production: false, seed: "cold" },
  { id: "lqd_prior_filter", name: "LQD-24 + prior + filter", family: "lqd", colour: null, fitMode: null, patchFit: {}, patchOptions: { observationFilterMode: "active" }, production: false, seed: "cold" },
];
const WARNING = "lane 'LQD-24 + prior + filter': the active filter is not usable at intraday cadence on short rungs today";
const estimateOf = (warnings: string[]): SeriesEstimate => ({
  instants: ["2026-09-10T14:00:00"], servable: [true], nFrames: 1, harvestSeconds: 12, calibrateSeconds: 4, perLaneSeconds: {}, warnings,
});

const createSeries = vi.fn();
const startSeries = vi.fn();
const deleteSeries = vi.fn();
const estimateSeries = vi.fn();
vi.mock("../../state/useSeries", () => ({
  fetchPresets: () => Promise.resolve(presets),
  createSeries: (...a: unknown[]) => createSeries(...a),
  startSeries: (...a: unknown[]) => startSeries(...a),
  deleteSeries: (...a: unknown[]) => deleteSeries(...a),
  estimateSeries: (...a: unknown[]) => estimateSeries(...a),
  importSeries: vi.fn(),
}));

async function open() {
  const onCreated = vi.fn();
  const onClose = vi.fn();
  render(<NewSeriesDialog open onClose={onClose} ticker="NVDA" fitMode="haircut" onCreated={onCreated} />);
  // The presets load before the buttons wake up.
  await waitFor(() => expect((screen.getByRole("button", { name: "Start" }) as HTMLButtonElement).disabled).toBe(false));
  return { onCreated, onClose };
}

const click = async (name: string) => {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
};

afterEach(cleanup); // no globals: unmount each dialog, else the next test sees two

beforeEach(() => {
  createSeries.mockReset();
  startSeries.mockReset();
  deleteSeries.mockReset();
  estimateSeries.mockReset();
  startSeries.mockResolvedValue({ seriesId: "s1", running: "s1", queue: [], progress: null });
  deleteSeries.mockResolvedValue({ deleted: true, id: "s1" });
});

describe("NewSeriesDialog: Start and the creation warnings", () => {
  it("stops on the draft when the creation carries warnings the user has not seen, then Start anyway runs it", async () => {
    createSeries.mockResolvedValue({ id: "s1", estimate: estimateOf([WARNING]) });
    const { onCreated, onClose } = await open();
    await click("Start");
    expect(createSeries).toHaveBeenCalledTimes(1);
    expect(startSeries).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByTestId("series-warnings").textContent).toContain("active filter is not usable");
    expect(screen.getByText(/Created as a draft/)).toBeTruthy();
    await click("Start anyway");
    expect(createSeries).toHaveBeenCalledTimes(1); // the draft is started, not re-created
    expect(startSeries).toHaveBeenCalledWith("s1");
    expect(onCreated).toHaveBeenCalledWith("s1");
    expect(onClose).toHaveBeenCalled();
  });

  it("starts at once when the creation carries no warning", async () => {
    createSeries.mockResolvedValue({ id: "s2", estimate: estimateOf([]) });
    const { onCreated } = await open();
    await click("Start");
    expect(startSeries).toHaveBeenCalledWith("s2");
    expect(onCreated).toHaveBeenCalledWith("s2");
    expect(screen.queryByTestId("series-warnings")).toBeNull();
  });

  it("does not ask twice: an Estimate that showed the warnings lets Start go through", async () => {
    estimateSeries.mockResolvedValue(estimateOf([WARNING]));
    createSeries.mockResolvedValue({ id: "s3", estimate: estimateOf([WARNING]) });
    const { onCreated } = await open();
    await click("Estimate");
    expect(screen.getByTestId("series-warnings").textContent).toContain(WARNING);
    await click("Start");
    expect(startSeries).toHaveBeenCalledWith("s3");
    expect(onCreated).toHaveBeenCalledWith("s3");
  });

  it("an edit after the stop discards the draft and the button reads Start again", async () => {
    createSeries.mockResolvedValue({ id: "s4", estimate: estimateOf([WARNING]) });
    await open();
    await click("Start");
    expect(screen.getByRole("button", { name: "Start anyway" })).toBeTruthy();
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Note"), { target: { value: "edited" } });
    });
    expect(deleteSeries).toHaveBeenCalledWith("s4");
    expect(screen.getByRole("button", { name: "Start" })).toBeTruthy();
    expect(screen.queryByTestId("series-warnings")).toBeNull();
  });

  it("Cancel after the stop discards the draft", async () => {
    createSeries.mockResolvedValue({ id: "s5", estimate: estimateOf([WARNING]) });
    const { onClose } = await open();
    await click("Start");
    await click("Cancel");
    expect(deleteSeries).toHaveBeenCalledWith("s5");
    expect(onClose).toHaveBeenCalled();
  });

  it("the frame budget field rides the spec: 300 s by default, blank = no cap, below 5 s blocks", async () => {
    createSeries.mockResolvedValue({ id: "s6", estimate: estimateOf([]) });
    await open();
    const budget = screen.getByLabelText("Frame budget (s)") as HTMLInputElement;
    expect(budget.value).toBe("300");
    await click("Start");
    expect(createSeries.mock.calls[0][0]).toMatchObject({ frameBudgetSeconds: 300 });
    await act(async () => {
      fireEvent.change(budget, { target: { value: "" } });
    });
    await click("Start");
    expect(createSeries.mock.calls[1][0]).toMatchObject({ frameBudgetSeconds: null });
    await act(async () => {
      fireEvent.change(budget, { target: { value: "2" } });
    });
    await click("Start");
    expect(createSeries).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert").textContent).toContain("at least 5 seconds");
  });
});
