// Variance swap card sizes (lib/asideSizes): compact = one row with the quote
// (or the model level) that expands the card; standard = readout, editor and
// undo / redo / reset; expanded = penalty, replication and hard-pin rows too.
// Rendered outside the column the card is expanded and carries no toggle.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VarSwapPanel from "./VarSwapPanel";
import type { VarSwapInfo } from "../lib/mockData";

const info = (over: Partial<VarSwapInfo> = {}): VarSwapInfo => ({
  level: 0.185,
  excluded: false,
  modelVol: 0.182,
  enabled: true,
  canUndo: true,
  canRedo: false,
  basisBp: 30,
  weightPct: 20,
  weightAbs: 1.5,
  stale: false,
  rmsShare: 0.1,
  ...over,
});

function renderPanel(over: Partial<Parameters<typeof VarSwapPanel>[0]> = {}) {
  const onToggleSize = vi.fn();
  const utils = render(
    <VarSwapPanel
      info={info()}
      live={false} // no backend round-trip (the hard-pin row needs one)
      onSet={vi.fn()}
      onExclude={vi.fn()}
      onInclude={vi.fn()}
      onRemove={vi.fn()}
      onUndo={vi.fn()}
      onRedo={vi.fn()}
      onReset={vi.fn()}
      onToggleSize={onToggleSize}
      {...over}
    />,
  );
  return { ...utils, onToggleSize };
}

afterEach(cleanup);

describe("VarSwapPanel sizes", () => {
  it("compact: one row with the quote and basis that expands the card", () => {
    const { onToggleSize } = renderPanel({ size: "S" });
    const expand = screen.getByLabelText("Expand Variance swap");
    expect(expand.textContent).toMatch(/quote 18\.50% · \+30 bp/);
    expect(screen.queryByTitle("Var-swap vol (%)")).toBeNull();
    expect(screen.queryByText("Undo")).toBeNull();
    fireEvent.click(expand);
    expect(onToggleSize).toHaveBeenCalledTimes(1);
    cleanup();
    renderPanel({ size: "S", info: info({ level: null, basisBp: null }) });
    expect(screen.getByLabelText("Expand Variance swap").textContent).toMatch(/model 18\.20%/);
    cleanup();
    renderPanel({ size: "S", info: info({ excluded: true }) });
    expect(screen.getByLabelText("Expand Variance swap").textContent).toMatch(/excluded/);
  });

  it("standard: the readout, the level editor and undo / redo / reset — no penalty lines", () => {
    const { onToggleSize } = renderPanel({ size: "M" });
    expect(screen.getByText(/model 18\.20% · quote 18\.50% · basis \+30 bp/)).toBeTruthy();
    expect(screen.getByTitle("Var-swap vol (%)")).toBeTruthy();
    expect(screen.getByText("Exclude")).toBeTruthy();
    expect(screen.getByText("Undo")).toBeTruthy();
    expect(screen.queryByText(/penalty 20% of quote weight/)).toBeNull();
    expect(screen.queryByText(/A penalty pulls the fitted var-swap/)).toBeNull();
    fireEvent.click(screen.getByLabelText("Expand Variance swap"));
    expect(onToggleSize).toHaveBeenCalledTimes(1);
  });

  it("expanded: everything, with the fold-back toggle; no toggle outside the column", () => {
    const { onToggleSize } = renderPanel({ size: "L", subtitle: "Editing 18-Dec-26 · model = LV surface fit" });
    expect(screen.getByText(/penalty 20% of quote weight/)).toBeTruthy();
    expect(screen.getByText(/Editing 18-Dec-26/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Shrink Variance swap"));
    expect(onToggleSize).toHaveBeenCalledTimes(1);
    cleanup();
    renderPanel({ onToggleSize: undefined });
    expect(screen.getByText(/penalty 20% of quote weight/)).toBeTruthy(); // expanded by default
    expect(screen.queryByLabelText("Shrink Variance swap")).toBeNull();
  });

  it("keeps the stale marker beside the title at every size", () => {
    for (const size of ["S", "M", "L"] as const) {
      renderPanel({ size, info: info({ stale: true }) });
      expect(screen.getByText("stale")).toBeTruthy();
      cleanup();
    }
  });
});
