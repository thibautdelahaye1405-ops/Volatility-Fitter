// As-of (timestamp) selector state — a two-level day -> moment pick.
//
// GET /asof returns the current selection plus the recent business days that have
// data, each flagging whether a close / captured snapshots / an intraday fetch
// are available. POST /asof applies either Live or a high-level moment
// (`{mode:"moment", on, moment, offsetMinutes}`); the backend resolves the
// concrete chain. Refetched when the active data source changes.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** One selectable business day and what it can serve. */
export interface AsOfDay {
  date: string; // ISO date
  isToday: boolean;
  hasClose: boolean; // official close available
  hasCaptures: boolean; // captured intraday snapshots exist
  intraday: boolean; // provider can fetch an arbitrary instant this day
}

/** A within-day moment. */
export type AsOfMoment = "close" | "latest" | "before_close";

/** Current as-of selection + day-grouped capabilities. */
export interface AsOfState {
  mode: string; // "live" | "eod" | "prev_close" | "captured" | "intraday"
  on: string | null;
  ts: string | null;
  day: string | null; // the dropdown day this resolved from
  moment: AsOfMoment | null;
  offset: number | null; // minutes-before-close for "before_close"
  supportedModes: string[];
  intradayCapable: boolean;
  closeOffsets: number[]; // preset "minutes before close" choices
  days: AsOfDay[]; // recent business days with data, newest first
}

export interface UseAsOfResult {
  asof: AsOfState | null;
  busy: boolean;
  /** Back to live real-time. */
  setLive: () => Promise<void>;
  /** The provider's prior-session settle (only when "prev_close" is supported). */
  setPrevClose: () => Promise<void>;
  /** Apply a (day, moment) pick; `offsetMinutes` only for "before_close". */
  setMoment: (on: string, moment: AsOfMoment, offsetMinutes?: number) => Promise<void>;
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

  const post = useCallback(
    async (body: Record<string, unknown>) => {
      setBusy(true);
      try {
        setAsofState(await api.post<AsOfState>("/asof", { body }));
        onChanged?.();
      } catch {
        /* switch failed: keep the current as-of */
      } finally {
        setBusy(false);
      }
    },
    [onChanged],
  );

  const setLive = useCallback(() => post({ mode: "live" }), [post]);
  const setPrevClose = useCallback(() => post({ mode: "prev_close" }), [post]);
  const setMoment = useCallback(
    (on: string, moment: AsOfMoment, offsetMinutes?: number) =>
      post({ mode: "moment", on, moment, offsetMinutes }),
    [post],
  );

  return { asof, busy, setLive, setPrevClose, setMoment };
}
