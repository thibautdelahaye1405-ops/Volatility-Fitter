// Nodes pane (UI SHELL v2, S2): the universe as a tree, right of the
// activity bar, 1/5 of the screen by default (resizable, Ctrl+B).
//
//   TICKER group   chevron · ticker · "lit/total" · amber "≠ as-of" pill when
//                  any expiry is served off the selected as-of · hover:
//                  lit-all / dark-all
//   expiry row     lit/dark dot (click = toggle designation, shared with the
//                  Graph canvas + Universe dialog) · expiry · tenor · HH:MM of
//                  the chain serving the node (NodeAsOfCell; amber when
//                  inexact) · RMS bp · quality glyph (ready / stale / arb /
//                  no fit)
//
// Single click = preview tab, double click / middle click = pinned tab (VS
// Code). Ctrl+P opens the quick-open palette over the same list. The active
// tab's row is highlighted. A filter box + "lit only" toggle narrow the tree;
// ⚙ opens the Universe dialog (add / remove tickers, expiry selection).
//
// Keyboard (wave 3, C1 — lib/treeNav): the tree is ONE tab stop with a roving
// focused row (aria-activedescendant, outlined): ↑/↓ move, ←/→ collapse /
// expand a ticker (→ enters it, ← climbs back), Home/End, letters type-ahead
// to the next ticker, Enter = preview tab, Shift+Enter / Space = pinned tab,
// Ctrl+Enter = open in the other editor group (split; C3), L = toggle
// lit/dark, Tab = the filter box. Ctrl+B (show) focuses the tree.
// Drag (wave 3, C5 — lib/nodeDnd): a row can be dragged onto the Graph
// canvas (lights it / pulses it) or onto the tab strip (pinned tab).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ChevronDown, ChevronRight, Filter, Settings2 } from "lucide-react";
import { useSmileSession } from "../../state/smileSession";
import { useWorkbench } from "../../state/workbench";
import { useLitMap } from "../../state/litMap";
import { useQualityReport } from "../../state/qualityContext";
import { useExpiryFormat } from "../../state/expiryFormat";
import { formatExpiry } from "../../lib/expiryFormat";
import { tabKey } from "../../lib/workbenchTabs";
import { EMPTY_TYPEAHEAD, groupId, treeKeyAction } from "../../lib/treeNav";
import { NODE_MIME, encodeNodeDrag } from "../../lib/nodeDnd";
import type { TreeRow, TypeAhead } from "../../lib/treeNav";
import type { QualityNode } from "../../state/useQuality";
import { AsOfMismatchPill, NodeAsOfCell } from "./NodeAsOfCell";

/** Quality glyph colour + tooltip for a node row. */
function glyphOf(q: QualityNode | undefined): { dot: string; title: string } {
  if (q === undefined) return { dot: "bg-slate-700", title: "no quality data" };
  if (!q.hasFit) return { dot: "bg-slate-600", title: "no fit yet" };
  if (!q.leeOk || !q.calendarOk || q.butterflyCertified === false)
    return { dot: "bg-rose-500", title: `arbitrage flag · ${q.issues.join(", ")}` };
  if (q.stale) return { dot: "bg-amber-400", title: "stale — inputs changed since the last calibration" };
  if (q.ready) return { dot: "bg-emerald-500", title: "publish-ready" };
  return { dot: "bg-amber-300", title: q.issues.join(", ") || "not ready" };
}

const iconBtn =
  "rounded p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200";
/** Outline of the keyboard-focused row (only while the tree has focus). */
const focusRing = "ring-1 ring-inset ring-accent-400/70";
/** DOM id of a row (aria-activedescendant target). */
const rowDomId = (id: string) => `nodes-row-${id.replace(/[^a-zA-Z0-9]/g, "_")}`;

