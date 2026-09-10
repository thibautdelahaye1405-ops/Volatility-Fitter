// Options ▸ Observation filter: the four knobs surfaced 2026-09-10 (API-only
// before) — the adaptive innovation gate, the process-noise clock and its two
// session-clock companions, which stay dimmed on the calendar clock.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OPTIONS_DEFAULTS } from "../state/useOptions";
import type { OptionsSettings } from "../state/useOptions";
import ObservationFilterPanel from "./ObservationFilterPanel";

// The diagnostics table fetches per ticker; a never-settling promise keeps the
// panel in its initial state without a live backend.
vi.mock("../state/api", () => ({ api: { get: vi.fn(() => new Promise(() => {})) } }));

const draft = (over: Partial<OptionsSettings> = {}): OptionsSettings => ({ ...OPTIONS_DEFAULTS, ...over });

const numberInput = (label: string): HTMLInputElement =>
  screen.getByText(label).parentElement!.querySelector("input") as HTMLInputElement;

function mount(over: Partial<OptionsSettings> = {}, patch = vi.fn()) {
  render(
    <ObservationFilterPanel draft={draft({ observationFilterMode: "overlay", ...over })} patch={patch}
      live ticker="SPY" fitMode="mid" refreshKey={0} />,
  );
  return patch;
}

afterEach(cleanup);

describe("ObservationFilterPanel · the surfaced knobs", () => {
  it("shows the adaptive gate and the clock with their defaults, the clock companions dimmed on calendar", () => {
    const patch = mount();
    expect(numberInput("Adaptive gate (σ; 0 = off)").value).toBe("3");
    const clock = screen.getByTestId("filter-clock") as HTMLSelectElement;
    expect(clock.value).toBe("calendar");
    expect(numberInput("Session share (of a day's variance)").disabled).toBe(true);
    expect(numberInput("Non-trading day weight").disabled).toBe(true);
    fireEvent.change(numberInput("Adaptive gate (σ; 0 = off)"), { target: { value: "0" } });
    expect(patch).toHaveBeenCalledWith({ filterAdaptiveSigma: 0 });
    fireEvent.change(clock, { target: { value: "session" } });
    expect(patch).toHaveBeenCalledWith({ filterClock: "session" });
  });

  it("enables the session share and the non-trading weight under the session clock", () => {
    const patch = mount({ filterClock: "session" });
    const share = numberInput("Session share (of a day's variance)");
    const weight = numberInput("Non-trading day weight");
    expect(share.disabled).toBe(false);
    expect(share.value).toBe("0.6");
    expect(weight.value).toBe("0");
    fireEvent.change(share, { target: { value: "0.9" } });
    expect(patch).toHaveBeenCalledWith({ filterSessionShare: 0.9 });
    fireEvent.change(weight, { target: { value: "1" } });
    expect(patch).toHaveBeenCalledWith({ filterNonTradingWeight: 1 });
  });

  it("hides every knob while the filter is off", () => {
    mount({ observationFilterMode: "off" });
    expect(screen.queryByText("Adaptive gate (σ; 0 = off)")).toBeNull();
    expect(screen.queryByTestId("filter-clock")).toBeNull();
  });
});
