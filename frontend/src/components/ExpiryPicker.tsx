// Per-ticker expiry picker for the Universe tab.
//
// Shows a ticker's full available expiry ladder (GET /universe/{t}/expiries)
// with a checkbox per rung, bulk-selection chips that add a whole class or
// window at once, and a "Reset to default" that re-applies the default rule.
// Every change PUTs the new selection and calls onChanged() so the smile
// session (and every workspace's selectors) refit on the new ladder.
import { useCallback, useEffect, useState } from "react";
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

interface ExpiryPickerProps {
  ticker: string;
  /** Refit the session on the new ladder after a selection change. */
  onChanged: () => void;
}

export default function ExpiryPicker({ ticker, onChanged }: ExpiryPickerProps) {
  const [data, setData] = useState<PickerData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<PickerData>(`/universe/${ticker}/expiries`)
      .then(setData)
      .catch((e: unknown) => setError(messageOf(e)));
  }, [ticker]);
  useEffect(() => load(), [load]);

  const apply = async (next: Set<string>) => {
    if (next.size === 0) return; // keep at least one rung
    setBusy(true);
    setError(null);
    try {
      const d = await api.put<PickerData>(`/universe/${ticker}/expiries`, {
        body: { expiries: [...next] },
      });
      setData(d);
      onChanged();
    } catch (e: unknown) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api.post<PickerData>(`/universe/${ticker}/expiries/reset`);
      setData(d);
      onChanged();
    } catch (e: unknown) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  if (data === null) {
    return <p className="px-1 py-2 text-[11px] text-slate-500">{error ?? "Loading expiries…"}</p>;
  }

  const selected = new Set(data.expiries.filter((e) => e.selected).map((e) => e.expiry));
  const nSel = selected.size;

  const addChip = (id: string) => {
    const next = new Set(selected);
    data.expiries.filter((e) => matchesChip(e, id)).forEach((e) => next.add(e.expiry));
    void apply(next);
  };
  const toggle = (expiry: string) => {
    const next = new Set(selected);
    if (next.has(expiry)) next.delete(expiry);
    else next.add(expiry);
    void apply(next);
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
          <button key={c.id} className={chipClass} disabled={busy} onClick={() => addChip(c.id)}>
            {c.label}
          </button>
        ))}
        <button
          className={`${chipClass} ml-auto`}
          disabled={busy}
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
          {data.expiries.map((e) => (
            <label
              key={e.expiry}
              className="flex cursor-pointer items-center gap-2 py-0.5 text-[11px] hover:bg-slate-800/30"
            >
              <input
                type="checkbox"
                checked={e.selected}
                disabled={busy}
                onChange={() => toggle(e.expiry)}
                className="accent-accent-500"
              />
              <span className={`w-24 font-mono ${e.selected ? "text-slate-100" : "text-slate-500"}`}>
                {e.expiry}
              </span>
              <span className={`w-16 ${BUCKET_COLOR[e.bucket] ?? "text-slate-400"}`}>{e.bucket}</span>
              <span className="ml-auto font-mono text-[10px] text-slate-600">{e.days}d</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
