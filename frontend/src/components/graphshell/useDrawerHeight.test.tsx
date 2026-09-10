// Resizable graph drawer (GRAPH ERGONOMICS rider, 2026-09-10): the tab default
// applies untouched; a drag on the top-edge handle sets the height within the
// clamp and persists it; double-click resets; a stored height is honoured on
// mount. The hook is exercised through a minimal harness — GraphDrawer itself
// only spreads the handle props and applies the height.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { DrawerTab } from "./GraphDrawer";
import {
  DRAWER_HEIGHT_KEY,
  DRAWER_MAX_VH,
  DRAWER_MIN_PX,
  defaultDrawerHeight,
  useDrawerHeight,
} from "./useDrawerHeight";

function Harness({ tab }: { tab: DrawerTab }) {
  const d = useDrawerHeight(tab);
  return (
    <div>
      <div data-testid="handle" {...d.handleProps} />
      <div data-testid="body" style={{ height: d.height }} />
      <span data-testid="dragged">{String(d.dragged)}</span>
    </div>
  );
}

const heightOf = () => (screen.getByTestId("body") as HTMLElement).style.height;
const drag = (fromY: number, toY: number) => {
  fireEvent.mouseDown(screen.getByTestId("handle"), { clientY: fromY, button: 0 });
  fireEvent.mouseMove(window, { clientY: toY });
  fireEvent.mouseUp(window, { clientY: toY });
};

beforeEach(() => localStorage.removeItem(DRAWER_HEIGHT_KEY));
afterEach(cleanup);

describe("useDrawerHeight", () => {
  it("applies the tab default until dragged", () => {
    render(<Harness tab="relations" />);
    expect(heightOf()).toBe(`${defaultDrawerHeight("relations")}px`);
    expect(defaultDrawerHeight("relations")).toBe(256);
    expect(defaultDrawerHeight("preview")).toBe(208);
    expect(screen.getByTestId("dragged").textContent).toBe("false");
    cleanup();
    render(<Harness tab="diagnostics" />);
    expect(heightOf()).toBe("208px");
  });

  it("a drag up makes the drawer taller, is clamped, and is remembered", () => {
    render(<Harness tab="relations" />);
    drag(500, 400); // 100 px up from 256
    expect(heightOf()).toBe("356px");
    expect(screen.getByTestId("dragged").textContent).toBe("true");
    expect(JSON.parse(localStorage.getItem(DRAWER_HEIGHT_KEY) ?? "null")).toBe(356);
    drag(500, 5000); // far below: the minimum
    expect(heightOf()).toBe(`${DRAWER_MIN_PX}px`);
    drag(500, -5000); // far above: the viewport share
    const max = Math.max(DRAWER_MIN_PX, Math.floor(window.innerHeight * DRAWER_MAX_VH));
    expect(heightOf()).toBe(`${max}px`);
    expect(max).toBeGreaterThan(DRAWER_MIN_PX);
  });

  it("double-click resets to the default and forgets the stored height", () => {
    render(<Harness tab="relations" />);
    drag(500, 450);
    expect(heightOf()).toBe("306px");
    fireEvent.doubleClick(screen.getByTestId("handle"));
    expect(heightOf()).toBe("256px");
    expect(localStorage.getItem(DRAWER_HEIGHT_KEY)).toBeNull();
    expect(screen.getByTestId("dragged").textContent).toBe("false");
  });

  it("honours a stored height on mount (clamped) and ignores garbage", () => {
    localStorage.setItem(DRAWER_HEIGHT_KEY, "300");
    render(<Harness tab="preview" />);
    expect(heightOf()).toBe("300px");
    cleanup();
    localStorage.setItem(DRAWER_HEIGHT_KEY, "7"); // below the minimum → clamped
    render(<Harness tab="preview" />);
    expect(heightOf()).toBe(`${DRAWER_MIN_PX}px`);
    cleanup();
    localStorage.setItem(DRAWER_HEIGHT_KEY, "\"nope\"");
    render(<Harness tab="preview" />);
    expect(heightOf()).toBe("208px");
  });

  it("a non-primary button does not start a drag", () => {
    render(<Harness tab="relations" />);
    fireEvent.mouseDown(screen.getByTestId("handle"), { clientY: 500, button: 2 });
    fireEvent.mouseMove(window, { clientY: 300 });
    fireEvent.mouseUp(window, { clientY: 300 });
    expect(heightOf()).toBe("256px");
  });
});