export default function NodesPane() {
  const { universe, source } = useSmileSession();
  const wb = useWorkbench();
  const lit = useLitMap();
  const { nodeOf } = useQualityReport();
  const { format } = useExpiryFormat();
  const [query, setQuery] = useState("");
  const [litOnly, setLitOnly] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [treeFocused, setTreeFocused] = useState(false);
  const typeahead = useRef<TypeAhead>(EMPTY_TYPEAHEAD);
  const treeRef = useRef<HTMLDivElement | null>(null);
  const filterRef = useRef<HTMLInputElement | null>(null);

  const tickers = universe?.tickers ?? [];
  const q = query.trim().toUpperCase();
  const activeKey = wb.activeTab?.key ?? null;
  const openKeys = useMemo(() => new Set(wb.tabs.map((t) => t.key)), [wb.tabs]);
  const live = source === "live";

  const setGroup = (t: string, expanded: boolean) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (expanded) next.delete(t);
      else next.add(t);
      return next;
    });

  // Visible rows: ticker groups (filtered) + the expiry rows of expanded ones.
  const groups = useMemo(
    () =>
      tickers
        .map((ticker) => {
          const ladder = universe?.expiries[ticker] ?? [];
          const rows = ladder.filter((r) => {
            const isLit = lit.litOf(ticker, r.expiry);
            if (litOnly && isLit !== true) return false;
            if (q === "") return true;
            return ticker.includes(q) || r.expiry.includes(q) || formatExpiry(r.expiry, r.t, format).toUpperCase().includes(q);
          });
          return { ticker, ladder, rows, open: !collapsed.has(ticker) };
        })
        .filter((g) => g.rows.length > 0 || q === ""),
    [tickers, universe, lit, litOnly, q, format, collapsed],
  );
  const flat = useMemo<TreeRow[]>(
    () =>
      groups.flatMap((g) => [
        { id: groupId(g.ticker), kind: "group" as const, ticker: g.ticker, expanded: g.open },
        ...(g.open ? g.rows.map((r) => ({ id: tabKey(g.ticker, r.expiry), kind: "node" as const, ticker: g.ticker, expiry: r.expiry })) : []),
      ]),
    [groups],
  );
  // Keep the focused row valid; default it to the active tab (or the first row).
  const focusValid = focusedId !== null && flat.some((r) => r.id === focusedId);
  const effectiveFocus = focusValid ? focusedId : (activeKey !== null && flat.some((r) => r.id === activeKey) ? activeKey : (flat[0]?.id ?? null));

  // Ctrl+B (show) → focus the tree (workbench.focusNodesPane bumps the seq).
  useEffect(() => {
    if (wb.nodesFocusSeq > 0) treeRef.current?.focus();
  }, [wb.nodesFocusSeq]);
  // Scroll the focused row into view while navigating.
  useEffect(() => {
    if (!treeFocused || effectiveFocus === null) return;
    document.getElementById(rowDomId(effectiveFocus))?.scrollIntoView?.({ block: "nearest" });
  }, [effectiveFocus, treeFocused]);

  const onTreeKey = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const r = treeKeyAction(flat, effectiveFocus, e, typeahead.current, Date.now());
      typeahead.current = r.typeahead;
      const a = r.action;
      if (a === null) return;
      e.preventDefault();
      switch (a.type) {
        case "focus": setFocusedId(a.id); break;
        case "expand": setGroup(a.ticker, a.expanded); setFocusedId(groupId(a.ticker)); break;
        case "open":
          setFocusedId(tabKey(a.ticker, a.expiry));
          if (a.mode === "split") wb.openBeside({ ticker: a.ticker, expiry: a.expiry });
          else wb.openNode({ ticker: a.ticker, expiry: a.expiry }, { preview: a.mode === "preview" });
          break;
        case "lit": if (live) lit.toggleNode(a.ticker, a.expiry); break;
        case "filter": filterRef.current?.focus(); break;
      }
    },
    [flat, effectiveFocus, wb, live, lit],
  );

  const nodeCount = tickers.reduce((n, t) => n + (universe?.expiries[t] ?? []).length, 0);
  const litCount = lit.nodes.filter((n) => n.lit).length;

  return (
    <aside
      aria-label="Nodes"
      data-tour="nodes"
      className="flex min-w-0 shrink-0 flex-col border-r border-slate-800 bg-surface-950"
      style={{ width: wb.layout.nodesWidth }}
    >
      {/* Header */}
      <div className="flex h-9 shrink-0 items-center gap-1 px-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Nodes</span>
        <span className="truncate text-[10px] text-slate-600" title="tickers · nodes · lit">
          {tickers.length} · {nodeCount}
          {live ? ` · ${litCount} lit` : ""}
        </span>
        <span className="ml-auto flex items-center">
          <button
            className={`${iconBtn} ${litOnly ? "text-accent-400" : ""}`}
            title="Show lit (observed) nodes only"
            aria-pressed={litOnly}
            onClick={() => setLitOnly((v) => !v)}
          >
            <Filter size={13} strokeWidth={1.75} />
          </button>
          <button
            className={iconBtn}
            title="Manage universe — add / remove tickers, choose expiries, saved universes"
            onClick={() => wb.openDialog("universe")}
          >
            <Settings2 size={13} strokeWidth={1.75} />
          </button>
        </span>
      </div>
      <div className="shrink-0 px-2 pb-1.5">
        <input
          ref={filterRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter nodes…"
          aria-label="Filter nodes"
          className="w-full rounded-md border border-slate-800 bg-surface-900 px-2 py-1 text-[11px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-accent-500"
        />
      </div>

      {/* Tree: one tab stop, roving focused row */}
      <div
        ref={treeRef}
        role="tree"
        tabIndex={0}
        aria-label="Universe nodes"
        aria-activedescendant={effectiveFocus !== null ? rowDomId(effectiveFocus) : undefined}
        onKeyDown={onTreeKey}
        onFocus={() => setTreeFocused(true)}
        onBlur={() => setTreeFocused(false)}
        className="min-h-0 flex-1 overflow-y-auto pb-2 outline-none"
      >
        {universe === null && (
          <p className="px-3 py-2 text-[11px] text-slate-500">Loading universe…</p>
        )}
        {groups.map(({ ticker, ladder, rows, open }) => {
          const litN = ladder.filter((r) => lit.litOf(ticker, r.expiry) === true).length;
          const activeHere = wb.activeTab?.ticker === ticker;
          const gid = groupId(ticker);
          const gFocused = treeFocused && effectiveFocus === gid;
          return (
            <div key={ticker} role="treeitem" id={rowDomId(gid)} aria-expanded={open} aria-selected={false}>
              <div
                className={[
                  "group flex h-7 items-center gap-1 pr-2 pl-1 text-xs",
                  activeHere ? "text-slate-100" : "text-slate-300",
                  gFocused ? focusRing : "",
                ].join(" ")}
              >
                <button
                  tabIndex={-1}
                  className="flex min-w-0 flex-1 items-center gap-1 text-left"
                  onClick={() => { setGroup(ticker, !open); setFocusedId(gid); }}
                  title={open ? "Collapse" : "Expand"}
                >
                  {open ? (
                    <ChevronDown size={13} className="shrink-0 text-slate-600" />
                  ) : (
                    <ChevronRight size={13} className="shrink-0 text-slate-600" />
                  )}
                  <span className="truncate font-mono font-semibold">{ticker}</span>
                  {live && (
                    <span className="ml-1 font-mono text-[10px] text-slate-600">
                      {litN}/{ladder.length}
                    </span>
                  )}
                  {ladder.some((r) => r.asOfExact === false) && <AsOfMismatchPill />}
                </button>
                {live && (
                  <span className="hidden shrink-0 gap-0.5 group-hover:flex">
                    <button tabIndex={-1}
                      className="rounded border border-slate-800 px-1 text-[9px] text-accent-300 hover:border-accent-500/50"
                      title="Light every expiry (observed)"
                      onClick={() => lit.setTicker(ticker, true)}
                    >
                      lit
                    </button>
                    <button tabIndex={-1}
                      className="rounded border border-slate-800 px-1 text-[9px] text-slate-500 hover:border-slate-600"
                      title="Darken every expiry (extrapolated)"
                      onClick={() => lit.setTicker(ticker, false)}
                    >
                      dark
                    </button>
                  </span>
                )}
              </div>

              {open &&
                rows.map((r) => {
                  const key = tabKey(ticker, r.expiry);
                  const isActive = key === activeKey;
                  const isOpen = openKeys.has(key);
                  const isLit = lit.litOf(ticker, r.expiry);
                  const qn = nodeOf(ticker, r.expiry);
                  const g = glyphOf(qn);
                  const rFocused = treeFocused && effectiveFocus === key;
                  return (
                    <div
                      key={key}
                      id={rowDomId(key)}
                      role="treeitem"
                      aria-selected={isActive}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData(NODE_MIME, encodeNodeDrag({ ticker, expiry: r.expiry }));
                        e.dataTransfer.setData("text/plain", `${ticker} ${r.expiry}`);
                        e.dataTransfer.effectAllowed = "copyLink";
                      }}
                      onClick={() => { setFocusedId(key); wb.openNode({ ticker, expiry: r.expiry }, { preview: true }); }}
                      onDoubleClick={() => wb.openNode({ ticker, expiry: r.expiry })}
                      onAuxClick={(e) => {
                        // Middle-click = pinned tab (VS Code's open-in-background).
                        if (e.button === 1) wb.openNode({ ticker, expiry: r.expiry });
                      }}
                      className={[
                        "flex h-6 cursor-pointer items-center gap-1.5 pr-2 pl-5 text-[11px] transition-colors",
                        isActive
                          ? "bg-accent-500/10 text-slate-100"
                          : isOpen
                            ? "text-slate-200 hover:bg-slate-800/50"
                            : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200",
                        rFocused ? focusRing : "",
                      ].join(" ")}
                    >
                      {isActive && <span className="-ml-5 mr-3 h-4 w-0.5 rounded-r bg-accent-400" />}
                      {/* Lit/dark designation dot */}
                      <button
                        tabIndex={-1}
                        aria-label={isLit ? "lit (observed) — click to darken" : "dark (extrapolated) — click to light"}
                        title={
                          isLit === undefined
                            ? "designation unavailable"
                            : isLit
                              ? "lit — observed source for the graph solver (click to darken · L)"
                              : "dark — extrapolated by the graph solver (click to light · L)"
                        }
                        disabled={isLit === undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          lit.toggleNode(ticker, r.expiry);
                        }}
                        className={[
                          "h-2.5 w-2.5 shrink-0 rounded-full border transition-colors",
                          isLit === undefined
                            ? "border-slate-700"
                            : isLit
                              ? "border-accent-400 bg-accent-400 shadow-[0_0_6px_rgba(56,189,248,0.6)]"
                              : "border-slate-600 hover:border-slate-400",
                        ].join(" ")}
                      />
                      <span className="truncate font-mono">{formatExpiry(r.expiry, r.t, format)}</span>
                      <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-600">
                        {r.t < 0.1 ? `${Math.round(r.t * 365)}d` : `${r.t.toFixed(2)}y`}
                      </span>
                      <NodeAsOfCell row={r} />
                      {qn?.hasFit && (
                        <span className="w-8 shrink-0 text-right font-mono text-[10px] text-slate-500" title="RMS fit error (bp)">
                          {qn.rmsBp.toFixed(0)}
                        </span>
                      )}
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${g.dot}`} title={g.title} />
                    </div>
                  );
                })}
            </div>
          );
        })}
        {universe !== null && tickers.length === 0 && (
          <p className="px-3 py-2 text-[11px] text-slate-500">
            Universe is empty — add tickers via ⚙.
          </p>
        )}
      </div>
    </aside>
  );
}
