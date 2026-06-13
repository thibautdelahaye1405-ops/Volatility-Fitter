// As-of (timestamp) selector state: Live / Previous Close / a provider EOD
// trading day / a captured intraday snapshot. Talks to GET /asof (capabilities +
// current selection) and POST /asof (apply). Refetched when the active data
// source changes, since each source supports different history.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** Current as-of selection + what the active source/store can offer. */
export interface AsOfState {
  mode: string; // "live" | "prev_close" | "eod" | "captured"
  on: string | null; // ISO date for "eod"
  ts: string | null; // ISO datetime for "captured"
  supportedModes: string[];
  prevCloseAvailable: boolean;
  historyDates: string[]; // provider EOD trading days, newest first
  captured: string[]; // captured intraday timestamps, newest first
}

/** A selection to POST. */
export interface AsOfSelection {
  mode: string;
  on?: string | null;
  ts?: string | null;
}

export interface UseAsOfResult {
  asof: AsOfState | null;
  busy: boolean;
  setAsOf: (selection: AsOfSelection) => Promise<void>;
}

export function useAsOf(
  live: boolean,
  activeSource: string,
  onChanged?: () => void,
): UseAsOfResult {
  const [asof, setAsofState] = useState<AsOfState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!live) {
      setAsofState(null);
      return;
    }
    const controller = new AbortController();
    api
      .get<AsOfState>("/asof", { signal: controller.signal })
      .then(setAsofState)
      .catch(() => {
        /* keep last known state on a transient failure */
      });
    return () => controller.abort();
  }, [live, activeSource]);

  const setAsOf = useCallback(
    async (selection: AsOfSelection) => {
      setBusy(true);
      try {
        const next = await api.post<AsOfState>("/asof", {
          body: { mode: selection.mode, on: selection.on ?? null, ts: selection.ts ?? null },
        });
        setAsofState(next);
        onChanged?.();
      } catch {
        /* switch failed: keep the current as-of */
      } finally {
        setBusy(false);
      }
    },
    [onChanged],
  );

  return { asof, busy, setAsOf };
}
