// The relation DRAFT on screen (GRAPH ERGONOMICS ARC, E2): the single row
// list every message-family surface edits — the canvas arrows, the inspector's
// relation card, the Relations drawer tab and the templates.
//
// Ruling "what you see is what runs": edits land in local state at once (with
// undo / redo), then a debounced PUT stages them on the U6 DRAFT config; the
// shell derives `useDraftConfig` from the draft-vs-active diff so Run solves
// exactly the rows on screen, and Apply / Discard (the config pill) promote or
// drop them. Provenance of the rows on screen: the draft when one is staged
// with rows, else the active config, else the auto relations the solve would
// build (GET /graph/edges/messages/auto) — the first edit of an auto row
// materialises the whole set as an explicit draft, which is exactly the
// backend contract (an empty PUT means "back to auto").
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchMessageConfig } from "./useMessageConfig";
import { useMessageEdges, type MessageEdgeRow } from "./useMessageEdges";
import { flipRelation, relationKey } from "../lib/relationRows";

export type DraftSource = "draft" | "active" | "auto";

/** Debounce between the last edit and the PUT that stages it. */
export const DRAFT_PUT_DEBOUNCE_MS = 450;
/** Undo depth. */
const HISTORY_CAP = 60;

export interface RelationDraft {
  /** The effective rows on screen (draft → active → auto). */
  rows: MessageEdgeRow[];
  /** Where the rows on screen come from. */
  source: DraftSource;
  loading: boolean;
  /** A PUT is pending (debounce) or in flight. */
  saving: boolean;
  error: string | null;
  canUndo: boolean;
  canRedo: boolean;
  /** Edit operations — each one is an undo step and schedules a PUT. */
  add: (row: MessageEdgeRow) => void;
  update: (key: string, patch: Partial<MessageEdgeRow>) => void;
  remove: (key: string) => void;
  removeMany: (keys: readonly string[]) => void;
  /** Reverse a relation's direction (§7.6/§8.3 identities). Returns the new key. */
  flip: (key: string) => string | null;
  /** Replace the whole list (templates, the §20 editor's save). */
  replaceAll: (rows: MessageEdgeRow[]) => void;
  /** Load the auto relations as editable rows (explicit draft). */
  seedAuto: () => Promise<void>;
  /** Stage an empty draft — the solve goes back to the auto relations. */
  resetAuto: () => Promise<void>;
  undo: () => void;
  redo: () => void;
  /** Re-read the slots (after Apply / Discard / an external editor save). */
  reload: () => void;
  /** Look up a row by its directed key. */
  byKey: (key: string) => MessageEdgeRow | undefined;
}

/** Everything `useRelationDraft` needs from the shell. */
interface RelationDraftOptions {
  /** False under the smooth field (no message rows to edit): stays idle. */
  enabled: boolean;
  /** Fired after a PUT landed — the shell refreshes the config pair. */
  onPersisted?: () => void;
}

