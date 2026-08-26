// Node tab strip of the main pane (UI SHELL v2, S2): one tab per open node
// (ticker · expiry), VS Code semantics — preview tabs italic, double-click
// pins, middle-click / × closes, drag to reorder, right-click context menu
// (close / close others / close all / pin). A quality glyph per tab shows
// stale (amber) or arb-flagged (rose) fits at a glance.
import { useState } from "react";
import type { DragEvent, MouseEvent } from "react";
import { X } from "lucide-react";
import { useWorkbench } from "../../state/workbench";
import { useExpiryFormat } from "../../state/expiryFormat";
import { useQualityReport } from "../../state/qualityContext";
import { useSmileSession } from "../../state/smileSession";
import { formatExpiry } from "../../lib/expiryFormat";
import type { WorkbenchTab } from "../../lib/workbenchTabs";
import { MenuDivider, MenuItem } from "../topbar/Menu";

interface Ctx {
  key: string;
  x: number;
  y: number;
}

export default function TabStrip() {
  const wb = useWorkbench();
  const { format } = useExpiryFormat();
  const { universe } = useSmileSession();
  const { nodeOf } = useQualityReport();
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [dragKey, setDragKey] = useState<string | null>(null);

  /** Year-fraction of a node from the universe ladders (label formatting). */
  const tOf = (t: WorkbenchTab): number =>
    universe?.expiries[t.ticker]?.find((r) => r.expiry === t.expiry)?.t ?? 0;

  const onDrop = (e: DragEvent<HTMLElement>, targetKey: string) => {
    e.preventDefault();
    if (dragKey === null || dragKey === targetKey) return;
    const idx = wb.tabs.findIndex((t) => t.key === targetKey);
    wb.moveTab(dragKey, idx);
    setDragKey(null);
  };

  const onContext = (e: MouseEvent, key: string) => {
    e.preventDefault();
    setCtx({ key, x: e.clientX, y: e.clientY });
  };

  return (
    <div
      role="tablist"
      aria-label="Open nodes"
      className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-slate-800 bg-surface-950"
    >
      {wb.tabs.length === 0 && (
        <span className="flex items-center px-3 text-[11px] text-slate-600">
          No node open — click one in the Nodes pane
        </span>
      )}
      {wb.tabs.map((t) => {
        const active = t.key === wb.activeTab?.key;
        const q = nodeOf(t.ticker, t.expiry);
        const arb = q !== undefined && q.hasFit && (!q.leeOk || !q.calendarOk);
        const glyph = arb ? "bg-rose-500" : q?.stale ? "bg-amber-400" : null;
        return (
          <div
            key={t.key}
            role="tab"
            aria-selected={active}
            draggable
            onDragStart={() => setDragKey(t.key)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, t.key)}
            onClick={() => wb.activateTab(t.key)}
            onDoubleClick={() => wb.pinTab(t.key)}
            onAuxClick={(e) => {
              if (e.button === 1) wb.closeTab(t.key);
            }}
            onContextMenu={(e) => onContext(e, t.key)}
            title={`${t.ticker} ${t.expiry}${t.preview ? " · preview (double-click to pin)" : ""}${
              q?.issues.length ? ` · ${q.issues.join(", ")}` : ""
            }`}
            className={[
              "group relative flex max-w-56 shrink-0 cursor-pointer select-none items-center gap-1.5",
              "border-r border-slate-800 pl-3 pr-1.5 text-xs transition-colors",
              active
                ? "bg-surface-900 text-slate-100"
                : "text-slate-400 hover:bg-surface-900/60 hover:text-slate-200",
            ].join(" ")}
          >
            {active && <span className="absolute inset-x-0 top-0 h-0.5 bg-accent-400" />}
            {glyph && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${glyph}`} />}
            <span className={["truncate", t.preview ? "italic" : ""].join(" ")}>
              <span className="font-semibold">{t.ticker}</span>{" "}
              <span className="font-mono text-[11px] opacity-80">
                {formatExpiry(t.expiry, tOf(t), format)}
              </span>
            </span>
            <button
              aria-label={`Close ${t.ticker} ${t.expiry}`}
              title="Close (Alt+W · middle-click)"
              onClick={(e) => {
                e.stopPropagation();
                wb.closeTab(t.key);
              }}
              className={[
                "rounded p-0.5 text-slate-500 transition-colors hover:bg-slate-700/60 hover:text-slate-100",
                active ? "opacity-70" : "opacity-0 group-hover:opacity-70",
              ].join(" ")}
            >
              <X size={12} strokeWidth={2} />
            </button>
          </div>
        );
      })}

      {/* Context menu (anchored at the pointer). */}
      {ctx !== null && (
        <>
          <button className="fixed inset-0 z-30 cursor-default" aria-hidden onClick={() => setCtx(null)} />
          <div
            className="fixed z-40 w-44 rounded-lg border border-slate-700 bg-surface-800 py-1 shadow-xl shadow-black/40"
            style={{ left: ctx.x, top: ctx.y }}
          >
            {wb.tabs.find((t) => t.key === ctx.key)?.preview && (
              <MenuItem label="Keep open (pin)" onClick={() => { wb.pinTab(ctx.key); setCtx(null); }} />
            )}
            <MenuItem label="Close" detail="Alt+W" onClick={() => { wb.closeTab(ctx.key); setCtx(null); }} />
            <MenuItem label="Close others" onClick={() => { wb.closeOthers(ctx.key); setCtx(null); }} />
            <MenuDivider />
            <MenuItem label="Close all" onClick={() => { wb.closeAll(); setCtx(null); }} />
          </div>
        </>
      )}
    </div>
  );
}
