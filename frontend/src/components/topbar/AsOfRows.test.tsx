// As-of picker contract: every moment is LISTED; one the active source cannot
// serve is dimmed + disabled with its reason (never hidden, never clickable),
// today is Live (its intraday rows disabled with that reason), and a source
// whose history is bid = ask closes is tagged "marks".
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AsOfRows, fmtCaptureTime } from "./AsOfRows";
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
    setCaptured: vi.fn(async () => {}),
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

  it("offers a captured-only day as REPLAYS of its own captures, never as a fetch at any instant", () => {
    const captures = ["2026-08-28T19:32:00", "2026-08-28T14:05:00"];
    const { hook } = renderRows(state({
      intradayCapable: false,
      supportedModes: ["live"],
      days: [{ date: "2026-08-28", isToday: false, hasClose: false, hasCaptures: true, intraday: false, spread: "quotes", reason: null, captures }],
    }));
    // The newest capture IS the day's latest: enabled, labelled with its time.
    const latest = screen.getByText(`Latest capture · ${fmtCaptureTime(captures[0])}`).closest("button") as HTMLButtonElement;
    expect(latest.disabled).toBe(false);
    fireEvent.click(latest);
    expect(hook.setMoment).toHaveBeenCalledWith("2026-08-28", "latest");
    // A fetch at an arbitrary instant is NOT something this source can do.
    for (const n of [15, 60]) {
      const off = screen.getByText(`${n} min before close`).closest("button") as HTMLButtonElement;
      expect(off.disabled).toBe(true);
      expect(off.title).toMatch(/pick a captured snapshot/);
      fireEvent.click(off);
    }
    expect(hook.setMoment).toHaveBeenCalledTimes(1);
    // The other captured instant is its own explicit replay row.
    const rows = screen.getAllByTestId("asof-capture-row");
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain(`Captured · ${fmtCaptureTime(captures[1])}`);
    fireEvent.click(rows[0]);
    expect(hook.setCaptured).toHaveBeenCalledWith("2026-08-28T14:05:00");
    // Close is not served either (a live-only source), with the reason.
    const closeRow = screen.getByText("Close (official)").closest("button") as HTMLButtonElement;
    expect(closeRow.disabled).toBe(true);
    expect(screen.getByTestId("asof-day-2026-08-28").getAttribute("data-empty")).toBe("false");
  });

  it("highlights an explicit captured replay on its day row", () => {
    const captures = ["2026-08-28T19:32:00", "2026-08-28T14:05:00"];
    renderRows(state({
      mode: "captured", ts: "2026-08-28T14:05:00", day: null, moment: null,
      days: [{ date: "2026-08-28", isToday: false, hasClose: false, hasCaptures: true, intraday: false, spread: "quotes", reason: null, captures }],
    }));
    const row = screen.getAllByTestId("asof-capture-row")[0];
    expect(row.textContent).toContain("✓");
  });
});