export function useRelationDraft({ enabled, onPersisted }: RelationDraftOptions): RelationDraft {
  const { fetchAuto, putEdges } = useMessageEdges();
  const [rows, setRows] = useState<MessageEdgeRow[]>([]);
  const [source, setSource] = useState<DraftSource>("auto");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  // Undo / redo stacks of full row lists (rows are small; a copy per step is
  // cheaper than an operation log and trivially correct).
  const undoRef = useRef<MessageEdgeRow[][]>([]);
  const redoRef = useRef<MessageEdgeRow[][]>([]);
  const [histTick, setHistTick] = useState(0);
  // Pending PUT (debounced); the ref carries the latest rows into the timer.
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<MessageEdgeRow[] | null>(null);
  const onPersistedRef = useRef(onPersisted);
  onPersistedRef.current = onPersisted;

  /** Load the slots: draft rows → active rows → auto relations. */
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoading(true);
    setError(null);
    (async () => {
      const pair = await fetchMessageConfig().catch(() => null);
      const draft = pair?.draft?.rows ?? [];
      const active = pair?.active?.rows ?? [];
      if (draft.length > 0) return { rows: draft, source: "draft" as const };
      if (active.length > 0) return { rows: active, source: "active" as const };
      return { rows: await fetchAuto(), source: "auto" as const };
    })()
      .then((r) => {
        if (!alive) return;
        setRows(r.rows);
        setSource(r.source);
        undoRef.current = [];
        redoRef.current = [];
        setHistTick((t) => t + 1);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [enabled, version, fetchAuto]);

  /** Stage `next` on the draft after the debounce (latest wins). */
  const schedulePut = useCallback(
    (next: MessageEdgeRow[]) => {
      pendingRef.current = next;
      setSaving(true);
      if (timerRef.current !== null) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        const payload = pendingRef.current;
        pendingRef.current = null;
        if (payload === null) return;
        putEdges(payload)
          .then(() => {
            setError(null);
            setSource("draft");
            onPersistedRef.current?.();
          })
          .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
          .finally(() => {
            if (pendingRef.current === null) setSaving(false);
          });
      }, DRAFT_PUT_DEBOUNCE_MS);
    },
    [putEdges],
  );

  // Flush a pending PUT on unmount (a lens switch must not drop an edit).
  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
      const payload = pendingRef.current;
      if (payload !== null) void putEdges(payload).catch(() => undefined);
    },
    [putEdges],
  );

  /** Commit an edit: push the previous list on the undo stack, drop redo. */
  const commit = useCallback(
    (next: MessageEdgeRow[]) => {
      setRows((prev) => {
        undoRef.current = [...undoRef.current.slice(-(HISTORY_CAP - 1)), prev];
        redoRef.current = [];
        return next;
      });
      setHistTick((t) => t + 1);
      schedulePut(next);
    },
    [schedulePut],
  );

  const add = useCallback(
    (row: MessageEdgeRow) => {
      const key = relationKey(row);
      commit([...rows.filter((r) => relationKey(r) !== key), row]);
    },
    [rows, commit],
  );
  const update = useCallback(
    (key: string, patch: Partial<MessageEdgeRow>) => {
      if (!rows.some((r) => relationKey(r) === key)) return;
      commit(rows.map((r) => (relationKey(r) === key ? { ...r, ...patch } : r)));
    },
    [rows, commit],
  );
  const removeMany = useCallback(
    (keys: readonly string[]) => {
      const drop = new Set(keys);
      if (!rows.some((r) => drop.has(relationKey(r)))) return;
      commit(rows.filter((r) => !drop.has(relationKey(r))));
    },
    [rows, commit],
  );
  const remove = useCallback((key: string) => removeMany([key]), [removeMany]);
  const flip = useCallback(
    (key: string): string | null => {
      const row = rows.find((r) => relationKey(r) === key);
      if (row === undefined) return null;
      const flipped = flipRelation(row);
      const nk = relationKey(flipped);
      commit(rows.map((r) => (relationKey(r) === key ? flipped : r)).filter(
        (r, i, arr) => arr.findIndex((x) => relationKey(x) === relationKey(r)) === i,
      ));
      return nk;
    },
    [rows, commit],
  );
  const replaceAll = useCallback((next: MessageEdgeRow[]) => commit(next), [commit]);

  const seedAuto = useCallback(async () => {
    setError(null);
    try {
      commit(await fetchAuto());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [fetchAuto, commit]);

  const resetAuto = useCallback(async () => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    pendingRef.current = null;
    setSaving(true);
    setError(null);
    try {
      await putEdges([]);
      const auto = await fetchAuto();
      setRows((prev) => {
        undoRef.current = [...undoRef.current.slice(-(HISTORY_CAP - 1)), prev];
        redoRef.current = [];
        return auto;
      });
      setSource("auto");
      setHistTick((t) => t + 1);
      onPersistedRef.current?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [putEdges, fetchAuto]);

  const undo = useCallback(() => {
    const prev = undoRef.current.pop();
    if (prev === undefined) return;
    setRows((cur) => {
      redoRef.current.push(cur);
      return prev;
    });
    setHistTick((t) => t + 1);
    schedulePut(prev);
  }, [schedulePut]);
  const redo = useCallback(() => {
    const next = redoRef.current.pop();
    if (next === undefined) return;
    setRows((cur) => {
      undoRef.current.push(cur);
      return next;
    });
    setHistTick((t) => t + 1);
    schedulePut(next);
  }, [schedulePut]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const index = useMemo(() => new Map(rows.map((r) => [relationKey(r), r])), [rows]);
  const byKey = useCallback((key: string) => index.get(key), [index]);

  // histTick is read so canUndo/canRedo re-render with the stacks.
  void histTick;
  return {
    rows,
    source,
    loading,
    saving,
    error,
    canUndo: undoRef.current.length > 0,
    canRedo: redoRef.current.length > 0,
    add,
    update,
    remove,
    removeMany,
    flip,
    replaceAll,
    seedAuto,
    resetAuto,
    undo,
    redo,
    reload,
    byKey,
  };
}
