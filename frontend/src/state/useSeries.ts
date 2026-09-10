// Series data layer (SERIES ARC S4): the hooks and verbs the Series lens
// runs on — the ticker's series list (re-read while a job moves), one
// series document (re-read on demand or when the job's counters move), the
// job status through the SSE stream with a polling backstop (the useWorkflow
// pattern: an absent / dropped stream degrades to polling, never freezes),
// and the verbs (estimate · create · import · start · resume · pause ·
// cancel · delete · presets). Live backend only — never a mock. Errors are
// thrown as Error(<the backend's `detail`>) so a dialog can print them.
import { useCallback, useEffect, useState } from "react";
import { api, API_BASE_URL, ApiError } from "./api";
import type {
  LaneSpec, SeriesDoc, SeriesEstimate, SeriesImportRequest, SeriesJobStatus, SeriesSpec,
  SeriesStatus, SeriesSummary,
} from "../lib/seriesTypes";

/** List refresh cadence while any listed series is queued / harvesting / calibrating. */
const LIST_POLL_MS = 5_000;
/** Status poll cadence when the SSE stream is down; relaxed ×5 while it pushes. */
const STATUS_POLL_MS = 3_000;
const ACTIVE_STATUSES: ReadonlySet<SeriesStatus> = new Set(["queued", "harvesting", "calibrating"]);

/** A series whose job is still moving (the list keeps re-reading for it). */
export function isSeriesActive(status: SeriesStatus | null | undefined): boolean {
  return status != null && ACTIVE_STATUSES.has(status);
}

/** The backend's `detail` (a string, or pydantic's list of {msg}) when the
 *  error is an ApiError; the plain message otherwise. */
export function seriesErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = (JSON.parse(err.body) as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((d) => (typeof d === "object" && d !== null && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
          .join("; ");
      }
    } catch {
      /* not a JSON body */
    }
    return err.body || `${err.status} ${err.statusText}`;
  }
  return err instanceof Error ? err.message : String(err);
}

async function unwrap<T>(p: Promise<T>): Promise<T> {
  try {
    return await p;
  } catch (err: unknown) {
    throw new Error(seriesErrorMessage(err));
  }
}

const idPath = (id: string) => `/series/${encodeURIComponent(id)}`;

// ------------------------------------------------------------------ verbs

/** The eight lane presets resolved against the live settings. */
export function fetchPresets(): Promise<LaneSpec[]> {
  return unwrap(api.get<LaneSpec[]>("/series/presets"));
}

export function estimateSeries(spec: SeriesSpec): Promise<SeriesEstimate> {
  return unwrap(api.post<SeriesEstimate>("/series/estimate", { body: spec, timeoutMs: 120_000 }));
}

export function createSeries(spec: SeriesSpec): Promise<{ id: string; estimate: SeriesEstimate }> {
  return unwrap(api.post<{ id: string; estimate: SeriesEstimate }>("/series", { body: spec, timeoutMs: 120_000 }));
}

/** Frames from stored snapshots (captures · a backtest store · fixtures). */
export function importSeries(req: SeriesImportRequest): Promise<SeriesDoc> {
  return unwrap(api.post<SeriesDoc>("/series/import-store", { body: req, timeoutMs: 600_000 }));
}

export function startSeries(id: string): Promise<SeriesJobStatus> {
  return unwrap(api.post<SeriesJobStatus>(`${idPath(id)}/start`));
}

/** Same job slot as start: a paused / failed / cancelled series continues
 *  from its first unfinished frame. */
export function resumeSeries(id: string): Promise<SeriesJobStatus> {
  return unwrap(api.post<SeriesJobStatus>(`${idPath(id)}/resume`));
}

export function pauseSeries(id: string): Promise<SeriesJobStatus> {
  return unwrap(api.post<SeriesJobStatus>(`${idPath(id)}/pause`));
}

export function cancelSeries(id: string): Promise<SeriesJobStatus> {
  return unwrap(api.post<SeriesJobStatus>(`${idPath(id)}/cancel`));
}

/** Delete the series with its fits (a running job is stopped first). */
export function deleteSeries(id: string): Promise<{ deleted: boolean; id: string }> {
  return unwrap(api.delete<{ deleted: boolean; id: string }>(idPath(id)));
}

