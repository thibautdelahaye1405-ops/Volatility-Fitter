// Per-ticker expiry picker for the Universe tab.
//
// Shows a ticker's full available expiry ladder (GET /universe/{t}/expiries)
// with a checkbox per rung, bulk-selection chips that add a whole class or
// window at once, and a "Reset to default" that re-applies the default rule.
//
// Edits are COMPOSABLE and DEBOUNCED. Each toggle/chip mutates a synchronous
// selection ref (so a fast burst of clicks builds on each other instead of each
// reading the same stale snapshot and clobbering the others — the bug where
// deselecting 3 expiries only removed 1) and updates the checkboxes optimistically
// for instant feedback; a single PUT carrying the final set fires after a short
// debounce, then onChanged() refits the smile session on the new ladder.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../state/api";

interface ExpiryOption {
  expiry: string;
  t: number;
  days: number;
  bucket: string; // 0dte | weekly | monthly | quarterly | daily
  selected: boolean;
}
interface PickerData {
  ticker: string;
  asOf: string;
  mode: string; // auto | custom
  expiries: ExpiryOption[];
}

/** Collapse a burst of clicks into one PUT (ms). */
const COMMIT_DEBOUNCE_MS = 300;

/** Bulk-selection chips (each adds every matching expiry to the selection). */
const CHIPS = [
  { id: "0dte", label: "0DTE" },
  { id: "weekly", label: "Weeklies" },
  { id: "monthly", label: "Monthly" },
  { id: "quarterly", label: "Quarterly" },
  { id: "le1y", label: "≤1Y" },
  { id: "le2y", label: "≤2Y" },
  { id: "all", label: "All" },
];

/** Colour per bucket for the rung tags. */
const BUCKET_COLOR: Record<string, string> = {
  "0dte": "text-rose-400",
  weekly: "text-sky-400",
  monthly: "text-emerald-400",
  quarterly: "text-amber-400",
  daily: "text-slate-400",
};

function matchesChip(o: ExpiryOption, id: string): boolean {
  if (id === "0dte") return o.days <= 0;
  if (o.days <= 0) return false;
  if (id === "weekly" || id === "monthly" || id === "quarterly" || id === "daily")
    return o.bucket === id;
  if (id === "le1y") return o.days <= 366;
  if (id === "le2y") return o.days <= 731;
  if (id === "all") return true;
  return false;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const p: unknown = JSON.parse(err.body);
      if (typeof p === "object" && p !== null && typeof (p as { detail?: unknown }).detail === "string")
        return (p as { detail: string }).detail;
    } catch {
      /* non-JSON */
    }
  }
  return err instanceof Error ? err.message : String(err);
}

function selectionOf(d: PickerData): Set<string> {
  return new Set(d.expiries.filter((e) => e.selected).map((e) => e.expiry));
}

interface ExpiryPickerProps {
  ticker: string;
  /** Refit the session on the new ladder after a selection change. */
  onChanged: () => void;
}

