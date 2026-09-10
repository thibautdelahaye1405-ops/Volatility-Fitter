// The Series transport bar: the readout names the instant under the
// playhead, the buttons report actions, the scrubber / speed report state,
// and the gap / warm-up marks sit under the scrubber.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TransportBar, { transportReadout } from "./TransportBar";
import { initialPlayback } from "../../lib/seriesPlayback";
import type { FrameDoc } from "../../lib/seriesTypes";

afterEach(cleanup);

const doc = (idx: number, ts: string, patch: Partial<FrameDoc> = {}): FrameDoc => ({
  idx, ts, snapshotId: null, spot: 100, quoteKind: "quotes", nQuotes: 10, expiries: [],
  warmup: false, status: "ready", error: null, harvestedTs: null, ...patch,
});

const frames: FrameDoc[] = [
  doc(0, "2026-09-08T13:30:00", { warmup: true }),
  doc(1, "2026-09-08T13:45:00"),
  doc(2, "2026-09-08T14:00:00"),
  doc(3, "2026-09-09T13:30:00", { quoteKind: "marks" }),
  doc(4, "2026-09-09T13:45:00"),
];

describe("TransportBar", () => {
  it("renders the readout for the frame under the playhead", () => {
    render(
      <TransportBar playback={{ ...initialPlayback(), index: 1 }} nFrames={5} frames={frames} onChange={() => {}} onAction={() => {}} />,
    );
    expect(screen.getByTestId("series-transport")).toBeTruthy();
    expect(screen.getByTestId("series-readout").textContent).toBe("2026-09-08 13:45 UTC · frame 2/5 · NBBO");
    expect(transportReadout(frames, 3, 5)).toBe("2026-09-09 13:30 UTC · frame 4/5 · marks");
    expect(transportReadout(frames, 0, 5)).toBe("2026-09-08 13:30 UTC · frame 1/5 · NBBO · warm-up");
    expect(transportReadout([], 0, 0)).toBe("— · frame 0/0 · NBBO");
  });

  it("Play reports toggle; the label flips to Pause while playing", () => {
    const onAction = vi.fn();
    const { rerender } = render(
      <TransportBar playback={initialPlayback()} nFrames={5} frames={frames} onChange={() => {}} onAction={onAction} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(onAction).toHaveBeenCalledWith("toggle");
    fireEvent.click(screen.getByRole("button", { name: "Step forward" }));
    expect(onAction).toHaveBeenLastCalledWith("next");
    fireEvent.click(screen.getByRole("button", { name: "Last frame" }));
    expect(onAction).toHaveBeenLastCalledWith("last");
    rerender(
      <TransportBar playback={{ ...initialPlayback(), playing: true }} nFrames={5} frames={frames} onChange={() => {}} onAction={onAction} />,
    );
    expect(screen.getByRole("button", { name: "Pause" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("the scrubber and the speed menu report state changes; loop is a pressed toggle", () => {
    const onChange = vi.fn();
    const onAction = vi.fn();
    render(
      <TransportBar playback={{ ...initialPlayback(), playing: true }} nFrames={5} frames={frames} onChange={onChange} onAction={onAction} />,
    );
    const scrub = screen.getByLabelText("Frame") as HTMLInputElement;
    expect(scrub.max).toBe("4");
    fireEvent.change(scrub, { target: { value: "3" } });
    expect(onChange).toHaveBeenLastCalledWith({ index: 3, playing: false, speed: 1, loop: false });
    fireEvent.change(screen.getByLabelText("Speed"), { target: { value: "4" } });
    expect(onChange).toHaveBeenLastCalledWith({ index: 0, playing: true, speed: 4, loop: false });
    const loop = screen.getByRole("button", { name: "Loop" });
    expect(loop.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(loop);
    expect(onAction).toHaveBeenLastCalledWith("loop");
  });

  it("marks the session gap and the warm-up frame under the scrubber", () => {
    const { container } = render(
      <TransportBar playback={initialPlayback()} nFrames={5} frames={frames} onChange={() => {}} onAction={() => {}} />,
    );
    expect(container.querySelectorAll('[data-mark="gap"]').length).toBe(1);
    expect(container.querySelectorAll('[data-mark="warmup"]').length).toBe(1);
  });

  it("an empty series disables the controls", () => {
    render(<TransportBar playback={initialPlayback()} nFrames={0} frames={[]} onChange={() => {}} onAction={() => {}} />);
    expect((screen.getByRole("button", { name: "Play" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Frame") as HTMLInputElement).disabled).toBe(true);
  });
});
