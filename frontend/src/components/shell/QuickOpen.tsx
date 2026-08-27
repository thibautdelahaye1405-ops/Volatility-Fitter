// Quick open + command palette (UI SHELL v2, wave 2 + wave 3 C4) — VS Code's
// "Go to file" / "Command palette" in one box:
//   Ctrl+P           nodes: fuzzy match on ticker + formatted expiry + ISO
//                    date; Enter opens the node's tab (preview), Shift+Enter
//                    pins; rows show the lit/dark dot + the quality glyph.
//   Ctrl+K · ">"     commands: the registry (state/commands) — every menu
//                    row, verb, lens, layout toggle, dialog; Enter runs it.
//                    A command with an argument (Save to server…, Save
//                    universe as…) turns the box into its prompt.
// Typing / deleting ">" switches mode live. Mounted by ShellDialogs for the
// "quickopen" (nodes) and "commands" (">" pre-filled) dialog ids.
import { useEffect, useMemo, useRef, useState } from "react";
import { useSmileSession } from "../../state/smileSession";
import { useWorkbench } from "../../state/workbench";
import { useLitMap } from "../../state/litMap";
import { useQualityReport } from "../../state/qualityContext";
import { useExpiryFormat } from "../../state/expiryFormat";
import { useOptionalCommands } from "../../state/commands";
import type { Command } from "../../state/commands";
import { formatExpiry } from "../../lib/expiryFormat";
import { fuzzyScore } from "../../lib/commands";

interface Row {
  ticker: string;
  expiry: string;
  label: string;
  /** Lower-cased haystack for the fuzzy match. */
  hay: string;
}

const rowClass = (on: boolean) =>
  ["flex cursor-pointer items-center gap-2.5 px-4 py-1.5 text-xs", on ? "bg-accent-500/15 text-slate-100" : "text-slate-300"].join(" ");

