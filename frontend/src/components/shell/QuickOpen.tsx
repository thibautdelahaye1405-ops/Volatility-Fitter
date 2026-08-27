// Quick open (UI SHELL v2 wave 2, Ctrl+P — VS Code's "Go to file" for
// nodes): a palette over the universe's (ticker, expiry) nodes with fuzzy
// matching on ticker + formatted expiry + ISO date, ↑/↓ to move, Enter to
// open the node's tab (preview), Shift+Enter to pin, Esc to close. Rows show
// the lit/dark dot and the quality glyph so the palette doubles as a status
// scan. Mounted by ShellDialogs when the workbench dialog is "quickopen".
import { useEffect, useMemo, useRef, useState } from "react";
import { useSmileSession } from "../../state/smileSession";
import { useWorkbench } from "../../state/workbench";
import { useLitMap } from "../../state/litMap";
import { useQualityReport } from "../../state/qualityContext";
import { useExpiryFormat } from "../../state/expiryFormat";
import { formatExpiry } from "../../lib/expiryFormat";

interface Row {
  ticker: string;
  expiry: string;
  label: string;
  /** Lower-cased haystack for the fuzzy match. */
  hay: string;
}

/** Subsequence fuzzy match: every query char appears in order; score favours
 *  contiguous runs and early hits (0 = no match). */
function fuzzyScore(hay: string, q: string): number {
  if (q === "") return 1;
  let hi = 0, score = 0, run = 0;
  for (const ch of q) {
    const idx = hay.indexOf(ch, hi);
    if (idx < 0) return 0;
    run = idx === hi ? run + 1 : 1;
    score += run * 2 + (idx < 3 ? 2 : 0);
    hi = idx + 1;
  }
  return score;
}

export default function QuickOpen({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { universe } = useSmileSession();
  const wb = useWorkbench();
  const lit = useLitMap();
  const { nodeOf } = useQualityReport();
  const { format } = useExpiryFormat();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const rows = useMemo<Row[]>(
    () =>
      (universe?.tickers ?? []).flatMap((t) =>
        (universe?.expiries[t] ?? []).map((r) => {
          const label = formatExpiry(r.expiry, r.t, format);
          return { ticker: t, expiry: r.expiry, label, hay: `${t} ${label} ${r.expiry}`.toLowerCase() };
        }),
      ),
    [universe, format],
  );
  const hits = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/\s+/g, " ");
    return rows
      .map((r) => ({ r, s: fuzzyScore(r.hay, q.replace(/ /g, "")) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 40)
      .map((x) => x.r);
  }, [rows, query]);

  // Reset + focus on open.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const id = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open]);
  useEffect(() => setCursor(0), [query]);

  if (!open) return null;

  const pick = (row: Row, pin: boolean) => {
    wb.openNode({ ticker: row.ticker, expiry: row.expiry }, { preview: !pin });
    onClose();
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { setCursor((c) => Math.min(hits.length - 1, c + 1)); e.preventDefault(); }
    else if (e.key === "ArrowUp") { setCursor((c) => Math.max(0, c - 1)); e.preventDefault(); }
    else if (e.key === "Enter") { const h = hits[cursor]; if (h) pick(h, e.shiftKey); e.preventDefault(); }
    else if (e.key === "Escape") { onClose(); e.preventDefault(); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      <button className="absolute inset-0 cursor-default bg-black/50" aria-label="Close" onClick={onClose} />
      <div
        role="dialog"
        aria-label="Quick open"
        className="relative w-[min(92vw,34rem)] overflow-hidden rounded-xl border border-slate-700 bg-surface-900 shadow-2xl shadow-black/60"
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
          placeholder="Go to node — type a ticker / expiry (Enter opens · Shift+Enter pins)"
          aria-label="Quick open"
          className="w-full border-b border-slate-800 bg-transparent px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
        />
        <ul role="listbox" className="max-h-[50vh] overflow-y-auto py-1">
          {hits.length === 0 && (
            <li className="px-4 py-3 text-xs text-slate-500">No node matches “{query}”.</li>
          )}
          {hits.map((h, i) => {
            const isLit = lit.litOf(h.ticker, h.expiry);
            const q = nodeOf(h.ticker, h.expiry);
            const dot = q === undefined || !q.hasFit ? "bg-slate-600"
              : !q.leeOk || !q.calendarOk ? "bg-rose-500" : q.stale ? "bg-amber-400" : "bg-emerald-500";
            return (
              <li
                key={`${h.ticker}|${h.expiry}`}
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={(e) => pick(h, e.shiftKey)}
                className={[
                  "flex cursor-pointer items-center gap-2.5 px-4 py-1.5 text-xs",
                  i === cursor ? "bg-accent-500/15 text-slate-100" : "text-slate-300",
                ].join(" ")}
              >
                <span
                  className={[
                    "h-2 w-2 shrink-0 rounded-full border",
                    isLit ? "border-accent-400 bg-accent-400" : "border-slate-600",
                  ].join(" ")}
                  title={isLit ? "lit" : "dark"}
                />
                <span className="font-semibold">{h.ticker}</span>
                <span className="font-mono text-slate-400">{h.label}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-600">{h.expiry}</span>
                {q?.hasFit && <span className="font-mono text-[10px] text-slate-500">{q.rmsBp.toFixed(0)} bp</span>}
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
