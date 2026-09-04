// Spot move card contract: the Market / Scenario follow selector lights the
// followed level and dims the other (the dial is locked while following the
// market), the ± fine-tune buttons (0.1 %, Shift = 1 %, clamped to ±15 %),
// Reset to 0.0 % and Sync to market, the real-time lock, and the Recalibrate
// button that names the top bar's scope and narrates the background job.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpotPanel, { DIAL_MAX_PCT, clockOf, snapDialPct } from "./SpotPanel";
import { SCOPE_STORAGE_KEY } from "../lib/calibScope";
import type { SpotState } from "../state/useSpot";

const state = (over: Partial<SpotState> = {}): SpotState => ({
  ticker: "SPY",
  anchorSpot: 6150,
  spotReturn: 0,
  shiftedSpot: 6150,
  regime: "sticky_strike",
  regimeSsr: 1,
  follow: "scenario",
  followForced: false,
  liveSpot: 6162.3,
  liveReturn: 6162.3 / 6150 - 1,
  liveAt: "2026-09-02T14:32:00",
  liveSource: "stream",
  streaming: true,
  sourceLabel: "Bloomberg",
  litNodes: 4,
  lvEnabled: true,
  ...over,
});

function renderPanel(over: Partial<Parameters<typeof SpotPanel>[0]> = {}) {
  const onSpotReturn = vi.fn();
  const onFollow = vi.fn();
  const onCalibrate = vi.fn();
  const onProbeLive = vi.fn();
  const utils = render(
    <SpotPanel
      spotReturn={0}
      spotState={state()}
      onSpotReturn={onSpotReturn}
      onFollow={onFollow}
      onCalibrate={onCalibrate}
      onProbeLive={onProbeLive}
      calib={{ running: false, current: "", phase: "", done: 0, total: 0 }}
      note={null}
      disabled={false}
      {...over}
    />,
  );
  return { ...utils, onSpotReturn, onFollow, onCalibrate, onProbeLive };
}

/** The emphasis of the spot-level ROW named `label` (the selector reuses the word "Scenario"). */
const emphasisOf = (label: string) =>
  screen.getAllByText(label).map((e) => e.closest("[data-emphasis]")).find(Boolean)?.getAttribute("data-emphasis");

afterEach(() => { cleanup(); localStorage.removeItem(SCOPE_STORAGE_KEY); });