export default function QuickOpen({
  open,
  onClose,
  initialQuery = "",
}: {
  open: boolean;
  onClose: () => void;
  /** ">" opens straight in command mode. */
  initialQuery?: string;
}) {
  const { universe } = useSmileSession();
  const wb = useWorkbench();
  const lit = useLitMap();
  const { nodeOf } = useQualityReport();
  const { format } = useExpiryFormat();
  const cmds = useOptionalCommands();
  const [query, setQuery] = useState(initialQuery);
  const [cursor, setCursor] = useState(0);
  /** A command awaiting its argument (the box becomes its prompt). */
  const [pending, setPending] = useState<Command | null>(null);
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
  const commandMode = pending === null && query.trimStart().startsWith(">");
  const q = (commandMode ? query.trimStart().slice(1) : query).trim().toLowerCase().replace(/\s+/g, " ");
  const hits = useMemo(() => {
    if (commandMode) return [];
    return rows
      .map((r) => ({ r, s: fuzzyScore(r.hay, q.replace(/ /g, "")) }))
      .filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 40).map((x) => x.r);
  }, [rows, q, commandMode]);
  const cmdHits = useMemo(() => {
    if (!commandMode || cmds === null) return [];
    const needle = q.replace(/ /g, "");
    return cmds.commands
      .map((c) => ({ c, s: fuzzyScore(`${c.category} ${c.label}`.toLowerCase(), needle) }))
      .filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.c.category.localeCompare(b.c.category)).slice(0, 60).map((x) => x.c);
  }, [cmds, q, commandMode]);
  const count = pending !== null ? 0 : commandMode ? cmdHits.length : hits.length;

  // Reset + focus on open.
  useEffect(() => {
    if (!open) return;
    setQuery(initialQuery);
    setCursor(0);
    setPending(null);
    const id = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open, initialQuery]);
  useEffect(() => setCursor(0), [query]);

  if (!open) return null;

  const pickNode = (row: Row, pin: boolean) => {
    wb.openNode({ ticker: row.ticker, expiry: row.expiry }, { preview: !pin });
    onClose();
  };
  const pickCommand = (c: Command) => {
    if (!c.enabled) return;
    if (c.arg) { setPending(c); setQuery(""); return; }
    onClose();
    c.run();
  };
  const submitArg = () => {
    if (pending === null || query.trim() === "") return;
    const c = pending;
    onClose();
    c.run(query.trim());
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { setCursor((c) => Math.min(Math.max(0, count - 1), c + 1)); e.preventDefault(); }
    else if (e.key === "ArrowUp") { setCursor((c) => Math.max(0, c - 1)); e.preventDefault(); }
    else if (e.key === "Enter") {
      if (pending !== null) submitArg();
      else if (commandMode) { const c = cmdHits[cursor]; if (c) pickCommand(c); }
      else { const h = hits[cursor]; if (h) pickNode(h, e.shiftKey); }
      e.preventDefault();
    }
    else if (e.key === "Escape") { if (pending !== null) { setPending(null); setQuery(">"); } else onClose(); e.preventDefault(); }
    else if (e.key === "Backspace" && pending !== null && query === "") { setPending(null); setQuery(">"); e.preventDefault(); }
  };
  const placeholder = pending !== null
    ? pending.arg?.placeholder ?? "argument"
    : commandMode
      ? "Type a command — Enter runs it (Esc closes)"
      : "Go to node — type a ticker / expiry (Enter opens · Shift+Enter pins · > for commands)";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      <button className="absolute inset-0 cursor-default bg-black/50" aria-label="Close" onClick={onClose} />
      <div
        role="dialog"
        aria-label={commandMode || pending ? "Command palette" : "Quick open"}
        className="relative w-[min(92vw,34rem)] overflow-hidden rounded-xl border border-slate-700 bg-surface-900 shadow-2xl shadow-black/60"
      >
        <div className="flex items-center border-b border-slate-800">
          {pending !== null && (
            <span className="ml-3 shrink-0 rounded bg-accent-500/15 px-1.5 py-0.5 text-[10px] font-medium text-accent-300">
              {pending.label}
            </span>
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder={placeholder}
            aria-label={pending !== null ? pending.label : commandMode ? "Command palette" : "Quick open"}
            className="w-full bg-transparent px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
          />
        </div>
        <ul role="listbox" className="max-h-[50vh] overflow-y-auto py-1">
          {pending !== null && (
            <li className="px-4 py-3 text-xs text-slate-500">Enter runs “{pending.label}” with the name above · Esc goes back.</li>
          )}
          {pending === null && commandMode && cmdHits.length === 0 && (
            <li className="px-4 py-3 text-xs text-slate-500">{cmds === null ? "Commands need the shell." : `No command matches “${q}”.`}</li>
          )}
          {pending === null && commandMode && cmdHits.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === cursor} aria-disabled={!c.enabled}
              onMouseEnter={() => setCursor(i)} onClick={() => pickCommand(c)}
              className={`${rowClass(i === cursor)} ${c.enabled ? "" : "opacity-40"}`}>
              <span className="w-16 shrink-0 text-[10px] uppercase tracking-wider text-slate-500">{c.category}</span>
              <span className="font-medium">{c.label}</span>
              {c.active === true && <span className="text-accent-400">✓</span>}
              {c.detail && <span className="truncate text-[10px] text-slate-500">{c.detail}</span>}
              {c.shortcut && (
                <kbd className="ml-auto rounded border border-slate-700 px-1 font-mono text-[9px] text-slate-500">{c.shortcut}</kbd>
              )}
            </li>
          ))}
          {pending === null && !commandMode && hits.length === 0 && (
            <li className="px-4 py-3 text-xs text-slate-500">No node matches “{query}”.</li>
          )}
          {pending === null && !commandMode && hits.map((h, i) => {
            const isLit = lit.litOf(h.ticker, h.expiry);
            const qn = nodeOf(h.ticker, h.expiry);
            const dot = qn === undefined || !qn.hasFit ? "bg-slate-600"
              : !qn.leeOk || !qn.calendarOk ? "bg-rose-500" : qn.stale ? "bg-amber-400" : "bg-emerald-500";
            return (
              <li key={`${h.ticker}|${h.expiry}`} role="option" aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)} onClick={(e) => pickNode(h, e.shiftKey)} className={rowClass(i === cursor)}>
                <span className={["h-2 w-2 shrink-0 rounded-full border", isLit ? "border-accent-400 bg-accent-400" : "border-slate-600"].join(" ")} title={isLit ? "lit" : "dark"} />
                <span className="font-semibold">{h.ticker}</span>
                <span className="font-mono text-slate-400">{h.label}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-600">{h.expiry}</span>
                {qn?.hasFit && <span className="font-mono text-[10px] text-slate-500">{qn.rmsBp.toFixed(0)} bp</span>}
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
