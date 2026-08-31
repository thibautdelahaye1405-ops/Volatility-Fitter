// Help ▸ Keyboard shortcuts (HELP CENTER ARC, H4): the documented chord table
// (lib/shortcuts.ts — the SAME list the global handler fires from), grouped,
// with a filter box; a deep link `shortcuts:<keys>` highlights a row.
import { useMemo, useState } from "react";
import { SHORTCUT_GROUPS } from "../../lib/shortcuts";
import type { HelpPageProps } from "./HelpCenter";

export default function ShortcutsPage({ anchor }: HelpPageProps) {
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  const groups = useMemo(
    () => SHORTCUT_GROUPS.map((g) => ({ ...g, items: g.items.filter((s) => !q || `${s.keys} ${s.label} ${g.title}`.toLowerCase().includes(q)) })).filter((g) => g.items.length > 0),
    [q],
  );
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter shortcuts" placeholder="Filter chords — Ctrl, Alt, tab, zoom, quote…"
          className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-surface-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-accent-600/60 focus:outline-none" />
        <span className="text-[10px] text-slate-500">Browser-reserved chords (Ctrl+digits, Ctrl+W, Ctrl+PgUp/PgDn) are avoided on purpose</span>
      </div>
      <div className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
        {groups.map((g) => (
          <section key={g.title}>
            <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{g.title}</h3>
            <dl className="divide-y divide-slate-800/70">
              {g.items.map((s) => {
                const hit = anchor !== undefined && s.keys === anchor;
                return (
                  <div key={s.keys + s.label} className={["flex items-start gap-3 rounded px-1 py-1.5", hit ? "bg-accent-500/10" : ""].join(" ")}>
                    <dt className="w-44 shrink-0 pt-px">
                      <kbd className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">{s.keys}</kbd>
                    </dt>
                    <dd className="text-xs text-slate-400">{s.label}</dd>
                  </div>
                );
              })}
            </dl>
          </section>
        ))}
      </div>
      {groups.length === 0 && <p className="text-xs text-slate-500">No chord matches “{filter}”.</p>}
    </div>
  );
}
