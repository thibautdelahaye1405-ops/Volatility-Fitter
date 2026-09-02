// Options ▸ Workflow & data under the Auto-update model: ONE control without a
// live stream (Off / Spot only / Spot + quotes every x s, 15 s floor for a full
// snapshot), dimmed while Stream live book is on — spot and quotes then flow
// continuously; "Freeze fit while streaming" holds the fit instead and the
// stream refit cadence shows only while the fit is not frozen.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OPTIONS_DEFAULTS } from "../../state/useOptions";
import type { OptionsSettings } from "../../state/useOptions";
import { WorkflowSection } from "./SmallSections";

const draft = (over: Partial<OptionsSettings> = {}): OptionsSettings => ({ ...OPTIONS_DEFAULTS, ...over });

const updateButtons = (): HTMLButtonElement[] =>
  Array.from(screen.getByTestId("auto-update").querySelectorAll("button")) as HTMLButtonElement[];

const numberInput = (label: string): HTMLInputElement =>
  screen.getByText(label).parentElement!.querySelector("input") as HTMLInputElement;

afterEach(cleanup);

describe("WorkflowSection · Auto-update without a live stream", () => {
  it("offers Off / Spot only / Spot + quotes and a cadence row for the timed choices", () => {
    const patch = vi.fn();
    render(<WorkflowSection draft={draft({ autoStream: false })} patch={patch} live />);
    expect(updateButtons().map((b) => b.textContent)).toEqual(["Off", "Spot only", "Spot + quotes"]);
    expect(updateButtons().every((b) => !b.disabled)).toBe(true);
    expect(screen.queryByText("Every (s)")).toBeNull(); // off: no cadence
    fireEvent.click(updateButtons()[1]);
    expect(patch).toHaveBeenCalledWith({ autoUpdate: "spot" });
    cleanup();
    render(<WorkflowSection draft={draft({ autoStream: false, autoUpdate: "spot", autoUpdateSeconds: 5 })} patch={patch} live />);
    expect(numberInput("Every (s)").value).toBe("5");
    expect(screen.queryByText(/15 s minimum/)).toBeNull();
  });

  it("floors Spot + quotes at 15 s: switching to it lifts a short cadence, and so does typing below it", () => {
    const patch = vi.fn();
    render(<WorkflowSection draft={draft({ autoStream: false, autoUpdate: "spot", autoUpdateSeconds: 5 })} patch={patch} live />);
    fireEvent.click(updateButtons()[2]);
    expect(patch).toHaveBeenCalledWith({ autoUpdate: "snapshot", autoUpdateSeconds: 15 });
    cleanup();
    render(<WorkflowSection draft={draft({ autoStream: false, autoUpdate: "snapshot", autoUpdateSeconds: 60 })} patch={patch} live />);
    expect(screen.getByText(/15 s minimum/)).toBeTruthy();
    fireEvent.change(numberInput("Every (s)"), { target: { value: "3" } });
    expect(patch).toHaveBeenLastCalledWith({ autoUpdateSeconds: 15 });
    fireEvent.change(numberInput("Every (s)"), { target: { value: "30" } });
    expect(patch).toHaveBeenLastCalledWith({ autoUpdateSeconds: 30 });
  });

  it("never shows the old split selectors", () => {
    render(<WorkflowSection draft={draft()} patch={vi.fn()} live />);
    expect(screen.queryByText("Spot prices")).toBeNull();
    expect(screen.queryByText("Options quotes")).toBeNull();
    expect(screen.queryByText("Fetch every (min)")).toBeNull();
  });
});

describe("WorkflowSection · while the live book streams", () => {
  it("dims Auto-update with the streaming note and hides its cadence", () => {
    render(<WorkflowSection draft={draft({ autoStream: true, autoUpdate: "snapshot", autoUpdateSeconds: 60 })} patch={vi.fn()} live />);
    expect(updateButtons().every((b) => b.disabled)).toBe(true);
    expect(screen.getByTestId("update-streaming-note").textContent).toMatch(/flow continuously/);
    expect(screen.queryByText("Every (s)")).toBeNull();
  });

  it("offers the freeze switch and the stream refit cadence while the fit is not frozen", () => {
    const patch = vi.fn();
    render(<WorkflowSection draft={draft({ autoStream: true, streamFreezeFit: false, streamRefitSeconds: 5 })} patch={patch} live />);
    const freeze = screen.getByText("Freeze fit while streaming").closest("label")!.querySelector("input") as HTMLInputElement;
    expect(freeze.checked).toBe(false);
    expect(numberInput("Stream refit every (s)").value).toBe("5");
    fireEvent.click(freeze);
    expect(patch).toHaveBeenCalledWith({ streamFreezeFit: true });
  });

  it("hides the refit cadence once the fit is frozen, and everything streaming-related once streaming is off", () => {
    render(<WorkflowSection draft={draft({ autoStream: true, streamFreezeFit: true })} patch={vi.fn()} live />);
    expect(screen.getByText("Freeze fit while streaming")).toBeTruthy();
    expect(screen.queryByText("Stream refit every (s)")).toBeNull();
    cleanup();
    render(<WorkflowSection draft={draft({ autoStream: false })} patch={vi.fn()} live />);
    expect(screen.queryByText("Freeze fit while streaming")).toBeNull();
    expect(screen.queryByText("Stream refit every (s)")).toBeNull();
    expect(screen.queryByTestId("update-streaming-note")).toBeNull();
  });
});
