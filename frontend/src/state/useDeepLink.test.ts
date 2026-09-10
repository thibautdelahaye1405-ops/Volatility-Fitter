import { describe, expect, it } from "vitest";
import { parseDeepLink, stripDeepLink } from "./useDeepLink";
import { setPendingSeriesLink, takePendingSeriesLink } from "./seriesDeepLink";

describe("parseDeepLink", () => {
  it("reads a node + activity the connector's Workbench button emits", () => {
    expect(parseDeepLink("?node=SPX%7C2026-09-18&activity=localvol")).toEqual({
      node: { ticker: "SPX", expiry: "2026-09-18" },
      activity: "localvol",
    });
  });
  it("upper-cases the ticker and drops an unknown activity", () => {
    expect(parseDeepLink("?node=spy|2026-07-10&activity=nope")).toEqual({
      node: { ticker: "SPY", expiry: "2026-07-10" },
      activity: undefined,
    });
  });
  it("accepts index spellings and rejects malformed nodes", () => {
    expect(parseDeepLink("?node=SX5E%20Index|2026-12-18")?.node.ticker).toBe("SX5E INDEX");
    expect(parseDeepLink("?node=SPX")).toBeNull();
    expect(parseDeepLink("?node=SPX|18-09-2026")).toBeNull();
    expect(parseDeepLink("")).toBeNull();
    expect(parseDeepLink("?activity=graph")).toBeNull();
  });

  // SERIES ARC S4: `series=<id>&frame=<n>` beside the node.
  it("reads a series id and frame, defaulting the activity to the Series lens", () => {
    expect(parseDeepLink("?node=SPY|2026-12-18&series=ser_2026-09-10_ab12&frame=37")).toEqual({
      node: { ticker: "SPY", expiry: "2026-12-18" },
      activity: "series",
      series: { id: "ser_2026-09-10_ab12", frame: 37 },
    });
  });
  it("keeps an explicit activity, drops a bad frame and a bad series id", () => {
    expect(parseDeepLink("?node=SPY|2026-12-18&series=x1&frame=-2&activity=parametric")).toEqual({
      node: { ticker: "SPY", expiry: "2026-12-18" },
      activity: "parametric",
      series: { id: "x1" },
    });
    expect(parseDeepLink("?node=SPY|2026-12-18&series=%3Cbad%3E&frame=3")?.series).toBeUndefined();
    expect(parseDeepLink("?series=x1&frame=3")).toBeNull(); // a series link still needs its node
  });
});

describe("stripDeepLink", () => {
  it("removes only the deep-link params from the address bar", () => {
    window.history.replaceState(null, "", "/?node=SPX|2026-09-18&activity=parametric&keep=1#h");
    stripDeepLink();
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#h");
  });
  it("strips the series params too", () => {
    window.history.replaceState(null, "", "/?node=SPX|2026-09-18&series=x1&frame=3&keep=1");
    stripDeepLink();
    expect(window.location.search).toBe("?keep=1");
  });
});

describe("pending series link", () => {
  it("is taken once", () => {
    setPendingSeriesLink({ id: "x1", frame: 2 });
    expect(takePendingSeriesLink()).toEqual({ id: "x1", frame: 2 });
    expect(takePendingSeriesLink()).toBeNull();
  });
});
