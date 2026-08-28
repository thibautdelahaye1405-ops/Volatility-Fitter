// Node tab strip of ONE editor group (UI SHELL v2, S2 / wave 3 C3): one tab
// per open node (ticker · expiry), VS Code semantics — preview tabs italic,
// double-click pins, middle-click / × closes, drag to reorder, right-click
// context menu (close / close others / close all / pin / move to another
// group — one row per other group when three are open). Pinned tabs carry a
// pin glyph, preview tabs are italic + muted; a quality glyph per tab shows
// stale (amber) or arb-flagged (rose) fits. A node dragged from the Nodes
// pane and dropped on the strip opens as a PINNED tab in this group; dragging
// a tab onto the main pane's right 20 % splits, onto its bottom 20 % splits
// down (the workbench's draggingTab feeds those zones). The unfocused groups'
// strips read dimmer.
import { useState } from "react";
import type { DragEvent, MouseEvent } from "react";
import { Pin, X } from "lucide-react";
import { useWorkbench } from "../../state/workbench";
import { useExpiryFormat } from "../../state/expiryFormat";
import { useQualityReport } from "../../state/qualityContext";
import { useRootSmileSession } from "../../state/smileSession";
import { formatExpiry } from "../../lib/expiryFormat";
import type { WorkbenchTab } from "../../lib/workbenchTabs";
import { NODE_MIME, decodeNodeDrag, isNodeDrag, routeNodeDrop } from "../../lib/nodeDnd";
import { MenuDivider, MenuItem } from "../topbar/Menu";

interface Ctx {
  key: string;
  x: number;
  y: number;
}