describe("SpotPanel", () => {
  it("shows the calibrated, market (streamed) and scenario spots", () => {
    renderPanel({ spotReturn: 0.03 });
    expect(screen.getByText("6150.00")).toBeTruthy(); // calibrated anchor
    expect(screen.getByText(/6162\.30\s+\+0\.20%/)).toBeTruthy(); // market + return vs anchor
    expect(screen.getByText(/Bloomberg · streaming/)).toBeTruthy();
    expect(screen.getByText(/6334\.50\s+\+3\.0%/)).toBeTruthy(); // scenario = anchor × 1.03
    expect(screen.getByText("STREAMING")).toBeTruthy();
    expect(screen.queryByLabelText("Probe market spot")).toBeNull(); // no probe while streaming
  });

  it("lights the followed level: scenario lights the dial, market dims it", () => {
    renderPanel({ spotReturn: 0.03 });
    expect(emphasisOf("Scenario")).toBe("on");
    expect(emphasisOf("Market")).toBe("off");
    expect(screen.getByTestId("spot-dial").getAttribute("data-active")).toBe("true");
    expect((screen.getByLabelText("Spot return") as HTMLInputElement).disabled).toBe(false);
    cleanup();
    renderPanel({ spotState: state({ follow: "market" }) });
    expect(emphasisOf("Market")).toBe("on");
    expect(emphasisOf("Scenario")).toBe("off");
    expect(screen.getByTestId("spot-dial").getAttribute("data-active")).toBe("false");
    expect((screen.getByLabelText("Spot return") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Spot up 0.1 percent") as HTMLButtonElement).disabled).toBe(true);
  });

  it("switches the follow mode from the selector", () => {
    const { onFollow } = renderPanel();
    fireEvent.click(screen.getByText("Market spot"));
    expect(onFollow).toHaveBeenLastCalledWith("market");
    fireEvent.click(screen.getByText("Scenario", { selector: "button" }));
    expect(onFollow).toHaveBeenLastCalledWith("scenario");
  });

  it("offers a probe button and the stamp when the market spot is not streamed", () => {
    const { onProbeLive } = renderPanel({ spotState: state({ streaming: false, liveSource: "probe" }) });
    fireEvent.click(screen.getByLabelText("Probe market spot"));
    expect(onProbeLive).toHaveBeenCalledTimes(1);
    expect(screen.getByText(new RegExp(`probe ${clockOf("2026-09-02T14:32:00")}`))).toBeTruthy();
  });

  it("fine-tunes the dial by 0.1 % (Shift: 1 %) and clamps at the range", () => {
    const { onSpotReturn } = renderPanel({ spotReturn: 0.02 });
    fireEvent.click(screen.getByLabelText("Spot up 0.1 percent"));
    expect(onSpotReturn).toHaveBeenLastCalledWith(0.021);
    fireEvent.click(screen.getByLabelText("Spot down 0.1 percent"));
    expect(onSpotReturn).toHaveBeenLastCalledWith(0.019);
    fireEvent.click(screen.getByLabelText("Spot up 0.1 percent"), { shiftKey: true });
    expect(onSpotReturn).toHaveBeenLastCalledWith(0.03);
    cleanup();
    const top = renderPanel({ spotReturn: DIAL_MAX_PCT / 100 });
    expect((screen.getByLabelText("Spot up 0.1 percent") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Spot down 0.1 percent"));
    expect(top.onSpotReturn).toHaveBeenLastCalledWith(0.149);
  });

  it("resets to 0.0 % and syncs the dial to the market return", () => {
    const { onSpotReturn } = renderPanel({ spotReturn: 0.03 });
    fireEvent.click(screen.getByText(/Reset to 0\.0%/));
    expect(onSpotReturn).toHaveBeenLastCalledWith(0);
    fireEvent.click(screen.getByText("Sync to market"));
    expect(onSpotReturn).toHaveBeenLastCalledWith(0.002); // +0.20 % snapped to the 0.1 % grid
  });

  it("disables Reset at 0 and Sync when the scenario already sits at the market spot", () => {
    renderPanel({ spotReturn: 6162.3 / 6150 - 1 });
    expect((screen.getByText("Sync to market") as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    renderPanel({ spotReturn: 0 });
    expect((screen.getByText(/Reset to 0\.0%/).closest("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the STREAMING badge while the book streams and keeps the dial free in scenario mode", () => {
    renderPanel({ spotState: state({ streaming: true, follow: "scenario" }) });
    expect(screen.getByText("STREAMING")).toBeTruthy();
    expect((screen.getByLabelText("Spot return") as HTMLInputElement).disabled).toBe(false);
    cleanup();
    renderPanel({ spotState: state({ streaming: false, follow: "market" }) });
    expect(screen.queryByText("STREAMING")).toBeNull();
    expect(screen.queryByText("LIVE")).toBeNull(); // the real-time spot mode badge is gone
    expect(emphasisOf("Market")).toBe("on");
  });

  it("recalibrates the ticker with the top bar's scope and narrates the job", () => {
    localStorage.setItem(SCOPE_STORAGE_KEY, "parametric");
    const { onCalibrate } = renderPanel();
    const button = screen.getByText("Recalibrate SPY (Param only)");
    expect(screen.getByText(/Calibrate, this ticker only · streamed quotes \+ spot snapshot · 4 nodes/)).toBeTruthy();
    fireEvent.click(button);
    expect(onCalibrate).toHaveBeenCalledWith("parametric");
    cleanup();
    localStorage.setItem(SCOPE_STORAGE_KEY, "both");
    renderPanel({ spotState: state({ streaming: false, liveSource: "chain" }) });
    expect(screen.getByText("Recalibrate SPY (Param + LV)")).toBeTruthy();
    expect(screen.getByText(/last fetched quotes \+ spot · 4 nodes \+ LV/)).toBeTruthy();
    cleanup();
    renderPanel({
      calib: { running: true, current: "SPY 2026-09-18", phase: "Parametric", done: 2, total: 5 },
      note: { ok: true, text: "Book snapshot taken (quotes + spot) · calibrating SPY — Param + LV at 6162.30…" },
    });
    const busy = screen.getByText(/Calibrating · SPY 2026-09-18 · Parametric 2\/5/) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toMatch(/Book snapshot taken/);
  });

  it("snaps dial values to the 0.1 % grid inside ±15 %", () => {
    expect(snapDialPct(2.04)).toBe(2);
    expect(snapDialPct(2.06)).toBe(2.1);
    expect(snapDialPct(40)).toBe(DIAL_MAX_PCT);
    expect(snapDialPct(-40)).toBe(-DIAL_MAX_PCT);
    expect(clockOf(null)).toBe("");
    expect(clockOf("garbage")).toBe("");
  });

  it("standard size keeps the follow selector, the three spot rows, the dial and Recalibrate", () => {
    const onToggleSize = vi.fn();
    renderPanel({ spotReturn: 0.03, size: "M", onToggleSize });
    expect(screen.getByText("Market spot")).toBeTruthy();
    expect(screen.getByText("6150.00")).toBeTruthy(); // Calibrated row stays
    expect(screen.getByLabelText("Spot return")).toBeTruthy();
    expect(screen.getByText(/Recalibrate SPY/)).toBeTruthy();
    expect(screen.queryByText(/Regime · R/)).toBeNull(); // expanded-only rows
    expect(screen.queryByText(/Reset to 0\.0%/)).toBeNull();
    expect(screen.queryByText(/no recalibration/)).toBeNull();
    expect(screen.queryByText(/Calibrate, this ticker only/)).toBeNull();
    fireEvent.click(screen.getByLabelText("Expand Spot move"));
    expect(onToggleSize).toHaveBeenCalledTimes(1);
  });

  it("compact size is one row naming the followed spot, and the row expands the card", () => {
    const onToggleSize = vi.fn();
    renderPanel({ spotReturn: 0.03, size: "S", onToggleSize });
    expect(screen.queryByLabelText("Spot return")).toBeNull();
    expect(screen.queryByText("STREAMING")).toBeNull(); // the badge shrinks to its dot
    const expand = screen.getByLabelText("Expand Spot move");
    expect(expand.textContent).toMatch(/Scenario 6334\.50 \+3\.0%/);
    fireEvent.click(expand);
    expect(onToggleSize).toHaveBeenCalledTimes(1);
    cleanup();
    renderPanel({ size: "S", spotState: state({ follow: "market" }), onToggleSize });
    expect(screen.getByLabelText("Expand Spot move").textContent).toMatch(/Market 6162\.30 \+0\.20%/);
    cleanup();
    renderPanel({ size: "S", onToggleSize, calib: { running: true, current: "SPY", phase: "", done: 1, total: 3 } });
    expect(screen.getByLabelText("Expand Spot move").textContent).toMatch(/Calibrating 1\/3/);
  });

  it("expanded size shows everything and offers the fold-back toggle", () => {
    const onToggleSize = vi.fn();
    renderPanel({ size: "L", onToggleSize });
    expect(screen.getByText(/Regime · R/)).toBeTruthy();
    expect(screen.getByText(/Calibrate, this ticker only/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Shrink Spot move"));
    expect(onToggleSize).toHaveBeenCalledTimes(1);
    cleanup();
    renderPanel(); // outside the column: expanded, no toggle
    expect(screen.queryByLabelText("Shrink Spot move")).toBeNull();
  });
});

