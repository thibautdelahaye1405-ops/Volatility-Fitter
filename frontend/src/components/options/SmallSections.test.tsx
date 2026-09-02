// Options ▸ Workflow & data is streaming-aware: with Stream live book on, the
// options-quotes timer is dimmed (the book serves every fetch and the streaming
// refit replaces the timer) while Spot prices stays live — Real-time is what
// turns on live re-pricing and the streaming refit loop, whose cadence then
// shows in the dialog.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OPTIONS_DEFAULTS } from "../../state/useOptions";
import type { OptionsSettings } from "../../state/useOptions";
import { WorkflowSection } from "./SmallSections";

const draft = (over: Partial<OptionsSettings> = {}): OptionsSettings => ({ ...OPTIONS_DEFAULTS, ...over });

const segButtons = (testId: string): HTMLButtonElement[] =>
  Array.from(screen.getByTestId(testId).querySelectorAll("button")) as HTMLButtonElement[];

afterEach(cleanup);

describe("WorkflowSection while the live book streams", () => {
  it("dims the options-quotes timer and hides its cadence rows", () => {
    render(<WorkflowSection draft={draft({ autoStream: true, optionsFetchMode: "auto" })} patch={vi.fn()} live />);
    expect(segButtons("options-quotes").every((b) => b.disabled)).toBe(true);
    expect(screen.getByTestId("quotes-streaming-note").textContent).toMatch(/live book/);
    expect(screen.queryByText("Fetch every (min)")).toBeNull();
  });

  it("keeps Spot prices live, explains it, and surfaces the stream refit cadence in real-time mode", () => {
    render(<WorkflowSection draft={draft({ autoStream: true, spotMode: "realtime" })} patch={vi.fn()} live />);
    expect(segButtons("spot-prices").every((b) => !b.disabled)).toBe(true);
    expect(screen.getByTestId("spot-streaming-note").textContent).toMatch(/streaming refit/);
    expect(screen.getByText("Poll every (s)")).toBeTruthy();
    expect(screen.getByText("Stream refit every (s)")).toBeTruthy();
  });

  it("restores the timer and hides the streaming notes once streaming is off", () => {
    render(<WorkflowSection draft={draft({ autoStream: false, optionsFetchMode: "auto", spotMode: "realtime" })} patch={vi.fn()} live />);
    expect(segButtons("options-quotes").every((b) => !b.disabled)).toBe(true);
    expect(screen.getByText("Fetch every (min)")).toBeTruthy();
    expect(screen.queryByTestId("quotes-streaming-note")).toBeNull();
    expect(screen.queryByTestId("spot-streaming-note")).toBeNull();
    expect(screen.queryByText("Stream refit every (s)")).toBeNull();
  });
});
