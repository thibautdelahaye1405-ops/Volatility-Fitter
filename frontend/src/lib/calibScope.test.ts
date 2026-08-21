import { describe, expect, it } from "vitest";

import {
  CALIB_SCOPES,
  DEFAULT_SCOPE,
  SCOPE_LABEL,
  SCOPE_SHORT,
  SCOPE_STORAGE_KEY,
  isCalibScope,
  readCalibScope,
  scopeBadge,
  scopeDetail,
  writeCalibScope,
} from "./calibScope";

class MemStorage {
  map = new Map<string, string>();
  getItem(k: string) {
    return this.map.has(k) ? this.map.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.map.set(k, v);
  }
}

describe("calibScope — the three first-class Calibrate choices", () => {
  it("lists exactly Param+LV / Param only / LV only with labels for face and menu", () => {
    expect(CALIB_SCOPES).toEqual(["both", "parametric", "lv"]);
    expect(SCOPE_LABEL).toEqual({ both: "Parametric + LV", parametric: "Parametric only", lv: "Local-Vol only" });
    expect(SCOPE_SHORT).toEqual({ both: "Param + LV", parametric: "Param only", lv: "LV only" });
    expect(isCalibScope("lv")).toBe(true);
    expect(isCalibScope("svi")).toBe(false);
  });

  it("persists the last chosen scope and falls back to the default on garbage / no storage", () => {
    const s = new MemStorage();
    expect(readCalibScope(s)).toBe(DEFAULT_SCOPE);
    writeCalibScope("lv", s);
    expect(s.getItem(SCOPE_STORAGE_KEY)).toBe("lv");
    expect(readCalibScope(s)).toBe("lv");
    s.setItem(SCOPE_STORAGE_KEY, "nonsense");
    expect(readCalibScope(s)).toBe(DEFAULT_SCOPE);
    expect(readCalibScope(null)).toBe(DEFAULT_SCOPE);
    expect(() => writeCalibScope("both", null)).not.toThrow();
  });

  it("badges the parametric stale count for the parametric scopes and the LV one for LV only", () => {
    expect(scopeBadge("both", 3, 1)).toBe(3);
    expect(scopeBadge("parametric", 3, 1)).toBe(3);
    expect(scopeBadge("lv", 3, 1)).toBe(1);
  });

  it("details mirror the server semantics (LV gate, stale counts)", () => {
    expect(scopeDetail("both", 0, 0, false)).toMatch(/gated off/);
    expect(scopeDetail("both", 2, 0, true)).toBe("2 stale node(s), then LV surfaces");
    expect(scopeDetail("both", 0, 0, true)).toBe("all lit nodes, then LV surfaces");
    expect(scopeDetail("parametric", 2, 5, true)).toMatch(/^2 stale node\(s\)/);
    expect(scopeDetail("parametric", 0, 5, true)).toMatch(/LV left as is/);
    expect(scopeDetail("lv", 9, 2, true)).toBe("2 stale LV surface(s) — no parametric refit");
    expect(scopeDetail("lv", 9, 0, false)).toMatch(/no parametric refit/);
  });
});
