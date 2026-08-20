// Fetch hook for GET /smiles/{ticker}/{expiry}/weights (V3.4 item 5).
//
// The endpoint is read-only and poll-safe (it never triggers a fit), so the
// hook simply refetches whenever the smile identity changes — quote edits,
// undo/redo, scheme/settings changes and calibrations all swap the `smile`
// object (the QuoteTable reload idiom). In mock mode (or on any fetch
// failure while a mock smile shows) it falls back to equal weights derived
// from the quote strikes so the strip renders standalone.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { FitMode } from "./useSmile";
import type { SmileData } from "../lib/mockData";
import { mockWeightEntries } from "../lib/weightStrip";
import type { WeightsData } from "../lib/weightStrip";

export function useWeights(
  enabled: boolean,
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  smile: SmileData | null,
): WeightsData | null {
  const [data, setData] = useState<WeightsData | null>(null);

  useEffect(() => {
    if (!enabled || smile === null) {
      setData(null);
      return;
    }
    if (!live || ticker === "" || expiry === "") {
      // Mock fallback: equal scheme over the mock quotes' strikes.
      setData({
        ticker: smile.ticker,
        expiry: smile.expiry,
        scheme: "equal",
        maxMult: 10,
        meanNormalized: true,
        entries: mockWeightEntries(smile.quotes),
      });
      return;
    }
    const controller = new AbortController();
    api
      .get<WeightsData>(`/smiles/${ticker}/${expiry}/weights`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then(setData)
      .catch(() => {
        if (!controller.signal.aborted) setData(null);
      });
    return () => controller.abort();
  }, [enabled, live, ticker, expiry, fitMode, smile]);

  return data;
}
