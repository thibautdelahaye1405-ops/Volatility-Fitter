// The shared slider (GRAPH ERGONOMICS ARC, E4): linear and log scales map
// the range position to the value, the readout formats, the reference mark
// and the reset affordance render.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Slider, { fromPosition, toPosition } from "./Slider";

afterEach(cleanup);

describe("Slider", () => {
  it("maps positions on a log scale", () => {
    expect(toPosition(100, true)).toBeCloseTo(2, 12);
    expect(fromPosition(-1, true)).toBeCloseTo(0.1, 12);
    expect(toPosition(3, false)).toBe(3);
  });

  it("emits values, formats the readout, resets", () => {
    const onChange = vi.fn();
    const onReset = vi.fn();
    render(
      <Slider label="β" value={1} min={0.1} max={10} log format={(v) => `${v.toFixed(1)}x`} onChange={onChange} mark={1} onReset={onReset} testId="s" />,
    );
    expect(screen.getByTestId("s-readout").textContent).toBe("1.0x");
    const input = screen.getByTestId("s") as HTMLInputElement;
    expect(Number(input.min)).toBeCloseTo(-1, 12);
    expect(Number(input.max)).toBeCloseTo(1, 12);
    fireEvent.change(input, { target: { value: "0.5" } });
    expect(onChange).toHaveBeenCalledWith(10 ** 0.5);
    fireEvent.click(screen.getByTitle("Reset"));
    expect(onReset).toHaveBeenCalled();
  });
});
