// Data Source selector state: the configured market-data feeds, their status
// lights, and the active one. Talks to GET /datasources (polled lightly so a
// source coming online — e.g. a Bloomberg Terminal — updates the light) and
// POST /datasource/{id} to switch. Switching triggers an `onSwitched` callback
// (the session refetches the universe + smile on the new feed).
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** A status light level mirrored from the backend's feed_status(). */
export type SourceStatus = "green" | "amber" | "red";

/** One selectable data source. */
export interface DataSourceInfo {
  id: string;
  label: string;
  status: SourceStatus;
  detail: string;
  active: boolean;
}

/** Worst loaded live-chain age across the universe (backend data_age).
 *  Null when not applicable: historical as-of, nothing fetched, synthetic. */
export interface DataAgeInfo {
  ageMin: number;
  level: "fresh" | "amber" | "red";
  label: string; // human age: "4m" / "13.5h" / "3.2d"
  worstTicker: string;
}

/** Response of GET /datasources and POST /datasource/{id}. */
interface DataSourcesResponse {
  active: string;
  sources: DataSourceInfo[];
  dataAge?: DataAgeInfo | null;
}

/** What the TopBar selector consumes. */
export interface UseDataSourcesResult {
  sources: DataSourceInfo[];
  active: string;
  switching: boolean;
  dataAge: DataAgeInfo | null;
  switchSource: (id: string) => Promise<void>;
  /** Re-read the registry now (a snapshot file just registered a source). */
  refresh: () => void;
}

/** Re-probe interval so a source coming up/down updates its light. */
const POLL_MS = 30_000;
/** A switch answers from the backend's status cache (never a feed probe), so a
 *  slow answer means the server itself is wedged — give up well before the
 *  60 s default and tell the user. */
const SWITCH_TIMEOUT_MS = 20_000;

export function useDataSources(
  live: boolean,
  onSwitched?: () => void,
  onError?: (message: string) => void,
): UseDataSourcesResult {
  const [sources, setSources] = useState<DataSourceInfo[]>([]);
  const [active, setActive] = useState("");
  const [switching, setSwitching] = useState(false);
  const [dataAge, setDataAge] = useState<DataAgeInfo | null>(null);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const apply = (d: DataSourcesResponse) => {
    setSources(d.sources);
    setActive(d.active);
    setDataAge(d.dataAge ?? null);
  };

  // Poll /datasources while the backend is live; clear when offline (mock).
  useEffect(() => {
    if (!live) {
      setSources([]);
      setActive("");
      setDataAge(null);
      return;
    }
    const controller = new AbortController();
    const refresh = () =>
      api
        .get<DataSourcesResponse>("/datasources", { signal: controller.signal })
        .then(apply)
        .catch(() => {
          /* transient probe failure: keep the last known lights */
        });
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [live, nonce]);

  const switchSource = useCallback(
    async (id: string) => {
      if (id === active || switching) return;
      setSwitching(true);
      try {
        apply(await api.post<DataSourcesResponse>(`/datasource/${id}`, { timeoutMs: SWITCH_TIMEOUT_MS }));
        onSwitched?.();
      } catch (err: unknown) {
        // Never silent: say so, then re-read the registry — the backend may
        // have switched before the answer got lost, and the lights must not
        // stay frozen on the source we tried to leave.
        onError?.(`Switch to ${id} failed: ${err instanceof Error ? err.message : String(err)}`);
        refresh();
      } finally {
        setSwitching(false);
      }
    },
    [active, switching, onSwitched, onError, refresh],
  );

  return { sources, active, switching, dataAge, switchSource, refresh };
}
