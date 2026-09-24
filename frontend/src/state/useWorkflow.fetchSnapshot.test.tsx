// The Fetch ▾ Snapshot verb sends the 15-s freshness window (`maxAgeSeconds`)
// so a double-click / a Calibrate-after-Fetch costs zero provider calls, and
// the Last chip says how many tickers the backend skipped as fresh. The
// legacy /fetch/options verb keeps its empty body. Offline: the api is mocked.
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiPost = vi.fn();
const apiGet = vi.fn();
vi.mock("./api", () => ({
  API_BASE_URL: "http://localhost:0",
  api: {
    post: (...args: unknown[]) => apiPost(...args),
    get: (...args: unknown[]) => apiGet(...args),
  },
  ApiError: class ApiError extends Error {},
}));

import { doneLabel, FETCH_MAX_AGE_S, useWorkflow } from "./useWorkflow";

beforeEach(() => {
  apiPost.mockReset();
  apiGet.mockReset();
  apiGet.mockRejectedValue(new Error("offline")); // the post-action resync is a no-op
});

describe("doneLabel", () => {
  it("names the skipped-fresh tickers of a snapshot fetch and nothing else", () => {
    expect(doneLabel("fetchSnapshot", { tickers: ["SPY"], skippedFresh: ["QQQ", "AAPL"] }))
      .toBe("Fetched snapshot · 2 fresh, skipped");
    expect(doneLabel("fetchSnapshot", { tickers: ["SPY"], skippedFresh: [] })).toBe("Fetched snapshot");
    expect(doneLabel("fetchSnapshot", undefined)).toBe("Fetched snapshot");
    expect(doneLabel("options", { skippedFresh: ["QQQ"] })).toBe("Fetched option quotes");
  });
});

describe("useWorkflow fetch verbs", () => {
  it("posts the freshness window with Snapshot and narrates the skipped tickers", async () => {
    apiPost.mockResolvedValue({ tickers: ["SPY"], spots: {}, calibrationStarted: false, skippedFresh: ["QQQ", "AAPL"] });
    const { result } = renderHook(() => useWorkflow(false, vi.fn(), "mid"));
    await act(async () => {
      await result.current.fetchSnapshot();
    });
    expect(FETCH_MAX_AGE_S).toBe(15);
    expect(apiPost).toHaveBeenCalledWith(
      "/fetch/snapshot",
      expect.objectContaining({ body: { maxAgeSeconds: 15 }, params: { fit_mode: "mid" } }),
    );
    await waitFor(() => expect(result.current.lastAction?.label).toBe("Fetched snapshot · 2 fresh, skipped"));
    expect(result.current.lastAction?.ok).toBe(true);
    expect(result.current.pending).toBeNull();
  });

  it("leaves the legacy option-quotes verb without a window", async () => {
    apiPost.mockResolvedValue({ tickers: ["SPY"], spots: {}, calibrationStarted: false });
    const { result } = renderHook(() => useWorkflow(false, vi.fn(), "mid"));
    await act(async () => {
      await result.current.fetchOptions();
    });
    expect(apiPost).toHaveBeenCalledWith("/fetch/options", expect.objectContaining({ body: {} }));
    await waitFor(() => expect(result.current.lastAction?.label).toBe("Fetched option quotes"));
  });
});