// ------------------------------------------------------------------ hooks

export interface SeriesListResult {
  /** Newest first (the backend's order). */
  series: SeriesSummary[];
  /** First read of the current ticker in flight. */
  loading: boolean;
  /** The current ticker's list has been read at least once. */
  loaded: boolean;
  /** The backend's refusal (409 without a store, a network error), or null. */
  error: string | null;
  refresh: () => void;
}

/** The ticker's series; re-read on demand and every 5 s while any listed
 *  job is queued / harvesting / calibrating. Empty off-live or without a ticker. */
export function useSeriesList(ticker: string | null, live: boolean): SeriesListResult {
  const [series, setSeries] = useState<SeriesSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  const enabled = live && ticker !== null && ticker !== "";

  useEffect(() => {
    if (!enabled) {
      setSeries([]);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer = 0;
    let first = true;
    const tick = async () => {
      if (first) setLoading(true);
      try {
        const r = await api.get<{ series: SeriesSummary[] }>("/series", { params: { ticker } });
        if (cancelled) return;
        setSeries(r.series);
        setError(null);
        setLoadedFor(ticker);
        // Keep re-reading only while a job moves; refresh() restarts the loop.
        if (r.series.some((s) => isSeriesActive(s.status))) {
          timer = window.setTimeout(() => void tick(), LIST_POLL_MS);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        setError(seriesErrorMessage(err));
        setLoadedFor(ticker);
      } finally {
        if (!cancelled && first) setLoading(false);
        first = false;
      }
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, ticker, nonce]);

  return { series, loading, loaded: enabled && loadedFor === ticker, error, refresh };
}

export interface SeriesDocResult {
  /** The document of `id` (never another series' — null across an id change). */
  doc: SeriesDoc | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/** One series document; re-read when `epoch` changes (the lens bumps it
 *  when the job's framesReady / fitsDone / status move) or on refresh(). */
export function useSeriesDoc(id: string | null, epoch: number): SeriesDocResult {
  const [doc, setDoc] = useState<SeriesDoc | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (id === null) {
      setDoc(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get<SeriesDoc>(idPath(id))
      .then((d) => {
        if (!cancelled) setDoc(d);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(seriesErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, epoch, nonce]);

  return { doc: doc !== null && doc.id === id ? doc : null, loading, error, refresh };
}

/** The job status of one series: SSE `GET /series/stream/{id}` (one status
 *  JSON per `data:` event, keep-alive comments ignored by EventSource) with a
 *  3 s poll while the stream is down — relaxed once the job stops moving.
 *  Closed on unmount / id change; null until the first status arrives. */
export function useSeriesStatus(id: string | null): SeriesJobStatus | null {
  const [status, setStatus] = useState<SeriesJobStatus | null>(null);

  useEffect(() => {
    setStatus(null);
    if (id === null) return;
    let stopped = false;
    let timer = 0;
    let es: EventSource | null = null;
    let sseOk = false;
    let moving = true;
    const apply = (s: SeriesJobStatus) => {
      if (stopped) return;
      moving = isSeriesActive(s.progress?.status) || s.queue.length > 0;
      setStatus(s);
    };
    const poll = async () => {
      try {
        apply(await api.get<SeriesJobStatus>(`${idPath(id)}/status`));
      } catch {
        /* backend unreachable: keep the last status */
      }
    };
    const tick = async () => {
      if (!sseOk) await poll();
      if (stopped) return;
      const delay = STATUS_POLL_MS * (sseOk ? 5 : 1) * (moving ? 1 : 5);
      timer = window.setTimeout(() => void tick(), delay);
    };
    if (typeof EventSource !== "undefined") {
      const src = new EventSource(new URL(`/series/stream/${encodeURIComponent(id)}`, API_BASE_URL));
      src.onopen = () => {
        sseOk = true;
      };
      src.onmessage = (e) => {
        try {
          apply(JSON.parse(e.data as string) as SeriesJobStatus);
        } catch {
          /* a malformed frame: the next one / the poll backstop recovers */
        }
      };
      // EventSource reconnects by itself; the poll covers the gap.
      src.onerror = () => {
        sseOk = false;
      };
      es = src;
    }
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      if (es) es.close();
    };
  }, [id]);

  return status;
}