export default function ExpiryPicker({ ticker, onChanged }: ExpiryPickerProps) {
  const [data, setData] = useState<PickerData | null>(null);
  // Optimistic selection (instant checkbox feedback). `selectedRef` mirrors it
  // synchronously so a rapid burst of toggles composes off the latest intent
  // rather than a stale render snapshot.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const selectedRef = useRef<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const pendingRef = useRef(false); // an edit is queued/in-flight: don't clobber it

  const applySelection = useCallback((next: Set<string>) => {
    selectedRef.current = next;
    setSelected(next);
  }, []);

  const load = useCallback(() => {
    api
      .get<PickerData>(`/universe/${ticker}/expiries`)
      .then((d) => {
        setData(d);
        if (!pendingRef.current) applySelection(selectionOf(d)); // keep live edits
      })
      .catch((e: unknown) => setError(messageOf(e)));
  }, [ticker, applySelection]);

  // Reload when the ticker changes; cancel any queued commit from the old one.
  useEffect(() => {
    pendingRef.current = false;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    load();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [load]);

  /** Push the latest intended selection to the backend (debounced caller). */
  const flush = useCallback(async () => {
    timerRef.current = undefined;
    const next = selectedRef.current;
    setSaving(true);
    setError(null);
    try {
      const d = await api.put<PickerData>(`/universe/${ticker}/expiries`, {
        body: { expiries: [...next] },
      });
      setData(d);
      // Only resync from the response if no newer edit was queued meanwhile.
      if (timerRef.current === undefined) applySelection(selectionOf(d));
      onChanged();
    } catch (e: unknown) {
      setError(messageOf(e));
      load(); // resync the ladder from the server on failure
    } finally {
      setSaving(false);
      if (timerRef.current === undefined) pendingRef.current = false;
    }
  }, [ticker, onChanged, applySelection, load]);

  /** Optimistically apply `next` and schedule a single debounced PUT. */
  const commit = useCallback(
    (next: Set<string>) => {
      if (next.size === 0) return; // keep at least one rung
      applySelection(next);
      pendingRef.current = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => void flush(), COMMIT_DEBOUNCE_MS);
    },
    [applySelection, flush],
  );

  if (data === null) {
    return <p className="px-1 py-2 text-[11px] text-slate-500">{error ?? "Loading expiries…"}</p>;
  }

  const nSel = selected.size;

  const addChip = (id: string) => {
    const next = new Set(selectedRef.current);
    data.expiries.filter((e) => matchesChip(e, id)).forEach((e) => next.add(e.expiry));
    commit(next);
  };
  const toggle = (expiry: string) => {
    const next = new Set(selectedRef.current);
    if (next.has(expiry)) next.delete(expiry);
    else next.add(expiry);
    commit(next);
  };

  const reset = async () => {
    if (timerRef.current) window.clearTimeout(timerRef.current); // drop queued edits
    timerRef.current = undefined;
    pendingRef.current = false;
    setSaving(true);
    setError(null);
    try {
      const d = await api.post<PickerData>(`/universe/${ticker}/expiries/reset`);
      setData(d);
      applySelection(selectionOf(d));
      onChanged();
    } catch (e: unknown) {
      setError(messageOf(e));
    } finally {
      setSaving(false);
    }
  };

  const chipClass =
    "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[10px] font-medium " +
    "text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 " +
    "disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className="mt-1 rounded-md border border-slate-800 bg-surface-800/40 p-2">
      {/* Bulk chips + reset */}
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <span className="mr-1 text-[10px] text-slate-500">Select:</span>
        {CHIPS.map((c) => (
          <button key={c.id} className={chipClass} onClick={() => addChip(c.id)}>
            {c.label}
          </button>
        ))}
        <button
          className={`${chipClass} ml-auto`}
          title="Re-apply the default selection rule"
          onClick={() => void reset()}
        >
          Reset
        </button>
      </div>

      <div className="mb-1 flex items-center justify-between text-[10px] text-slate-500">
        <span>
          {nSel} of {data.expiries.length} selected ·{" "}
          <span className={data.mode === "custom" ? "text-accent-400" : "text-slate-500"}>
            {data.mode}
          </span>
          {saving && <span className="ml-1 text-slate-600">· saving…</span>}
        </span>
        {error && (
          <span className="truncate text-amber-400" title={error}>
            {error}
          </span>
        )}
      </div>

      {/* Available ladder (nearest first) */}
      <div className="max-h-56 overflow-y-auto">
        <div className="divide-y divide-slate-800/40">
          {data.expiries.map((e) => {
            const isSel = selected.has(e.expiry);
            return (
              <label
                key={e.expiry}
                className="flex cursor-pointer items-center gap-2 py-0.5 text-[11px] hover:bg-slate-800/30"
              >
                <input
                  type="checkbox"
                  checked={isSel}
                  onChange={() => toggle(e.expiry)}
                  className="accent-accent-500"
                />
                <span className={`w-24 font-mono ${isSel ? "text-slate-100" : "text-slate-500"}`}>
                  {e.expiry}
                </span>
                <span className={`w-16 ${BUCKET_COLOR[e.bucket] ?? "text-slate-400"}`}>{e.bucket}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-600">{e.days}d</span>
              </label>
            );
          })}
        </div>
      </div>
    </div>
  );
}
