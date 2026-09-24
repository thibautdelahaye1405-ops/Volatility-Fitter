// Data Source selector state: the configured market-data feeds, their status
// lights, and the active one. Talks to GET /datasources (polled lightly so a
// source coming online — e.g. a Bloomberg Terminal — updates the light) and
// POST /datasource/{id} to switch. Switching triggers an `onSwitched` callback
// (the session refetches the universe + smile on the new feed).
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** A status light level mirrored from the backend's feed_status(). */
export type SourceStatus = "green" | "amber" | "red";

/** A streaming source's live health (backend StreamHealth — Massive's live
 *  book since 2026-09-24): the socket, the acknowledged / refused / over-cap
 *  counts against the cap, the message rate over the last 10 s, ages in
 *  seconds, the last error, and the light's own reading. Null while the source
 *  does not stream. */
export interface StreamHealth {
  connected: boolean;
  running?: boolean;
  connections?: number;
  connectedCount?: number;
  url?: string | null;
  cluster?: "realtime" | "delayed" | null;
  messages?: number;
  quotes?: number;
  rate: number;
  lastMessageAge: number | null;
  lastQuoteAge: number | null;
  lastMessageUtc?: string | null;
  reconnects: number;
  lastError: string | null;
  lastErrorAge?: number | null;
  authFailed?: boolean;
  subscribed: number;
  acknowledged: number;
  refused: number;
  overCap: number;
  requested: number;
  cap: number;
  sessionOpen: boolean;
  /** ticker -> served from the book right now (acknowledged + a quote booked). */
  tickers?: Record<string, boolean>;
  /** The allocation policy's answer (backend stream_allocation): per ticker
   *  the planned / live / focus counts, the focus nodes ("TICKER|ISO"), the
   *  per-ticker floor and the REST cadence behind the book. */
  allocation?: Record<string, { requested: number; live: number; focus: number }>;
  focus?: string[];
  floor?: number;
  restSeconds?: number | null;
  level: SourceStatus;
  detail: string;
}

/** One selectable data source. */
export interface DataSourceInfo {
  id: string;
  label: string;
  status: SourceStatus;
  detail: string;
  active: boolean;
  /** The active tickers this source serves now — pinned to it, or following
   *  it as the universe's default (state/tickerSources.ts). */
  tickers?: string[];
  /** Live-stream health while the source streams (null otherwise). */
  stream?: StreamHealth | null;
}

/** A seconds age for the health lines: "2 s", "4 min", "3 h", "—". */
export function fmtAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

const n = (v: number) => v.toLocaleString("en-US");

/** The one-line health reading of the Data-sources card:
 *  "812 acked · 340 msg/s · last tick 2 s" (refusals and over-cap appended). */
export function streamHealthLine(s: StreamHealth): string {
  const parts = [`${n(s.acknowledged)} acked`, `${Math.round(s.rate)} msg/s`, `last tick ${fmtAge(s.lastQuoteAge)}`];
  if (s.refused > 0) parts.push(`${n(s.refused)} refused`);
  if (s.overCap > 0) parts.push(`${n(s.overCap)} over cap`);
  return parts.join(" · ");
}

/** The health lines of the market pill's tooltip (subscription, flow, errors). */
export function streamHealthLines(s: StreamHealth): string[] {
  const sub = [`${n(s.acknowledged)} acked of ${n(s.subscribed)} subscribed (cap ${n(s.cap)})`];
  if (s.overCap > 0) sub.push(`${n(s.overCap)} over cap`);
  if (s.refused > 0) sub.push(`${n(s.refused)} refused`);
  const flow = [`${Math.round(s.rate)} msg/s`, `last tick ${fmtAge(s.lastQuoteAge)}`];
  if (s.cluster) flow.push(`${s.cluster} cluster`);
  if (!s.sessionOpen) flow.push("session closed");
  const lines = [sub.join(" · "), flow.join(" · ")];
  const shares = Object.entries(s.allocation ?? {});
  if (shares.length > 0) {
    // "NVDA 560/3,026 (focus 170) · SPY 390/10,544 · focus NVDA|2026-10-16 · rest 60 s"
    const parts = shares.map(([t, a]) => `${t} ${n(a.live)}/${n(a.requested)}${a.focus > 0 ? ` (focus ${n(a.focus)})` : ""}`);
    parts.push(`focus ${s.focus && s.focus.length > 0 ? s.focus.join(", ") : "none"}`);
    if (s.restSeconds != null) parts.push(`rest ${s.restSeconds} s`);
    lines.push(parts.join(" · "));
  }
  if (s.reconnects > 0 || s.lastError) {
    const err = [`${s.reconnects} reconnect${s.reconnects === 1 ? "" : "s"}`];
    if (s.lastError) err.push(`last error: ${s.lastError}`);
    lines.push(err.join(" · "));
  }
  return lines;
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
