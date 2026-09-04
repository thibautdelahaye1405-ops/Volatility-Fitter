// Compare chip strip: the default chip set is the three calibratable
// families; the reference family (eSSVI) lives behind "+ reference", reads
// as a dashed "ref" chip once revealed, and hiding the group deselects it.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CompareChips, { prevailingModelId } from "./CompareChips";
import type { CompareModelId } from "../../lib/mockData";

afterEach(cleanup);

function renderChips(selected: CompareModelId[] = ["lqd"]) {
  const onToggle = vi.fn();
  render(
    <CompareChips prevailing="lqd" selected={new Set(selected)} onToggle={onToggle} data={null} loading={false} />,
  );
  return { onToggle };
}

const chipNames = () =>
  screen
    .getAllByRole("button")
    .filter((b) => b.hasAttribute("aria-pressed"))
    .map((b) => b.textContent ?? "");

describe("CompareChips", () => {
  it("shows LQD / SVI-JW / MCS by default and no eSSVI chip", () => {
    renderChips();
    const names = chipNames();
    expect(names.some((n) => n.startsWith("LQD"))).toBe(true);
    expect(names.some((n) => n.startsWith("SVI-JW"))).toBe(true);
    expect(names.some((n) => n.startsWith("MCS"))).toBe(true);
    expect(names.some((n) => n.includes("eSSVI"))).toBe(false);
    expect(screen.getByRole("button", { name: /show reference families/i })).toHaveProperty("textContent", "+ reference");
  });

  it("+ reference reveals the eSSVI chip tagged ref; clicking it selects it", () => {
    const { onToggle } = renderChips();
    fireEvent.click(screen.getByRole("button", { name: /show reference families/i }));
    const ref = chipNames().find((n) => n.includes("eSSVI"));
    expect(ref).toBeDefined();
    expect(ref).toContain("ref");
    fireEvent.click(screen.getByRole("button", { name: /^eSSVI/ }));
    expect(onToggle).toHaveBeenCalledWith("essvi");
  });

  it("a remembered eSSVI selection shows its chip without the reveal, and hiding deselects it", () => {
    const { onToggle } = renderChips(["lqd", "essvi"]);
    expect(chipNames().some((n) => n.includes("eSSVI"))).toBe(true);
    const hide = screen.getByRole("button", { name: /hide reference families/i });
    expect(hide.textContent).toBe("− reference");
    fireEvent.click(hide);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith("essvi");
  });

  it("the prevailing chip is disabled and labelled calibrated", () => {
    renderChips();
    const lqd = screen.getByRole("button", { name: /^LQD/ });
    expect((lqd as HTMLButtonElement).disabled).toBe(true);
    expect(lqd.textContent).toContain("calibrated");
  });
});

describe("prevailingModelId", () => {
  it("routes ids and labels onto families, eSSVI before SVI", () => {
    expect(prevailingModelId("svi_jw", "SVI-JW")).toBe("svi");
    expect(prevailingModelId("essvi", undefined)).toBe("essvi");
    expect(prevailingModelId("sigmoid", "Multi-Core Sigmoid")).toBe("sigmoid");
    expect(prevailingModelId(undefined, undefined)).toBe("lqd");
  });
});
