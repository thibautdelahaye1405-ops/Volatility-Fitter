// Per-ticker sources: the pure resolution + labels the Nodes pane and the
// market pill rely on (the hook itself is exercised through the dialog).
import { describe, expect, it } from "vitest";
import { AUTO_SOURCE, autoPinLabel, resolveTickerSource, shortSourceLabel, sourceLabel } from "./tickerSources";

describe("resolveTickerSource", () => {
  it("returns the pin when set, else the universe's default source", () => {
    const pins = { SX5E: "bloomberg" };
    expect(resolveTickerSource(pins, "cboe", "SX5E")).toBe("bloomberg");
    expect(resolveTickerSource(pins, "cboe", "SPY")).toBe("cboe");
    expect(resolveTickerSource(undefined, "cboe", "SPY")).toBe("cboe");
  });

  it("reads an auto pin through the backend's resolution, the default until known", () => {
    const pins = { SPY: AUTO_SOURCE, SX5E: "bloomberg" };
    expect(AUTO_SOURCE).toBe("auto");
    expect(resolveTickerSource(pins, "massive", "SPY", { SPY: "cboe" })).toBe("cboe");
    expect(resolveTickerSource(pins, "massive", "SPY")).toBe("massive"); // not resolved yet
    expect(resolveTickerSource(pins, "massive", "SX5E", { SX5E: "cboe" })).toBe("bloomberg"); // a real pin wins
  });
});

describe("autoPinLabel", () => {
  it("names the resolved source — never a silent Auto", () => {
    const labelOf = (id: string) => (id === "cboe" ? "Cboe (delayed)" : id);
    expect(autoPinLabel("cboe", labelOf)).toBe("Auto → Cboe (delayed)");
    expect(autoPinLabel(undefined, labelOf)).toBe("Auto (fastest green source)");
    expect(shortSourceLabel(AUTO_SOURCE)).toBe("AUTO");
    expect(sourceLabel(AUTO_SOURCE)).toBe("Auto");
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
