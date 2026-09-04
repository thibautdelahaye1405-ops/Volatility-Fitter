// The right-hand column's sizing contract: one shared focus, the expanded
// card compresses the other two to compact, no focus = all standard; a focus
// on a gated-off card reads as none; the preference round-trips storage.
import { describe, expect, it } from "vitest";
import {
  ASIDE_FOCUS_STORAGE_KEY,
  ASIDE_PANELS,
  asideCardShrinks,
  asideSizeOf,
  effectiveAsideFocus,
  readAsideFocus,
  toggleAsideFocus,
  writeAsideFocus,
} from "./asideSizes";

describe("aside sizes", () => {
  it("gives every card the standard size when nothing is expanded", () => {
    for (const p of ASIDE_PANELS) expect(asideSizeOf(null, p)).toBe("M");
  });

  it("expands the focused card and compresses the other two", () => {
    expect(asideSizeOf("varswap", "varswap")).toBe("L");
    expect(asideSizeOf("varswap", "spot")).toBe("S");
    expect(asideSizeOf("varswap", "diag")).toBe("S");
  });

  it("toggles: expand a card, move the focus to another, fold back to standard", () => {
    expect(toggleAsideFocus(null, "spot")).toBe("spot");
    expect(toggleAsideFocus("spot", "diag")).toBe("diag");
    expect(toggleAsideFocus("diag", "diag")).toBeNull();
  });

  it("ignores a focus on a card that is not rendered", () => {
    expect(effectiveAsideFocus("varswap", ["spot", "diag"])).toBeNull();
    expect(effectiveAsideFocus("varswap", ASIDE_PANELS)).toBe("varswap");
    expect(effectiveAsideFocus(null, ASIDE_PANELS)).toBeNull();
  });

  it("lets the expanded card and the standard diagnostics card give up height", () => {
    expect(asideCardShrinks("L", "spot")).toBe(true);
    expect(asideCardShrinks("M", "diag")).toBe(true);
    expect(asideCardShrinks("M", "spot")).toBe(false);
    expect(asideCardShrinks("S", "diag")).toBe(false);
  });

  it("round-trips the preference through storage and tolerates garbage", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    };
    expect(readAsideFocus(storage)).toBeNull();
    writeAsideFocus("diag", storage);
    expect(store.get(ASIDE_FOCUS_STORAGE_KEY)).toBe("diag");
    expect(readAsideFocus(storage)).toBe("diag");
    writeAsideFocus(null, storage);
    expect(store.has(ASIDE_FOCUS_STORAGE_KEY)).toBe(false);
    store.set(ASIDE_FOCUS_STORAGE_KEY, "everything");
    expect(readAsideFocus(storage)).toBeNull();
    expect(readAsideFocus(null)).toBeNull();
  });
});
