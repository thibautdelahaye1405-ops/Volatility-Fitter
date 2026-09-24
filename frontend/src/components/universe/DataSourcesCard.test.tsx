// The Data-sources card shows one health line under a streaming source
// (acknowledged · msg/s · last tick), red when the stream is refused / dead,
// and no line under a source without a live book.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DataSourcesCard from "./DataSourcesCard";
import type { DataSourceInfo } from "../../state/useDataSources";

const sources: DataSourceInfo[] = [
  {
    id: "massive", label: "Massive", status: "amber", detail: "delayed feed · streaming 812", active: true, tickers: ["SPY"],
    stream: {
      connected: true, cluster: "delayed", rate: 340, lastMessageAge: 2, lastQuoteAge: 2, reconnects: 0, lastError: null,
      subscribed: 950, acknowledged: 812, refused: 0, overCap: 916, requested: 1866, cap: 950, sessionOpen: true,
      level: "amber", detail: "streaming 812 · 340 msg/s · last 2 s",
    },
  },
  { id: "cboe", label: "Cboe (delayed)", status: "amber", detail: "~15-min delayed", active: false, tickers: [], stream: null },
  {
    id: "bloomberg", label: "Bloomberg", status: "red", detail: "stream refused", active: false, tickers: [],
    stream: {
      connected: true, rate: 0, lastMessageAge: 30, lastQuoteAge: null, reconnects: 2, lastError: "Subscription limit reached",
      subscribed: 400, acknowledged: 200, refused: 200, overCap: 0, requested: 400, cap: 950, sessionOpen: true,
      level: "red", detail: "stream refused",
    },
  },
];

function renderCard() {
  return render(
    <DataSourcesCard
      sources={sources} active="massive" switching={false} switchSource={vi.fn(async () => {})}
      snapshot={null} pins={{}} labelOf={(id) => id} clearPins={() => {}} pinBusy={null}
    />,
  );
}

afterEach(cleanup);

describe("DataSourcesCard", () => {
  it("shows one health line under a streaming source and none under the rest", () => {
    renderCard();
    const line = screen.getByTestId("stream-health-massive");
    expect(line.textContent).toBe("812 acked · 340 msg/s · last tick 2 s · 916 over cap");
    expect(line.title).toContain("812 acked of 950 subscribed (cap 950)");
    expect(screen.queryByTestId("stream-health-cboe")).toBeNull();
  });

  it("draws a refused stream's line in red", () => {
    renderCard();
    const line = screen.getByTestId("stream-health-bloomberg");
    expect(line.textContent).toContain("200 refused");
    expect(line.className).toContain("text-rose-400");
  });
});
