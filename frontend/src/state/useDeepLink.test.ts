import { describe, expect, it } from "vitest";
import { parseDeepLink, stripDeepLink } from "./useDeepLink";

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
});

describe("stripDeepLink", () => {
  it("removes only the deep-link params from the address bar", () => {
    window.history.replaceState(null, "", "/?node=SPX|2026-09-18&activity=parametric&keep=1#h");
    stripDeepLink();
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#h");
  });
});
