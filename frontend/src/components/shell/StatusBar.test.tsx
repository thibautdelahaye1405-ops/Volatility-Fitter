// Status-bar gauge helpers: the elapsed-time caption drawn next to a running
// step and against the client timeout of a Fetch / Calibrate action.
import { describe, expect, it } from "vitest";
import { formatElapsed } from "./StatusBar";

describe("formatElapsed", () => {
  it("reads seconds under a minute, then minutes and zero-padded seconds", () => {
    expect(formatElapsed(0)).toBe("0 s");
    expect(formatElapsed(12_400)).toBe("12 s");
    expect(formatElapsed(59_999)).toBe("59 s");
    expect(formatElapsed(65_000)).toBe("1m 05s");
    expect(formatElapsed(600_000)).toBe("10m 00s");
    expect(formatElapsed(-5)).toBe("0 s");
  });
});
