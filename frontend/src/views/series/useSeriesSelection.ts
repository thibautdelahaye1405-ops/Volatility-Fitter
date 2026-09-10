// Series lens · selection and job plumbing (SERIES ARC S4): which series the
// lens shows (a parked deep link, the remembered id, else the newest), its
// document (re-read when the job's counters move), the job status (stream +
// poll backstop) and the verbs with a busy flag and an inline error. The
// view memory owns the id; this hook only asks it to change through `select`.
import { useCallback, useEffect, useRef, useState } from "react";
import type { SeriesProgress } from "../../lib/seriesTypes";
import {
  cancelSeries, deleteSeries, pauseSeries, resumeSeries, startSeries,
  useSeriesDoc, useSeriesList, useSeriesStatus,
} from "../../state/useSeries";
import { takePendingSeriesLink } from "../../state/seriesDeepLink";
import type { SeriesLink } from "../../state/seriesDeepLink";
import { progressKey } from "./seriesSelectors";

export function useSeriesSelection(
  ticker: string,
  live: boolean,
  seriesId: string | null,
  select: (id: string | null) => void,
) {
  const selectRef = useRef(select);
  selectRef.current = select;
  // The deep link is taken ONCE, at mount (state/seriesDeepLink).
  const [pending, setPending] = useState<SeriesLink | null>(() => takePendingSeriesLink());
  // A series just created is selected before the list carries it.
  const createdRef = useRef<string | null>(null);

  const list = useSeriesList(live ? ticker : null, live);
  const { refresh } = list;
  const status = useSeriesStatus(seriesId);

  // Reconcile the selection with the list: the deep link wins once; an id
  // the list lacks is dropped (unless just created / just linked); nothing
  // picked → the newest.
  useEffect(() => {
    if (pending !== null && pending.id !== seriesId) {
      selectRef.current(pending.id);
      return;
    }
    if (!list.loaded || list.loading) return;
    const listed = seriesId !== null && list.series.some((s) => s.id === seriesId);
    if (listed) {
      if (createdRef.current === seriesId) createdRef.current = null;
      return;
    }
    if (seriesId !== null && (createdRef.current === seriesId || pending?.id === seriesId)) return;
    selectRef.current(list.series[0]?.id ?? null);
  }, [pending, seriesId, list.loaded, list.loading, list.series]);

  // The document re-reads when the job's counters move (frames harvested,
  // fits landed, status changed) — the first key never triggers a re-read.
  const key = progressKey(status?.progress ?? null);
  const [docEpoch, setDocEpoch] = useState(0);
  const keyRef = useRef(key);
  useEffect(() => {
    if (keyRef.current !== key) {
      keyRef.current = key;
      setDocEpoch((n) => n + 1);
    }
  }, [key]);
  const docState = useSeriesDoc(seriesId, docEpoch);
  const progress: SeriesProgress | null = status?.progress ?? docState.doc?.progress ?? null;

  // A series deleted elsewhere (404) drops out of the selection.
  useEffect(() => {
    if (docState.error !== null && /unknown series/i.test(docState.error)) {
      createdRef.current = null;
      setPending(null);
      selectRef.current(null);
      refresh();
    }
  }, [docState.error, refresh]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (verb: (id: string) => Promise<unknown>, after?: () => void) => {
      if (seriesId === null) return;
      setBusy(true);
      setError(null);
      try {
        await verb(seriesId);
        after?.();
        refresh();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [seriesId, refresh],
  );
  const name = docState.doc?.spec.name ?? seriesId ?? "";
  const verbs = {
    start: () => void run(startSeries),
    resume: () => void run(resumeSeries),
    pause: () => void run(pauseSeries),
    cancel: () => void run(cancelSeries),
    remove: () => {
      if (seriesId === null) return;
      if (!window.confirm(`Delete the series "${name}" with its frames and fits?`)) return;
      void run(deleteSeries, () => {
        createdRef.current = null;
        selectRef.current(null);
      });
    },
  };

  /** The dialog created (and started) a series: show it now, re-read the list. */
  const markCreated = useCallback(
    (id: string) => {
      createdRef.current = id;
      selectRef.current(id);
      refresh();
    },
    [refresh],
  );

  const clearPending = useCallback(() => setPending(null), []);
  const pendingFrame = pending !== null && pending.id === seriesId ? pending.frame ?? null : null;

  return {
    list,
    status,
    progress,
    doc: docState.doc,
    docLoading: docState.loading,
    docError: docState.error,
    /** Folds into the payload caches' epoch: changes as fits land. */
    epochKey: key,
    busy,
    error,
    verbs,
    markCreated,
    /** A deep link still to be consumed (its frame jump happens once the document is in). */
    pendingActive: pending !== null,
    pendingFrame,
    clearPending,
  };
}
