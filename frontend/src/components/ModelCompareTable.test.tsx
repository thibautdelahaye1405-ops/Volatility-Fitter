// Compare metrics table: reference rows (eSSVI) sit last, carry the
// "reference" pill and are marked for styling; model rows carry none.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import ModelCompareTable from "./ModelCompareTable";
import { getMockComparison } from "../lib/mockData";

afterEach(cleanup);

describe("ModelCompareTable", () => {
  it("tags the eSSVI row as a reference and keeps it last", () => {
    const data = getMockComparison();
    // Answer out of order on purpose: the table must still put the reference last.
    data.models = [data.models[3], data.models[0], data.models[1], data.models[2]];
    render(<ModelCompareTable data={data} />);
    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows.map((r) => r.getAttribute("data-reference"))).toEqual([null, null, null, "true"]);
    expect(rows[3].textContent).toContain("eSSVI");
    expect(rows[3].textContent).toContain("reference");
    expect(screen.getAllByText("reference").length).toBe(1);
    expect(screen.getByText("reference").getAttribute("title")).toMatch(/never a calibrated/i);
  });

  it("tags a tail-matched row with the constraints it carried", () => {
    const data = getMockComparison();
    data.models = data.models.map((m) =>
      m.model === "svi" ? { ...m, tailMatched: ["varswap", "edge"] as const } : m,
    ) as typeof data.models;
    render(<ModelCompareTable data={data} />);
    const pill = screen.getByText("= var-swap · edge");
    expect(pill.getAttribute("title")).toMatch(/matched to LQD/i);
    expect(screen.getAllByText(/^= /).length).toBe(1); // only the SVI-JW row
  });

  it("shows no pill when only models are compared", () => {
    const data = getMockComparison();
    data.models = data.models.filter((m) => m.model !== "essvi");
    render(<ModelCompareTable data={data} />);
    expect(screen.queryByText("reference")).toBeNull();
    expect(screen.getAllByRole("row").length).toBe(4);
  });
});
