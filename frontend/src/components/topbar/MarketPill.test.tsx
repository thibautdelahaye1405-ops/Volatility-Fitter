// The market pill's tooltip carries the active source's stream-health lines
// while it streams, and nothing of the kind when it does not.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MarketPill from "./MarketPill";
import { NodeScopeContext } from "../../state/smileSession";
import type { DataSourceInfo, UseDataSourcesResult } from "../../state/useDataSources";
import type { UseAsOfResult } from "../../state/useAsOf";

const massive = (stream: DataSourceInfo["stream"]): DataSourceInfo => ({
  id: "massive", label: "Massive", status: "amber", detail: "delayed feed", active: true, tickers: ["SPY"], stream,
});

function renderPill(source: DataSourceInfo) {
  const dataSources = {
    sources: [source], active: source.id, switching: false, dataAge: null,
    switchSource: vi.fn(async () => {}), refresh: vi.fn(),
  } as unknown as UseDataSourcesResult;
  const asof = { asof: null, busy: false } as unknown as UseAsOfResult;
  const session = { universe: null } as unknown as React.ContextType<typeof NodeScopeContext>;
  return render(
    <NodeScopeContext.Provider value={session}>
      <MarketPill dataSources={dataSources} asof={asof} onClick={() => {}} />
    </NodeScopeContext.Provider>,
  );
}

afterEach(cleanup);

describe("MarketPill", () => {
  it("lists the stream-health lines in its tooltip while the source streams", () => {
    renderPill(massive({
      connected: true, cluster: "delayed", rate: 340, lastMessageAge: 2, lastQuoteAge: 2, reconnects: 1,
      lastError: null, subscribed: 950, acknowledged: 812, refused: 0, overCap: 916, requested: 1866, cap: 950,
      sessionOpen: true, level: "amber", detail: "streaming 812 · 340 msg/s · last 2 s",
    }));
    const title = screen.getByRole("button").title;
    expect(title).toContain("Stream: 812 acked of 950 subscribed (cap 950) · 916 over cap");
    expect(title).toContain("Stream: 340 msg/s · last tick 2 s · delayed cluster");
    expect(title).toContain("Stream: 1 reconnect");
  });

  it("says nothing about a stream when the source does not stream", () => {
    renderPill(massive(null));
    expect(screen.getByRole("button").title).not.toContain("Stream:");
  });
});
