// Relation templates menu (GRAPH ERGONOMICS ARC, E5): one-click playbooks
// over the selected universe — Hub → names (a broad index informing every
// other ticker, directed in Layered), Peers ⇄ (one reciprocal factor per
// ticker pair and shared expiry), Calendar only (drop every cross relation).
// Applies through lib/relationTemplates onto the draft; nothing here persists
// on its own.
import { useState } from "react";
import { TEMPLATES, applyTemplate, contextTickers, type TemplateContext, type TemplateId } from "../../lib/relationTemplates";
import type { MessageEdgeRow } from "../../state/useMessageEdges";

interface RelationTemplatesMenuProps {
  ctx: Omit<TemplateContext, "hub">;
  onApply: (rows: MessageEdgeRow[]) => void;
}

const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

export default function RelationTemplatesMenu({ ctx, onApply }: RelationTemplatesMenuProps) {
  const [open, setOpen] = useState(false);
  const tickers = contextTickers(ctx);
  const [hub, setHub] = useState("");
  const activeHub = hub !== "" ? hub : (tickers[0] ?? "");

  const apply = (id: TemplateId) => {
    onApply(applyTemplate(id, { ...ctx, hub: activeHub }));
    setOpen(false);
  };

  return (
    <div className="relative">
      <button className={btn} onClick={() => setOpen((v) => !v)} title="Relation playbooks over the selected universe" data-testid="templates-menu">
        Templates ▾
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-72 rounded-md border border-slate-700 bg-surface-800 p-2 shadow-xl shadow-black/40">
          {TEMPLATES.map((t) => (
            <div key={t.id} className="mb-1.5 flex items-start gap-2 last:mb-0">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-medium text-slate-200">{t.label}</p>
                <p className="text-[10px] text-slate-500">{t.description}</p>
                {t.needsHub && (
                  <select
                    className="mt-1 rounded border border-slate-700 bg-surface-900 px-1 py-0.5 font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500"
                    value={activeHub}
                    onChange={(e) => setHub(e.target.value)}
                    title="The hub (informer) ticker"
                  >
                    {tickers.map((tk) => (
                      <option key={tk} value={tk}>
                        {tk}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <button
                className={btn + " shrink-0"}
                disabled={t.needsHub && activeHub === ""}
                onClick={() => apply(t.id)}
                data-testid={`template-${t.id}`}
              >
                Apply
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
