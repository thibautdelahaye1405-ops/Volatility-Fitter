// Fit switch of the anchoring axis: the options come from the node's axis
// report (Production + the non-production cells), the control hides when
// there is nothing to draw, a drawn shadow is tagged, and a remembered cell
// the node no longer offers reads Production.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FitAnchoringSwitch from "./FitAnchoringSwitch";
import { getMockAnchoring } from "../../lib/mockData";

afterEach(cleanup);

describe("FitAnchoringSwitch", () => {
  it("renders Production plus the available non-production cells and fires onChange", () => {
    const onChange = vi.fn();
    render(<FitAnchoringSwitch info={getMockAnchoring()} value="production" onChange={onChange} drawn={null} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Production", "Free"]);
    expect(screen.getByText("fit")).toBeTruthy();
    expect(screen.queryByText(/SHADOW/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Free" }));
    expect(onChange).toHaveBeenCalledWith("free");
  });

  it("is hidden when only production is available, and without a report", () => {
    const only = { ...getMockAnchoring(), available: ["prior"] as ("free" | "prior" | "filter")[] };
    const a = render(<FitAnchoringSwitch info={only} value="production" onChange={vi.fn()} />);
    expect(a.container.innerHTML).toBe("");
    cleanup();
    const b = render(<FitAnchoringSwitch info={null} value="free" onChange={vi.fn()} />);
    expect(b.container.innerHTML).toBe("");
  });

  it("tags the drawn shadow, and a cell the node no longer offers reads Production", () => {
    const { container } = render(
      <FitAnchoringSwitch info={getMockAnchoring()} value="filter" onChange={vi.fn()} drawn="free" />,
    );
    const tag = screen.getByText(/SHADOW · free/);
    expect(tag.getAttribute("title")).toMatch(/shadow fit drawn/i);
    expect(container.querySelector("[data-fit-anchoring]")?.getAttribute("data-fit-anchoring")).toBe("production");
  });
});
