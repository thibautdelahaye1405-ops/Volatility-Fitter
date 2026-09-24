// The per-row source select of the Universe dialog: its options may depend on
// the ticker (the "auto" policy pin reads "Auto → Cboe" once the backend
// resolved it), and choosing Auto posts the pin value "auto" through onChange.
// The lit map / expiry-format contexts are mocked.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LitDarkMatrix from "./LitDarkMatrix";
import { AUTO_SOURCE, autoPinLabel } from "../state/tickerSources";
import type { UniverseResponse } from "../state/useSmile";

vi.mock("../state/litMap", () => ({
  useLitMap: () => ({
    nodes: [{ ticker: "SPY", expiry: "2026-12-18", lit: true }],
    error: null,
    toggleNode: vi.fn(),
    setTicker: vi.fn(),
  }),
}));
vi.mock("../state/expiryFormat", () => ({ useExpiryFormat: () => ({ format: "dmy" }) }));

const universe: UniverseResponse = {
  asOf: "2026-09-24",
  tickers: ["SPY", "QQQ"],
  expiries: { SPY: [{ expiry: "2026-12-18", t: 0.23 }], QQQ: [] },
  defaultSource: "massive",
  tickerSources: { SPY: AUTO_SOURCE },
  resolvedSources: { SPY: "cboe", QQQ: "massive" },
};
const labelOf = (id: string) => ({ cboe: "Cboe (delayed)", massive: "Massive" })[id] ?? id;

afterEach(cleanup);

describe("LitDarkMatrix source column", () => {
  it("renders per-ticker options — Auto → Cboe on the auto-pinned row — and posts 'auto'", () => {
    const onChange = vi.fn();
    render(
      <LitDarkMatrix
        universe={universe}
        sourceColumn={{
          label: (t) => universe.tickerSources?.[t] ?? "",
          options: (t) => [
            { id: "", label: "Default (Massive)" },
            {
              id: AUTO_SOURCE,
              label: autoPinLabel(
                universe.tickerSources?.[t] === AUTO_SOURCE ? universe.resolvedSources?.[t] : undefined,
                labelOf,
              ),
            },
            { id: "cboe", label: "Cboe (delayed)" },
          ],
          onChange,
        }}
      />,
    );
    const spy = screen.getByLabelText("SPY data source") as HTMLSelectElement;
    const qqq = screen.getByLabelText("QQQ data source") as HTMLSelectElement;
    expect(spy.value).toBe(AUTO_SOURCE);
    expect(spy.options[spy.selectedIndex].text).toBe("Auto → Cboe (delayed)"); // the pick is never silent
    expect(qqq.value).toBe("");
    expect([...qqq.options].map((o) => o.text)).toContain("Auto (fastest green source)");
    fireEvent.change(qqq, { target: { value: AUTO_SOURCE } });
    expect(onChange).toHaveBeenCalledWith("QQQ", AUTO_SOURCE);
  });

  it("still accepts a plain options list", () => {
    render(
      <LitDarkMatrix
        universe={universe}
        sourceColumn={{ label: () => "", options: [{ id: "", label: "Default" }, { id: "cboe", label: "Cboe" }] }}
      />,
    );
    const spy = screen.getByLabelText("SPY data source") as HTMLSelectElement;
    expect([...spy.options].map((o) => o.value)).toEqual(["", "cboe"]);
  });
});