export default function TabStrip({ group = 0 }: { group?: number }) {
  const wb = useWorkbench();
  const { format } = useExpiryFormat();
  const { universe } = useRootSmileSession();
  const { nodeOf } = useQualityReport();
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const g = wb.groups[group];
  const tabs = g?.tabs.tabs ?? [];
  const activeKey = g?.tabs.activeKey ?? null;
  const focused = wb.focusedGroup === group;
  const split = wb.groups.length > 1;
  const other = split ? (group + 1) % wb.groups.length : -1; // the next group along the axis (the other one while two)

  /** Year-fraction of a node from the universe ladders (label formatting). */
  const tOf = (t: WorkbenchTab): number =>
    universe?.expiries[t.ticker]?.find((r) => r.expiry === t.expiry)?.t ?? 0;

  /** A node from the Nodes pane dropped anywhere on the strip → pinned tab here. */
  const dropNode = (e: DragEvent<HTMLElement>): boolean => {
    const node = decodeNodeDrag(e.dataTransfer.getData(NODE_MIME));
    if (!node) return false;
    e.preventDefault();
    const a = routeNodeDrop("tabstrip", node, { manual: false });
    if (a.type === "openTab") wb.openNodeIn(group, { ticker: a.ticker, expiry: a.expiry });
    return true;
  };
  const onDrop = (e: DragEvent<HTMLElement>, targetKey: string) => {
    if (dropNode(e)) return;
    e.preventDefault();
    const dragKey = wb.draggingTab;
    if (dragKey === null || dragKey === targetKey) return;
    if (!tabs.some((t) => t.key === dragKey)) { wb.moveTabToGroup(dragKey, group); wb.setDraggingTab(null); return; }
    wb.moveTab(dragKey, tabs.findIndex((t) => t.key === targetKey));
    wb.setDraggingTab(null);
  };
  const onContext = (e: MouseEvent, key: string) => {
    e.preventDefault();
    setCtx({ key, x: e.clientX, y: e.clientY });
  };

  return (
    <div
      role="tablist"
      aria-label={split ? `Open nodes (group ${group + 1})` : "Open nodes"}
      data-drop-zone="tabstrip"
      onDragOver={(e) => { if (isNodeDrag(e.dataTransfer.types) || wb.draggingTab !== null) e.preventDefault(); }}
      onDrop={(e) => { if (!dropNode(e) && wb.draggingTab !== null && !tabs.some((t) => t.key === wb.draggingTab)) { e.preventDefault(); wb.moveTabToGroup(wb.draggingTab, group); wb.setDraggingTab(null); } }}
      className={[
        "flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-slate-800 bg-surface-950",
        split && !focused ? "opacity-70" : "",
      ].join(" ")}
    >
      {tabs.length === 0 && (
        <span className="flex items-center px-3 text-[11px] text-slate-600">
          No node open — click one in the Nodes pane
        </span>
      )}
      {tabs.map((t) => {
        const active = t.key === activeKey;
        const q = nodeOf(t.ticker, t.expiry);
        const arb = q !== undefined && q.hasFit && (!q.leeOk || !q.calendarOk);
        const glyph = arb ? "bg-rose-500" : q?.stale ? "bg-amber-400" : null;
        return (
          <div
            key={t.key}
            role="tab"
            aria-selected={active}
            draggable
            onDragStart={() => wb.setDraggingTab(t.key)}
            onDragEnd={() => wb.setDraggingTab(null)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, t.key)}
            onClick={() => wb.activateTab(t.key)}
            onDoubleClick={() => wb.pinTab(t.key)}
            onAuxClick={(e) => { if (e.button === 1) wb.closeTab(t.key); }}
            onContextMenu={(e) => onContext(e, t.key)}
            title={`${t.ticker} ${t.expiry}${t.preview ? " · preview (double-click to pin)" : ""}${q?.issues.length ? ` · ${q.issues.join(", ")}` : ""}`}
            className={[
              "group relative flex max-w-56 shrink-0 cursor-pointer select-none items-center gap-1.5",
              "border-r border-slate-800 pl-3 pr-1.5 text-xs transition-colors",
              active ? "bg-surface-900 text-slate-100" : "text-slate-400 hover:bg-surface-900/60 hover:text-slate-200",
            ].join(" ")}
          >
            {active && <span className={`absolute inset-x-0 top-0 h-0.5 ${focused || !split ? "bg-accent-400" : "bg-slate-600"}`} />}
            {glyph && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${glyph}`} />}
            {!t.preview && <Pin size={10} strokeWidth={2} className="shrink-0 text-slate-500" />}
            <span className={["truncate", t.preview ? "italic opacity-80" : ""].join(" ")}>
              <span className="font-semibold">{t.ticker}</span>{" "}
              <span className="font-mono text-[11px] opacity-80">{formatExpiry(t.expiry, tOf(t), format)}</span>
            </span>
            <button
              aria-label={`Close ${t.ticker} ${t.expiry}`}
              title="Close (Alt+W · middle-click)"
              onClick={(e) => { e.stopPropagation(); wb.closeTab(t.key); }}
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
          <div className="fixed z-40 w-52 rounded-lg border border-slate-700 bg-surface-800 py-1 shadow-xl shadow-black/40" style={{ left: ctx.x, top: ctx.y }}>
            {tabs.find((t) => t.key === ctx.key)?.preview && (
              <MenuItem label="Keep open (pin)" onClick={() => { wb.pinTab(ctx.key); setCtx(null); }} />
            )}
            {wb.groups.length > 2 ? (
              wb.groups.map((_, i) => i !== group && (
                <MenuItem key={i} label={`Move to group ${i + 1}`} onClick={() => { wb.moveTabToGroup(ctx.key, i); setCtx(null); }} />
              ))
            ) : (
              <MenuItem label={split ? "Move to the other group" : "Open to the side (split)"} detail="Ctrl+\\"
                onClick={() => {
                  if (split) wb.moveTabToGroup(ctx.key, other);
                  else { wb.split(); wb.moveTabToGroup(ctx.key, group + 1); }
                  setCtx(null);
                }} />
            )}
            {!split && (
              <MenuItem label="Open below (split down)" detail="Ctrl+Shift+\\"
                onClick={() => { wb.splitDown(); wb.moveTabToGroup(ctx.key, group + 1); setCtx(null); }} />
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
