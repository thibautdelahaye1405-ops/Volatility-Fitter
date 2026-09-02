// Per-ticker sources: the pure resolution + labels the Nodes pane and the
// market pill rely on (the hook itself is exercised through the dialog).
import { describe, expect, it } from "vitest";
import { resolveTickerSource, shortSourceLabel, sourceLabel } from "./tickerSources";

describe("resolveTickerSource", () => {
  it("returns the pin when set, else the universe's default source", () => {
    const pins = { SX5E: "bloomberg" };
    expect(resolveTickerSource(pins, "cboe", "SX5E")).toBe("bloomberg");
    expect(resolveTickerSource(pins, "cboe", "SPY")).toBe("cboe");
    expect(resolveTickerSource(undefined, "cboe", "SPY")).toBe("cboe");
  });
});

describe("source labels", () => {
  it("uses the short badge map and falls back to the first four letters", () => {
    expect(shortSourceLabel("bloomberg")).toBe("BBG");
    expect(shortSourceLabel("massive")).toBe("MSV");
    expect(shortSourceLabel("cboe")).toBe("CBOE");
    expect(shortSourceLabel("someexchange")).toBe("SOME");
    expect(sourceLabel("bloomberg")).toBe("Bloomberg");
    expect(sourceLabel("mystery")).toBe("mystery");
  });
});
