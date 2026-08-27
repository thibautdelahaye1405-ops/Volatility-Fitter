// LocalVolTarget contract (V3.4 rider): the LV smile's fit-target overlay
// mirrors QuoteLayer — haircut ribbon from targetLo/Hi in "haircut" mode, the
// faint bid-ask ribbon + mid polyline in every mode, nothing at all when the
// chip is off; the chip state defaults ON and persists in localStorage.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  LV_SHOW_TARGET_KEY,
  LocalVolTargetChip,
  LocalVolTargetLayer,
  useLvShowTarget,
} from "./LocalVolTarget";
import type { QuoteBand } from "../state/useAffine";
import type { FitMode } from "../state/useSmile";

const q = (k: number, over: Partial<QuoteBand> = {}): QuoteBand => ({
  k, bid: 0.19, ask: 0.21, mid: 0.20, index: Math.round(k * 100), excluded: false, amended: false,
  targetLo: null, targetHi: null, ...over,
});
const haircut = (k: number, over: Partial<QuoteBand> = {}): QuoteBand =>
  q(k, { targetLo: 0.195, targetHi: 0.205, ...over });

// Pixel maps of the QuoteLayer test: x = 400 + 1000k, y = 300 - 1000σ.
const toX = (k: number) => 400 + 1000 * k;
const toY = (v: number) => 300 - 1000 * v;

function renderLayer(quotes: QuoteBand[], fitMode: FitMode, show = true) {
  const { container } = render(
    <svg>
      <LocalVolTargetLayer quotes={quotes} fitMode={fitMode} show={show} toX={toX} toY={toY} />
    </svg>,
  );
  const d = (id: string) => container.querySelector(`[data-testid="${id}"]`)?.getAttribute("d") ?? null;
  return { container, d };
}

afterEach(cleanup);

describe("LocalVolTargetLayer", () => {
  it("draws the haircut ribbon from targetLo/Hi in haircut mode (plus context)", () => {
    const { d } = renderLayer([haircut(-0.1), haircut(0), haircut(0.1)], "haircut");
    // Forward along hi (σ = 0.205 -> y = 95), back along lo (0.195 -> 105), closed.
    expect(d("lv-target-haircut")).toBe(
      "M300.00,95.00L400.00,95.00L500.00,95.00L500.00,105.00L400.00,105.00L300.00,105.00Z",
    );
    // The faint bid-ask ribbon and the mid polyline ride along (QuoteLayer rule).
    expect(d("lv-target-bidask")).toBe(
      "M300.00,90.00L400.00,90.00L500.00,90.00L500.00,110.00L400.00,110.00L300.00,110.00Z",
    );
    expect(d("lv-target-mid")).toBe("M300.00,100.00L400.00,100.00L500.00,100.00");
  });

  it("leaves a gap at an excluded strike", () => {
    const { d } = renderLayer(
      [haircut(-0.2), haircut(-0.1), haircut(0, { excluded: true }), haircut(0.1), haircut(0.2)],
      "haircut",
    );
    expect(d("lv-target-haircut")?.split("Z").filter((s) => s !== "").length).toBe(2);
  });

  it("draws the mid polyline (no haircut ribbon) in mid mode", () => {
    const { d } = renderLayer([q(-0.1), q(0), q(0.1)], "mid");
    expect(d("lv-target-mid")).toBe("M300.00,100.00L400.00,100.00L500.00,100.00");
    expect(d("lv-target-haircut")).toBeNull();
  });

  it("does not double-paint the raw band in bid-ask mode", () => {
    const quotes = [q(-0.1, { targetLo: 0.19, targetHi: 0.21 }), q(0, { targetLo: 0.19, targetHi: 0.21 })];
    const { d } = renderLayer(quotes, "bidask");
    expect(d("lv-target-bidask")).not.toBeNull();
    expect(d("lv-target-haircut")).toBeNull();
  });

  it("renders nothing when the chip is off", () => {
    const { container } = renderLayer([haircut(-0.1), haircut(0), haircut(0.1)], "haircut", false);
    expect(container.querySelector('[data-testid="lv-target-layer"]')).toBeNull();
    expect(container.querySelectorAll("path").length).toBe(0);
  });
});

function Harness() {
  const [on, setOn] = useLvShowTarget();
  return <LocalVolTargetChip on={on} fitMode="haircut" onToggle={setOn} />;
}

describe("Target chip + useLvShowTarget", () => {
  beforeEach(() => window.localStorage.removeItem(LV_SHOW_TARGET_KEY));

  it("defaults ON, toggles, and persists under volfit.lvShowTarget", () => {
    const { getByTestId } = render(<Harness />);
    const chip = getByTestId("lv-target-chip");
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(chip.textContent).toContain("haircut");
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    expect(window.localStorage.getItem(LV_SHOW_TARGET_KEY)).toBe("0");
    fireEvent.click(chip);
    expect(window.localStorage.getItem(LV_SHOW_TARGET_KEY)).toBe("1");
  });

  it("reads a stored OFF back on mount", () => {
    window.localStorage.setItem(LV_SHOW_TARGET_KEY, "0");
    const { getByTestId } = render(<Harness />);
    expect(getByTestId("lv-target-chip").getAttribute("aria-pressed")).toBe("false");
  });
});
