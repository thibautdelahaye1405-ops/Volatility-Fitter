// Stream-health formatting (the market pill's tooltip lines and the Data
// sources card's one-liner) off the backend StreamHealth block.
import { describe, expect, it } from "vitest";
import { fmtAge, streamHealthLine, streamHealthLines, type StreamHealth } from "./useDataSources";

const health = (over: Partial<StreamHealth> = {}): StreamHealth => ({
  connected: true,
  cluster: "delayed",
  rate: 340.4,
  lastMessageAge: 2.0,
  lastQuoteAge: 2.2,
  reconnects: 0,
  lastError: null,
  subscribed: 950,
  acknowledged: 812,
  refused: 0,
  overCap: 916,
  requested: 1866,
  cap: 950,
  sessionOpen: true,
  level: "amber",
  detail: "streaming 812 · 340 msg/s · last 2 s",
  ...over,
});

describe("stream health formatting", () => {
  it("formats ages", () => {
    expect(fmtAge(2.4)).toBe("2 s");
    expect(fmtAge(150)).toBe("3 min");
    expect(fmtAge(7200)).toBe("2.0 h");
    expect(fmtAge(null)).toBe("—");
  });

  it("writes the card's one-liner with refusals and over-cap appended", () => {
    expect(streamHealthLine(health())).toBe("812 acked · 340 msg/s · last tick 2 s · 916 over cap");
    expect(streamHealthLine(health({ refused: 5, overCap: 0 }))).toBe("812 acked · 340 msg/s · last tick 2 s · 5 refused");
  });

  it("lists the tooltip lines: subscription, flow, then errors only when there are any", () => {
    const lines = streamHealthLines(health());
    expect(lines).toEqual([
      "812 acked of 950 subscribed (cap 950) · 916 over cap",
      "340 msg/s · last tick 2 s · delayed cluster",
    ]);
    const closed = streamHealthLines(health({ sessionOpen: false, reconnects: 3, lastError: "Subscription limit reached", refused: 12 }));
    expect(closed[0]).toContain("12 refused");
    expect(closed[1]).toContain("session closed");
    expect(closed[2]).toBe("3 reconnects · last error: Subscription limit reached");
  });
});
