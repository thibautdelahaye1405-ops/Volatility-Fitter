// QuoteLayer markup contract: one PATH per beam (stem + caps) and one for the
// mid tick — never <line>s (in-place x/y attribute mutation of many lines left
// ghost beams in Chrome under live streaming; a path's `d` repaints reliably),
// off-plot culling, the excluded cross, the live flash colour and click-through.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import QuoteLayer from "./QuoteLayer";
import type { QuoteBand } from "../lib/mockData";

const q = (k: number, over: Partial<QuoteBand> = {}): QuoteBand => ({
  k, bid: 0.19, ask: 0.21, mid: 0.20, index: Math.round(k * 100), excluded: false, amended: false,
  strike: 100 * Math.exp(k), targetLo: null, targetHi: null, ...over,
});

function renderLayer(quotes: QuoteBand[], over: Partial<Parameters<typeof QuoteLayer>[0]> = {}) {
  const onQuoteSelect = vi.fn();
  const utils = render(
    <svg>
      <QuoteLayer
        quotes={quotes}
        variant="market"
        toX={(k) => 400 + 1000 * k}
        toY={(v) => 300 - 1000 * v}
        plotW={800}
        fitMode="mid"
        showTarget={false}
        selectedIndex={null}
        onQuoteSelect={onQuoteSelect}
        {...over}
      />
    </svg>,
  );
  return { ...utils, onQuoteSelect, layer: utils.container.querySelector('[data-testid="quote-layer-market"]')! };
}

afterEach(cleanup);

describe("QuoteLayer beams", () => {
  it("draws one beam path + one mid path per quote and no <line>", () => {
    const { layer } = renderLayer([q(-0.1), q(0), q(0.1)]);
    expect(layer.querySelectorAll("line").length).toBe(0);
    const groups = layer.querySelectorAll(":scope > g");
    expect(groups.length).toBe(3);
    const paths = groups[1].querySelectorAll("path");
    expect(paths.length).toBe(2);
    // Stem from bid to ask at x = 400, caps ±3.5 px; mid tick ±2.5 px at the mid.
    expect(paths[0].getAttribute("d")).toBe("M400.00,110.00V90.00M396.50,90.00H403.50M396.50,110.00H403.50");
    expect(paths[1].getAttribute("d")).toBe("M397.50,100.00H402.50");
  });

  it("culls off-plot strikes, crosses excluded ones, flashes ticked strikes", () => {
    const { layer } = renderLayer(
      [q(-2), q(0, { excluded: true }), q(0.05)],
      { flash: new Set([(100 * Math.exp(0.05)).toFixed(4)]) },
    );
    const groups = layer.querySelectorAll(":scope > g");
    expect(groups.length).toBe(2); // k = -2 -> x = -1600: culled
    expect(groups[0].querySelectorAll("path").length).toBe(3); // beam + mid + cross
    expect(groups[0].querySelector("g")?.getAttribute("opacity")).toBe("0.25");
    expect(groups[1].querySelector("path")?.getAttribute("stroke")).toBe("rgb(94 234 212 / 0.95)"); // hot
  });

  it("click-through selects by the calibration index and does not bubble", () => {
    const { layer, onQuoteSelect } = renderLayer([q(0.1), q(0.2, { index: -1 })]);
    const rects = layer.querySelectorAll("rect");
    expect(rects.length).toBe(1); // index -1 has no click target
    fireEvent.click(rects[0]);
    expect(onQuoteSelect).toHaveBeenCalledWith(10);
  });
});
