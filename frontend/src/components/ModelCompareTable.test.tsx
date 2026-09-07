// Compare metrics table: reference rows (eSSVI) sit last, carry the
// "reference" pill and are marked for styling; model rows carry none.
// Anchoring rows: the production row is tagged "prod", a shadow row sits
// under its family with its cell's pill, and the Pull column reads bp.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import ModelCompareTable from "./ModelCompareTable";
import { getMockComparison } from "../lib/mockData";
import type { CompareModelFit } from "../lib/mockData";

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

  it("tags the production row prod, a shadow row with its cell, and fills the Pull column", () => {
    const data = getMockComparison(); // production coincides with the prior cell
    const lqd: CompareModelFit = { ...data.models[0], pullAtmBp: 11.2, pullSkew: -0.004, pullCurveBp: 9.7 };
    const free: CompareModelFit = { ...lqd, anchoring: "free", pullAtmBp: 0, pullSkew: 0, pullCurveBp: 0 };
    data.models = [lqd, data.models[1], free]; // the shadow row is appended after the families
    render(<ModelCompareTable data={data} />);
    expect(screen.getByText("Pull").getAttribute("title")).toMatch(/free fit/i);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-shadow"))).toEqual([null, "free", null]); // grouped under LQD
    expect(rows[0].textContent).toContain("prod");
    expect(screen.getByText("prod").getAttribute("title")).toMatch(/\+ Prior/);
    expect(screen.getByText("free").getAttribute("title")).toMatch(/shadow/i);
    expect(screen.getByText("+11.2").getAttribute("title")).toMatch(/skew -0\.004/);
    expect(rows[1].textContent).toContain("0.0");
    expect(screen.getAllByTitle(/no pull measured/i).length).toBe(1); // the SVI-JW row
  });

  it("shows the prod pill alone when no cell was requested", () => {
    render(<ModelCompareTable data={getMockComparison()} />);
    expect(screen.getAllByText("prod").length).toBe(1);
    expect(screen.queryByText("free")).toBeNull();
    expect(screen.getAllByTitle(/no pull measured/i).length).toBe(4);
  });
});
