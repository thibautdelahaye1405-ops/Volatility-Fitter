// RangeBrush: the horizontal strike brush and its vertical twin (2026-09-08,
// the maturity window of the 3D surfaces) — handles carry the accessible
// names and orientation, the vertical track reads upward (low at the
// bottom), and a drag on a handle reports the new window.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RangeBrush from "./RangeBrush";

afterEach(cleanup);

function mockRect(el: Element, rect: Partial<DOMRect>) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100, x: 0, y: 0, toJSON: () => ({}),
    ...rect,
  } as DOMRect);
}

describe("RangeBrush", () => {
  it("horizontal by default: strike handles, lo at the left", () => {
    render(<RangeBrush min={0} max={10} value={[2, 8]} onChange={() => {}} format={(v) => v.toFixed(0)} />);
    const [lo, hi] = screen.getAllByRole("slider");
    expect(lo.getAttribute("aria-label")).toBe("Lower strike bound");
    expect(hi.getAttribute("aria-orientation")).toBe("horizontal");
    expect((lo as HTMLElement).style.left).toBe("20%");
    expect((hi as HTMLElement).style.left).toBe("80%");
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("vertical: the low handle sits at the bottom and the labels stack hi over lo", () => {
    const { container } = render(
      <RangeBrush
        min={0} max={10} value={[2, 8]} onChange={() => {}} orientation="vertical"
        format={(v) => `${v.toFixed(0)}y`} ariaLabels={["Lower maturity bound", "Upper maturity bound"]}
      />,
    );
    expect(container.firstElementChild?.getAttribute("data-orientation")).toBe("vertical");
    const [lo, hi] = screen.getAllByRole("slider");
    expect(lo.getAttribute("aria-label")).toBe("Lower maturity bound");
    expect(lo.getAttribute("aria-orientation")).toBe("vertical");
    expect((lo as HTMLElement).style.top).toBe("80%"); // low value near the bottom
    expect((hi as HTMLElement).style.top).toBe("20%");
    const labels = Array.from(container.querySelectorAll("span")).map((s) => s.textContent);
    expect(labels.indexOf("8y")).toBeLessThan(labels.indexOf("2y"));
  });

  it("dragging the vertical low handle upward raises the low bound", () => {
    const onChange = vi.fn();
    render(<RangeBrush min={0} max={10} value={[2, 8]} onChange={onChange} orientation="vertical" />);
    const [lo] = screen.getAllByRole("slider");
    const track = lo.parentElement!;
    mockRect(track, { top: 0, bottom: 100, height: 100 });
    (lo as HTMLElement).setPointerCapture = () => {};
    fireEvent.pointerDown(lo, { pointerId: 1, clientX: 10, clientY: 80 });
    fireEvent.pointerMove(track, { pointerId: 1, clientX: 10, clientY: 50 }); // half way up = 5
    expect(onChange).toHaveBeenLastCalledWith([5, 8]);
    fireEvent.pointerMove(track, { pointerId: 1, clientX: 10, clientY: 0 }); // the top: clamped under hi
    expect(onChange).toHaveBeenLastCalledWith([7.5, 8]);
  });

  it("dragging the horizontal window pans it whole", () => {
    const onChange = vi.fn();
    const { container } = render(<RangeBrush min={0} max={10} value={[2, 4]} onChange={onChange} />);
    const window = container.querySelector(".cursor-grab") as HTMLElement;
    const track = window.parentElement!;
    mockRect(track, { left: 0, right: 100, width: 100 });
    window.setPointerCapture = () => {};
    fireEvent.pointerDown(window, { pointerId: 1, clientX: 30, clientY: 5 });
    fireEvent.pointerMove(track, { pointerId: 1, clientX: 60, clientY: 5 });
    expect(onChange).toHaveBeenLastCalledWith([5, 7]);
  });
});
