// The Weights strip's readout as the smile chart's crosshair badge
// (2026-09-10): the chart hands the strip its crosshair k through the footer
// context; the bar pair under it lights up and its readout (k, target, the
// density multiplier, the weight) is drawn as the crosshair badge on the
// strip. No crosshair, or none within a few px of a bar, no badge. jsdom has
// no ResizeObserver, so the measuring hook and the weights fetch are mocked.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SmileData } from "../lib/mockData";
import type { WeightsData } from "../lib/weightStrip";
import WeightStrip, { weightReadout } from "./WeightStrip";
import { buildWeightBars } from "../lib/weightStrip";

// A measured 400 × 50 strip: plot width 400 − 52 − 14 = 334 px.
vi.mock("../lib/useElementSize", () => ({
  useElementSize: () => ({ ref: { current: null }, size: { width: 400, height: 50 } }),
}));

const WEIGHTS: WeightsData = {
  ticker: "SPY", expiry: "2026-10-16", scheme: "equal", maxMult: 10, meanNormalized: true,
  entries: [
    { index: 0, k: -0.1, spacing: 0.1, weightRaw: 1, weight: 0.8, excluded: false },
    { index: 1, k: 0.0, spacing: 0.1, weightRaw: 1, weight: 1.2, excluded: false },
    { index: 2, k: 0.1, spacing: 0.1, weightRaw: 1, weight: 1.0, excluded: false },
    { index: 3, k: 0.15, spacing: 0, weightRaw: 0, weight: 0, excluded: true },
  ],
};
vi.mock("../state/useWeights", () => ({ useWeights: () => WEIGHTS }));

const smile = { quotes: [{}, {}, {}, {}] } as unknown as SmileData;

/** The strip on an identity axis over k ∈ [−0.2, 0.2]: bars land at x =
 *  (k + 0.2) / 0.4 × 334 → 83.5, 167, 250.5 and 292.25 px. */
function mount(crosshairK: number | null | undefined) {
  render(
    <WeightStrip live ticker="SPY" expiry="2026-10-16" fitMode="mid" smile={smile}
      xView={[-0.2, 0.2]} tx={(k) => k} crosshairK={crosshairK} />,
  );
}

afterEach(cleanup);

describe("WeightStrip · crosshair badge", () => {
  it("badges the bar pair under the crosshair and lights it", () => {
    mount(0.001); // 167.8 px: 0.8 px from the k = 0 pair
    const badge = screen.getByTestId("weight-strip-badge");
    expect(badge.textContent).toBe("k 0.000 · target 1.000 · ×1.00 spacing · weight 1.20");
    const lit = document.querySelector('[data-active="true"]');
    expect(lit?.getAttribute("data-quote-index")).toBe("1");
    expect(document.querySelectorAll('[data-active="true"]').length).toBe(1);
  });

  it("shows nothing without a crosshair, or when no bar is within reach", () => {
    mount(null);
    expect(screen.queryByTestId("weight-strip-badge")).toBeNull();
    expect(document.querySelector('[data-active="true"]')).toBeNull();
    cleanup();
    mount(0.05); // 208.75 px: 41 px from either neighbour
    expect(screen.queryByTestId("weight-strip-badge")).toBeNull();
    cleanup();
    mount(undefined); // an older footer with no crosshair field
    expect(screen.queryByTestId("weight-strip-badge")).toBeNull();
  });

  it("reads an excluded quote as excluded, and keeps the native titles as the fallback", () => {
    mount(0.15); // the hollow outline at 292.25 px
    expect(screen.getByTestId("weight-strip-badge").textContent).toBe("k 0.150 · excluded");
    const titles = Array.from(document.querySelectorAll("title")).map((t) => t.textContent);
    expect(titles).toContain("k 0.000 · target 1.000 · ×1.00 spacing · weight 1.20");
    expect(titles).toContain("k 0.150 · excluded");
    // The badge text is the bar's own readout, the same function the titles use.
    const bars = buildWeightBars(WEIGHTS.entries, { scheme: "equal", maxMult: 10 });
    expect(weightReadout(bars[1])).toBe("k 0.000 · target 1.000 · ×1.00 spacing · weight 1.20");
  });
});
