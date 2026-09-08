// LvCompareChips: the t-interpolation chips toggle the twin's interpolant,
// the v1 tail target is lit and pinned with the riders muted, the mode
// switch is there, and the score strip reads the payload's pooled figures.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LvCompareChips from "./LvCompareChips";
import { lvCompareFixture } from "../../lib/lvCompare.fixture";

afterEach(cleanup);

function renderChips(data = lvCompareFixture(), loading = false) {
  const onTInterpChange = vi.fn();
  const onModeChange = vi.fn();
  render(
    <LvCompareChips
      tInterp="smooth" onTInterpChange={onTInterpChange}
      mode="sheets" onModeChange={onModeChange}
      data={data} loading={loading}
    />,
  );
  return { onTInterpChange, onModeChange };
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

  it("pins the v1 tail target lit and disabled, the riders muted and disabled", () => {
    renderChips();
    const model = screen.getByRole("button", { name: /Model wings/ }) as HTMLButtonElement;
    expect(model.disabled).toBe(true);
    expect(model.getAttribute("aria-pressed")).toBe("true");
    expect(model.textContent).toContain("v1");
    for (const name of [/Match LQD/, /Quoted range/, /Affine wings/]) {
      const b = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(b.disabled).toBe(true);
      expect(b.getAttribute("aria-pressed")).toBe("false");
      expect(b.textContent).toContain("rider");
    }
  });

  it("offers the three display modes and reports a pick", () => {
    const { onModeChange } = renderChips();
    fireEvent.click(screen.getByRole("button", { name: "Difference" }));
    expect(onModeChange).toHaveBeenCalledWith("diff");
    expect(screen.getByRole("button", { name: "Smiles" })).toBeTruthy();
  });

  it("the score strip reads the pooled figures and the repair summary", () => {
    renderChips();
    expect(screen.getByText(/conv twin 25 · affine 52 · param 5 bp/)).toBeTruthy();
    expect(screen.getByText(/round trip 24 · 96 bp/)).toBeTruthy();
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

  it("shows no strip before the first payload", () => {
    render(
      <LvCompareChips tInterp="buckets" onTInterpChange={() => {}} mode="smiles" onModeChange={() => {}} data={null} loading />,
    );
    expect(screen.queryByText(/round trip/)).toBeNull();
    expect(pressed(/^Buckets/)).toBe("true");
  });
});
