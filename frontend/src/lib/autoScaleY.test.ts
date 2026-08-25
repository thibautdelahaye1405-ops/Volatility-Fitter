import { describe, expect, it } from "vitest";

import {
  AUTOSCALE_STORAGE_KEY,
  DEFAULT_AUTOSCALE,
  autoScaleYWindow,
  isAutoScaleToggles,
  readSmileAutoScale,
  writeSmileAutoScale,
} from "./autoScaleY";

class MemStorage {
  map = new Map<string, string>();
  getItem(k: string) {
    return this.map.has(k) ? this.map.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.map.set(k, v);
  }
}

describe("autoScaleYWindow — the y-fraction policy after an x-view change", () => {
  it("fit snaps any window to the identity {0,1} (the base auto-fit shows through)", () => {
    expect(autoScaleYWindow({ yLo: 0.3, yHi: 0.5 }, { center: false, fit: true })).toEqual({ yLo: 0, yHi: 1 });
    // fit wins over center when both are on
    expect(autoScaleYWindow({ yLo: -0.4, yHi: 1.7 }, { center: true, fit: true })).toEqual({ yLo: 0, yHi: 1 });
  });

  it("fit on an already-identity window is a no-op (null: callers skip the state write)", () => {
    expect(autoScaleYWindow({ yLo: 0, yHi: 1 }, { center: true, fit: true })).toBeNull();
  });

  it("center preserves the span and recenters it on 0.5", () => {
    // zoomed in (span 0.5), sitting low -> same span, centered
    expect(autoScaleYWindow({ yLo: 0, yHi: 0.5 }, { center: true, fit: false })).toEqual({ yLo: 0.25, yHi: 0.75 });
    // zoomed OUT past the base (span 2) -> span kept, centered
    expect(autoScaleYWindow({ yLo: -1.5, yHi: 0.5 }, { center: true, fit: false })).toEqual({ yLo: -0.5, yHi: 1.5 });
  });

  it("center on an already-centered window is a no-op", () => {
    expect(autoScaleYWindow({ yLo: 0.25, yHi: 0.75 }, { center: true, fit: false })).toBeNull();
    expect(autoScaleYWindow({ yLo: 0, yHi: 1 }, { center: true, fit: false })).toBeNull();
  });

  it("both toggles off never rewrites (legacy free-zoom behavior)", () => {
    expect(autoScaleYWindow({ yLo: 0.3, yHi: 0.4 }, { center: false, fit: false })).toBeNull();
    expect(autoScaleYWindow({ yLo: 0, yHi: 1 }, { center: false, fit: false })).toBeNull();
  });
});

describe("smile auto-scale persistence (volfit.smileAutoScale)", () => {
  it("defaults BOTH toggles ON when nothing is stored / storage is unavailable", () => {
    expect(DEFAULT_AUTOSCALE).toEqual({ center: true, fit: true });
    expect(readSmileAutoScale(new MemStorage())).toEqual(DEFAULT_AUTOSCALE);
    expect(readSmileAutoScale(null)).toEqual(DEFAULT_AUTOSCALE);
    expect(() => writeSmileAutoScale({ center: false, fit: true }, null)).not.toThrow();
  });

  it("round-trips the toggles through the storage key", () => {
    const s = new MemStorage();
    writeSmileAutoScale({ center: false, fit: true }, s);
    expect(s.getItem(AUTOSCALE_STORAGE_KEY)).toBe(JSON.stringify({ center: false, fit: true }));
    expect(readSmileAutoScale(s)).toEqual({ center: false, fit: true });
    writeSmileAutoScale({ center: true, fit: false }, s);
    expect(readSmileAutoScale(s)).toEqual({ center: true, fit: false });
  });

  it("falls back to the default on garbage or partial payloads", () => {
    const s = new MemStorage();
    s.setItem(AUTOSCALE_STORAGE_KEY, "not json {");
    expect(readSmileAutoScale(s)).toEqual(DEFAULT_AUTOSCALE);
    s.setItem(AUTOSCALE_STORAGE_KEY, JSON.stringify({ center: true }));
    expect(readSmileAutoScale(s)).toEqual(DEFAULT_AUTOSCALE);
    s.setItem(AUTOSCALE_STORAGE_KEY, JSON.stringify({ center: "yes", fit: 1 }));
    expect(readSmileAutoScale(s)).toEqual(DEFAULT_AUTOSCALE);
    expect(isAutoScaleToggles({ center: true, fit: false })).toBe(true);
    expect(isAutoScaleToggles(null)).toBe(false);
  });
});
