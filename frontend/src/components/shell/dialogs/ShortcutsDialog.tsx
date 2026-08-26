// Help ▸ Keyboard shortcuts (UI SHELL v2): the documented chord table,
// grouped — rendered from lib/shortcuts.ts so it always matches the handler.
import Dialog from "../Dialog";
import { SHORTCUT_GROUPS } from "../../../lib/shortcuts";

export default function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Keyboard shortcuts"
      subtitle="Browser-reserved chords (Ctrl+digits, Ctrl+W, Ctrl+PgUp/PgDn) are avoided on purpose"
      width="w-[min(96vw,52rem)]"
      height="h-[min(84vh,44rem)]"
    >
      <div className="grid h-full grid-cols-1 gap-x-8 gap-y-5 overflow-y-auto p-5 md:grid-cols-2">
        {SHORTCUT_GROUPS.map((g) => (
          <section key={g.title}>
            <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              {g.title}
            </h3>
            <dl className="divide-y divide-slate-800/70">
              {g.items.map((s) => (
                <div key={s.keys + s.label} className="flex items-center gap-3 py-1.5">
                  <dt className="w-44 shrink-0">
                    <kbd className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                      {s.keys}
                    </kbd>
                  </dt>
                  <dd className="text-xs text-slate-400">{s.label}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
