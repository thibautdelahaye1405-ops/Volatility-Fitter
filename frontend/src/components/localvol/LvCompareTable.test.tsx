// LvCompareTable: one row per expiry with the three surfaces' bp columns and
// the round trip; the selected row is marked; clicking a row selects its
// expiry; a missing affine score reads as dashes.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LvCompareTable from "./LvCompareTable";
import { lvCompareFixture } from "../../lib/lvCompare.fixture";

afterEach(cleanup);

const fmt = (iso: string) => iso;

describe("LvCompareTable", () => {
  it("renders one row per expiry with the bp columns", () => {
    render(
      <LvCompareTable data={lvCompareFixture()} selectedExpiry="2026-12-10" onSelectExpiry={() => {}} formatExpiry={fmt} />,
    );
    const rows = screen.getAllByRole("row").filter((r) => r.hasAttribute("data-selected") || r.textContent?.startsWith("2026"));
    expect(rows).toHaveLength(2);
    const first = rows[0];
    const cells = Array.from(first.querySelectorAll("td")).map((td) => td.textContent);
    // Expiry · parametric rms/max · twin rms/conv/max · affine rms/conv/max · round trip rms/max
    expect(cells).toEqual(["2026-07-10", "5", "12", "25", "18", "60", "1", "40", "3", "30", "90"]);
    expect(rows[1].getAttribute("data-selected")).toBe("true");
    expect(first.getAttribute("data-selected")).toBeNull();
  });

  it("clicking a row selects its expiry", () => {
    const onSelectExpiry = vi.fn();
    render(
      <LvCompareTable data={lvCompareFixture()} selectedExpiry={null} onSelectExpiry={onSelectExpiry} formatExpiry={fmt} />,
    );
    fireEvent.click(screen.getByText("2026-12-10"));
    expect(onSelectExpiry).toHaveBeenCalledWith("2026-12-10");
  });

  it("dashes the affine columns when the LV fit has no score for the expiry", () => {
    const c = lvCompareFixture();
    c.smiles[0] = { ...c.smiles[0], affineScore: null };
    render(<LvCompareTable data={c} selectedExpiry={null} onSelectExpiry={() => {}} formatExpiry={fmt} />);
    const first = screen.getByText("2026-07-10").closest("tr")!;
    const cells = Array.from(first.querySelectorAll("td")).map((td) => td.textContent);
    expect(cells.slice(6, 9)).toEqual(["—", "—", "—"]);
  });
});
