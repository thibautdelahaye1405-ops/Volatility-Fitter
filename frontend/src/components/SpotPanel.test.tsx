// Spot move card contract: the three spot levels (calibrated / market /
// scenario), the ± fine-tune buttons (0.1 %, Shift = 1 %, clamped to ±15 %),
// Reset / Sync to market, the real-time lock, and the Re-anchor button that
// narrates the background job instead of blanking anything.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpotPanel, { DIAL_MAX_PCT, clockOf, snapDialPct } from "./SpotPanel";
import type { SpotState } from "../state/useSpot";

const state = (over: Partial<SpotState> = {}): SpotState => ({
  ticker: "SPY",
  anchorSpot: 6150,
  spotReturn: 0,
  shiftedSpot: 6150,
  regime: "sticky_strike",
  regimeSsr: 1,
  shiftSource: null,
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
  const onCalibrate = vi.fn();
  const onSyncLive = vi.fn();
  const onProbeLive = vi.fn();
  const utils = render(
    <SpotPanel
      spotReturn={0}
      spotState={state()}
      spotMode="static"
      onSpotReturn={onSpotReturn}
      onCalibrate={onCalibrate}
      onSyncLive={onSyncLive}
      onProbeLive={onProbeLive}
      calib={{ running: false, current: "", phase: "", done: 0, total: 0 }}
      note={null}
      disabled={false}
      {...over}
    />,
  );
  return { ...utils, onSpotReturn, onCalibrate, onSyncLive, onProbeLive };
}

afterEach(cleanup);

describe("SpotPanel", () => {
  it("shows the calibrated, market (streamed) and scenario spots", () => {
    renderPanel({ spotReturn: 0.03 });
    expect(screen.getByText("6150.00")).toBeTruthy(); // calibrated anchor
    expect(screen.getByText(/6162\.30\s+\+0\.20%/)).toBeTruthy(); // market + return vs anchor
    expect(screen.getByText(/Bloomberg · streaming/)).toBeTruthy();
    expect(screen.getByText(/6334\.50\s+\+3\.0%/)).toBeTruthy(); // scenario = anchor × 1.03
    expect(screen.getByText("STREAM")).toBeTruthy();
    expect(screen.queryByLabelText("Probe market spot")).toBeNull(); // no probe while streaming
  });

  it("offers a probe button and the stamp when the market spot is not streamed", () => {
    renderPanel({ spotState: state({ streaming: false, liveSource: "probe" }) });
    const probe = screen.getByLabelText("Probe market spot");
    expect(screen.getByText(new RegExp(`probe ${clockOf("2026-09-02T14:32:00")}`))).toBeTruthy();
    fireEvent.click(probe);
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

  it("resets and syncs to the market spot", () => {
    const { onSpotReturn, onSyncLive } = renderPanel({ spotReturn: 0.03 });
    fireEvent.click(screen.getByText("Reset"));
    expect(onSpotReturn).toHaveBeenLastCalledWith(0);
    fireEvent.click(screen.getByText("Sync to market"));
    expect(onSyncLive).toHaveBeenCalledTimes(1);
  });

  it("hides Sync when the scenario already sits at the market spot", () => {
    renderPanel({ spotReturn: 6162.3 / 6150 - 1 });
    expect((screen.getByText("Sync to market") as HTMLButtonElement).disabled).toBe(true);
  });

  it("locks the dial in real-time spot mode", () => {
    renderPanel({ spotMode: "realtime" });
    expect((screen.getByLabelText("Spot return") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Spot up 0.1 percent") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("LIVE")).toBeTruthy();
    expect(screen.queryByText("Sync to market")).toBeNull();
  });

  it("re-anchors the ticker and narrates the background job", () => {
    const { onCalibrate } = renderPanel();
    const button = screen.getByText("Re-anchor SPY");
    expect(screen.getByText(/calibrate 4 nodes \+ LV at the market spot/)).toBeTruthy();
    fireEvent.click(button);
    expect(onCalibrate).toHaveBeenCalledTimes(1);
    cleanup();
    renderPanel({
      calib: { running: true, current: "SPY 2026-09-18", phase: "Parametric", done: 2, total: 5 },
      note: { ok: true, text: "Quotes refetched · calibrating 4 nodes + LV at 6162.30…" },
    });
    const busy = screen.getByText(/Calibrating · SPY 2026-09-18 · Parametric 2\/5/) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toMatch(/Quotes refetched/);
  });

  it("snaps dial values to the 0.1 % grid inside ±15 %", () => {
    expect(snapDialPct(2.04)).toBe(2);
    expect(snapDialPct(2.06)).toBe(2.1);
    expect(snapDialPct(40)).toBe(DIAL_MAX_PCT);
    expect(snapDialPct(-40)).toBe(-DIAL_MAX_PCT);
    expect(clockOf(null)).toBe("");
    expect(clockOf("garbage")).toBe("");
  });
});
