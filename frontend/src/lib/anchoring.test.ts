// Unit tests for the anchoring axis's pure logic (lib/anchoring): the chip
// state (production / unavailable / selected), the shadow-row test and
// table pill, the Pull column text, the row key and the Fit switch options.
import { describe, expect, it } from "vitest";
import { getMockAnchoring } from "./mockData";
import type { AnchoringInfo } from "./mockData";
import {
  ANCHORING_DASH,
  ANCHORING_LABELS,
  ANCHORING_ORDER,
  ANCHORING_SHORT,
  ANCHORING_TITLES,
  anchoringChipState,
  anchoringPill,
  compareRowKey,
  fitSwitchOptions,
  formatPull,
  isShadowRow,
  unavailableHints,
} from "./anchoring";

/** The mock node: free + prior exist, production coincides with prior,
 *  the filter cell is missing with a reason. */
const info = (): AnchoringInfo => getMockAnchoring();

describe("constants", () => {
  it("names every cell in wire order with a label, a short name, a title and a dash", () => {
    expect(ANCHORING_ORDER).toEqual(["free", "prior", "filter"]);
    for (const c of ANCHORING_ORDER) {
      expect(ANCHORING_LABELS[c]).toBeTruthy();
      expect(ANCHORING_SHORT[c]).toBeTruthy();
      expect(ANCHORING_TITLES[c].length).toBeGreaterThan(40);
      expect(ANCHORING_DASH[c]).toMatch(/^\d+( \d+)+$/);
    }
    expect(ANCHORING_LABELS.prior).toBe("+ Prior");
    expect(ANCHORING_SHORT.filter).toBe("+filter");
  });
});

describe("anchoringChipState", () => {
  it("lights and tags the production cell whatever the selection", () => {
    const s = anchoringChipState("prior", new Set(), info());
    expect(s).toMatchObject({ on: true, production: true, available: true });
    expect(s.title).toMatch(/production fit — the prevailing row/i);
  });

  it("an unavailable cell is off and carries the node's reason, even when remembered as selected", () => {
    const s = anchoringChipState("filter", new Set(["filter"]), info());
    expect(s).toMatchObject({ on: false, production: false, available: false, preview: null });
    expect(s.title).toContain("filter is off");
  });

  it("a preview cell carries the backend's remark; production and missing cells never do", () => {
    const saved: AnchoringInfo = {
      ...info(), production: "free",
      preview: { prior: "no fetched prior — reads the latest saved snapshot" },
    };
    const s = anchoringChipState("prior", new Set(), saved);
    expect(s).toMatchObject({ on: false, available: true, production: false });
    expect(s.preview).toContain("saved snapshot");
    expect(s.title).toMatch(/Preview: no fetched prior/);
    expect(anchoringChipState("free", new Set(), saved).preview).toBeNull();
    expect(anchoringChipState("prior", new Set(), { ...saved, production: "prior" }).preview).toBeNull();
  });

  it("unavailableHints names each missing cell with its reason, in wire order", () => {
    expect(unavailableHints(info())).toEqual(["+ Filter: filter is off — Options ▸ Observation filter ▸ Overlay, then Calibrate"]);
    expect(unavailableHints({ ...info(), available: ["free"], notes: {} })).toEqual([
      "+ Prior: unavailable on this node", "+ Filter: unavailable on this node",
    ]);
    expect(unavailableHints(null)).toEqual([]);
  });

  it("a selected available cell is on; without a report every cell is assumed available", () => {
    expect(anchoringChipState("free", new Set(["free"]), info())).toMatchObject({ on: true, available: true, production: false });
    expect(anchoringChipState("free", new Set(), info()).on).toBe(false);
    expect(anchoringChipState("filter", new Set(), null)).toMatchObject({ on: false, available: true });
    expect(anchoringChipState("filter", new Set(["filter"]), undefined).on).toBe(true);
  });
});

describe("rows", () => {
  it("a shadow row carries a cell other than production", () => {
    expect(isShadowRow({ anchoring: "free" }, info())).toBe(true);
    expect(isShadowRow({ anchoring: "prior" }, info())).toBe(false); // the plain row names production
    expect(isShadowRow({ anchoring: null }, info())).toBe(false);
    expect(isShadowRow({}, info())).toBe(false);
    expect(isShadowRow({ anchoring: "prior" }, null)).toBe(true); // no report ⇒ nothing is production
  });

  it("pills: 'prod' on the production row, the short name on a shadow, none elsewhere", () => {
    const prod = anchoringPill({ anchoring: "prior" }, info());
    expect(prod?.label).toBe("prod");
    expect(prod?.title).toContain("+ Prior");
    const free = anchoringPill({ anchoring: "free" }, info());
    expect(free?.label).toBe("free");
    expect(free?.title).toMatch(/shadow/i);
    expect(anchoringPill({ anchoring: null }, info())).toBeNull();
    expect(anchoringPill({}, info())).toBeNull();
  });

  it("keys a family's plain row and its shadow rows apart", () => {
    expect(compareRowKey({ model: "lqd", anchoring: "free" })).toBe("lqd:free");
    expect(compareRowKey({ model: "svi", anchoring: null })).toBe("svi:plain");
    expect(compareRowKey({ model: "essvi" })).toBe("essvi:plain");
  });
});

describe("formatPull", () => {
  it("signed one-decimal ATM bp with skew and curve RMS in the hover", () => {
    const p = formatPull({ pullAtmBp: 12.34, pullSkew: -0.0041, pullCurveBp: 9.66 });
    expect(p.text).toBe("+12.3");
    expect(p.title).toContain("ATM +12.3 bp");
    expect(p.title).toContain("skew -0.004");
    expect(p.title).toContain("curve RMS 9.7 bp");
    expect(formatPull({ pullAtmBp: -4, pullSkew: 0, pullCurveBp: 0 }).text).toBe("-4.0");
    expect(formatPull({ pullAtmBp: 0, pullSkew: 0, pullCurveBp: 0 }).text).toBe("0.0"); // the free row
  });

  it("em-dashes a row without pulls", () => {
    expect(formatPull({}).text).toBe("—");
    expect(formatPull({ pullAtmBp: null }).title).toMatch(/no pull measured/i);
    expect(formatPull({ pullAtmBp: Number.NaN }).text).toBe("—");
  });
});

describe("fitSwitchOptions", () => {
  it("Production first, then every available cell that is not production", () => {
    expect(fitSwitchOptions(info())).toEqual([
      { id: "production", label: "Production" },
      { id: "free", label: "Free" },
    ]);
    expect(fitSwitchOptions(null)).toEqual([{ id: "production", label: "Production" }]);
    const all: AnchoringInfo = { ...info(), available: ["free", "prior", "filter"], production: null };
    expect(fitSwitchOptions(all).map((o) => o.id)).toEqual(["production", "free", "prior", "filter"]);
    expect(fitSwitchOptions({ ...all, production: "free" }).map((o) => o.id)).toEqual(["production", "prior", "filter"]);
  });
});
