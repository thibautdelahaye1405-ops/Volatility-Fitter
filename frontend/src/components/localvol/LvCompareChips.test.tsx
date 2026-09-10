// LvCompareChips: the t-interpolation chips toggle the twin's interpolant,
// the v1 tail target is lit and pinned with the riders muted, the mode
// switch is there, and the score strip reads the payload's pooled figures.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LvCompareChips from "./LvCompareChips";
import { lvCompareFixture } from "../../lib/lvCompare.fixture";

afterEach(cleanup);

function renderChips(data = lvCompareFixture(), loading = false, tails: "model" | "hull" | "affine" = "model") {
  const onTInterpChange = vi.fn();
  const onTailsChange = vi.fn();
  const onModeChange = vi.fn();
  render(
    <LvCompareChips
      tInterp="smooth" onTInterpChange={onTInterpChange}
      tails={tails} onTailsChange={onTailsChange}
      mode="sheets" onModeChange={onModeChange}
      data={data} loading={loading}
    />,
  );
  return { onTInterpChange, onTailsChange, onModeChange };
}

const pressed = (name: RegExp) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

describe("LvCompareChips", () => {
  it("lights Smooth and switches to Buckets on click", () => {
    const { onTInterpChange } = renderChips();
    expect(pressed(/^Smooth/)).toBe("true");
    expect(pressed(/^Buckets/)).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: /^Buckets/ }));
    expect(onTInterpChange).toHaveBeenCalledWith("buckets");
  });

  it("lit chips use the Compare grammar (slate for time, teal for tails) and spin only on a hard build", () => {
    const { container } = render(
      <LvCompareChips tInterp="smooth" onTInterpChange={() => {}} tails="model" onTailsChange={() => {}} mode="sheets" onModeChange={() => {}} data={lvCompareFixture()} loading={false} />,
    );
    const smooth = screen.getByRole("button", { name: /^Smooth/ });
    expect(smooth.className).toContain("text-slate-100");
    expect(smooth.className).not.toMatch(/orange/);
    expect(screen.getByRole("button", { name: /Model wings/ }).className).toContain("text-teal-100");
    expect(container.querySelector(".animate-spin")).toBeNull();
    cleanup();
    const spinning = render(
      <LvCompareChips tInterp="smooth" onTInterpChange={() => {}} tails="model" onTailsChange={() => {}} mode="sheets" onModeChange={() => {}} data={lvCompareFixture()} loading />,
    );
    expect(spinning.container.querySelector(".animate-spin")).not.toBeNull();
  });

  it("lights the tail target, switches on click, and keeps Match LQD a muted rider", () => {
    const { onTailsChange } = renderChips();
    const model = screen.getByRole("button", { name: /Model wings/ }) as HTMLButtonElement;
    expect(model.disabled).toBe(false);
    expect(model.getAttribute("aria-pressed")).toBe("true");
    for (const [name, id] of [[/Quoted range/, "hull"], [/Affine wings/, "affine"]] as const) {
      const b = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(b.disabled).toBe(false);
      expect(b.getAttribute("aria-pressed")).toBe("false");
      fireEvent.click(b);
      expect(onTailsChange).toHaveBeenCalledWith(id);
    }
    const rider = screen.getByRole("button", { name: /Match LQD/ }) as HTMLButtonElement;
    expect(rider.disabled).toBe(true);
    expect(rider.textContent).toContain("rider");
    cleanup();
    renderChips(lvCompareFixture(), true, "hull");
    expect(pressed(/Quoted range/)).toBe("true");
    expect(pressed(/Model wings/)).toBe("false");
  });

  it("offers the three display modes and reports a pick", () => {
    const { onModeChange } = renderChips();
    fireEvent.click(screen.getByRole("button", { name: "Difference" }));
    expect(onModeChange).toHaveBeenCalledWith("diff");
    expect(screen.getByRole("button", { name: "Smiles" })).toBeTruthy();
  });

  it("the score strip reads the pooled figures and the repair summary", () => {
    renderChips();
    expect(screen.getByText(/twin 5 · affine conv 52 · param 5 bp/)).toBeTruthy();
    expect(screen.getByText(/round trip 0\.9 · 3\.7 bp · floor 0\.8 · sheet 14/)).toBeTruthy();
    expect(screen.getByText("no repairs")).toBeTruthy();
    expect(screen.queryByText("STALE")).toBeNull();
  });

  it("flags a stale affine sheet and lists the repairs when the extraction touched something", () => {
    renderChips(lvCompareFixture({
      affineStale: true,
      counters: { butterfly: [1, 0, 0], calendar: [0, 0, 0], floored: [1, 0, 0], capped: [0, 0, 2], clean: false },
    }));
    expect(screen.getByText("STALE")).toBeTruthy();
    expect(screen.getByText("butterfly 1 · floored 1 · capped 2")).toBeTruthy();
  });

  it("flags a moved spot with the ANCHOR badge (the comparison stays at the calibration spot)", () => {
    renderChips(lvCompareFixture({ spotShift: 0.012 }));
    const badge = screen.getByText("ANCHOR");
    expect(badge.getAttribute("title")).toContain("1.20%");
    expect(badge.getAttribute("title")).toContain("calibration spot");
  });

  it("shows no strip before the first payload", () => {
    render(
      <LvCompareChips tInterp="buckets" onTInterpChange={() => {}} tails="model" onTailsChange={() => {}} mode="smiles" onModeChange={() => {}} data={null} loading />,
    );
    expect(screen.queryByText(/round trip/)).toBeNull();
    expect(pressed(/^Buckets/)).toBe("true");
  });
});
