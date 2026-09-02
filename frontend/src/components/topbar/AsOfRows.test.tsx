// As-of picker contract: every moment is LISTED; one the active source cannot
// serve is dimmed + disabled with its reason (never hidden, never clickable),
// today is Live (its intraday rows disabled with that reason), and a source
// whose history is bid = ask closes is tagged "marks".
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AsOfRows } from "./AsOfRows";
import type { AsOfState, UseAsOfResult } from "../../state/useAsOf";

const state = (over: Partial<AsOfState> = {}): AsOfState => ({
  mode: "live",
  on: null,
  ts: null,
  day: null,
  moment: null,
  offset: null,
  supportedModes: ["live", "prev_close", "eod"],
  intradayCapable: true,
  closeOffsets: [15, 60],
  days: [
    { date: "2026-09-02", isToday: true, hasClose: false, hasCaptures: false, intraday: false, spread: "marks", reason: "today is Live — pick Live" },
    { date: "2026-09-01", isToday: false, hasClose: true, hasCaptures: false, intraday: true, spread: "marks", reason: null },
  ],
  ...over,
});

function renderRows(asof: AsOfState) {
  const hook: UseAsOfResult = {
    asof,
    busy: false,
    setLive: vi.fn(async () => {}),
    setPrevClose: vi.fn(async () => {}),
    setMoment: vi.fn(async () => {}),
  } as unknown as UseAsOfResult;
  const utils = render(<AsOfRows asof={hook} />);
  return { ...utils, hook };
}

afterEach(cleanup);

describe("AsOfRows", () => {
  it("lists every moment and disables what the source cannot serve, with the reason", () => {
    const { hook } = renderRows(state());
    // Today expands first (no selection): its rows exist but are disabled.
    const closeRow = screen.getByText("Close (official)").closest("button") as HTMLButtonElement;
    expect(closeRow.disabled).toBe(true);
    expect(closeRow.title).toMatch(/no close yet/);
    const latest = screen.getByText("Latest snapshot").closest("button") as HTMLButtonElement;
    expect(latest.disabled).toBe(true);
    expect(latest.title).toMatch(/today's latest is Live/);
    fireEvent.click(latest);
    expect(hook.setMoment).not.toHaveBeenCalled();
    // The day row carries the reason and the marks tag is not shown for an empty day.
    expect(screen.getByTestId("asof-day-2026-09-02").getAttribute("data-empty")).toBe("true");
  });

  it("enables the served moments of a past day and tags a marks-only history", () => {
    const { hook } = renderRows(state());
    fireEvent.click(screen.getByText(/Tue 1 Sep/));
    const closeRow = screen.getByText("Close (official)").closest("button") as HTMLButtonElement;
    expect(closeRow.disabled).toBe(false);
    fireEvent.click(closeRow);
    expect(hook.setMoment).toHaveBeenCalledWith("2026-09-01", "close");
    const off = screen.getByText("60 min before close").closest("button") as HTMLButtonElement;
    expect(off.disabled).toBe(false);
    fireEvent.click(off);
    expect(hook.setMoment).toHaveBeenCalledWith("2026-09-01", "before_close", 60);
    expect(screen.getAllByText("marks").length).toBe(1); // the past day only
  });

  it("disables intraday moments on a past day the source cannot reconstruct", () => {
    renderRows(state({
      days: [{ date: "2026-08-31", isToday: false, hasClose: true, hasCaptures: false, intraday: false, spread: "quotes", reason: null }],
    }));
    const latest = screen.getByText("Latest snapshot").closest("button") as HTMLButtonElement;
    expect(latest.disabled).toBe(true);
    expect(latest.title).toMatch(/cannot fetch an intraday moment/);
    expect(screen.queryByText("marks")).toBeNull();
  });
});
