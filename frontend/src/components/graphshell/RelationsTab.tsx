// Relations drawer tab (GRAPH ERGONOMICS ARC, E5): every arrow of the canvas
// as a row — search, class filter, sort, click-to-select (the canvas glows
// the arrow, the inspector opens the slider card), × removes. The toolbar
// carries the draft actions: undo / redo, seed from the auto relations,
// reset to auto, the templates menu and the door to the §20 full editor
// (per-handle grid + the golden scenario preview).
import { useMemo, useState } from "react";
import { Redo2, Undo2 } from "lucide-react";
import RelationTemplatesMenu from "./RelationTemplatesMenu";
import { BETA_CAP } from "../../lib/calendarPolicy";
import { fmtSigmaPts } from "../../lib/precisionUnits";
import { relationKey, type NodeRef } from "../../lib/relationRows";
import type { SolverParams } from "../../state/useGraph";
import type { RelationClass } from "../../state/useMessageEdges";
import type { RelationDraft } from "../../state/useRelationDraft";

interface RelationsTabProps {
  draft: RelationDraft;
  params: SolverParams;
  raw: boolean;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  /** Selected-universe nodes (templates). */
  nodes: NodeRef[];
  onOpenFullEditor: () => void;
}

type SortKey = "informer" | "receiver" | "sigma" | "beta";
const CLASS_LABEL: Record<RelationClass, string> = {
  calendar: "calendar",
  broad_index: "index",
  sector_etf: "etf",
  sector_peer: "peer",
  custom: "custom",
};
const short = (ticker: string, expiry: string) => `${ticker} ${expiry.slice(5)}`;
const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";
const chip = (on: boolean) =>
  "rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors " +
  (on ? "bg-accent-600/25 text-accent-300" : "text-slate-500 hover:text-slate-300");

export default function RelationsTab({
  draft,
  params,
  raw,
  selectedKey,
  onSelect,
  nodes,
  onOpenFullEditor,
}: RelationsTabProps) {
  const [query, setQuery] = useState("");
  const [cls, setCls] = useState<RelationClass | "all">("all");
  const [sort, setSort] = useState<SortKey>("informer");

  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    const list = draft.rows.filter(
      (r) =>
        (cls === "all" || r.relationClass === cls) &&
        (q === "" ||
          `${r.sourceTicker} ${r.sourceExpiry} ${r.targetTicker} ${r.targetExpiry}`.toUpperCase().includes(q)),
    );
    const by: Record<SortKey, (a: typeof list[number], b: typeof list[number]) => number> = {
      informer: (a, b) => `${a.sourceTicker}${a.sourceExpiry}`.localeCompare(`${b.sourceTicker}${b.sourceExpiry}`),
      receiver: (a, b) => `${a.targetTicker}${a.targetExpiry}`.localeCompare(`${b.targetTicker}${b.targetExpiry}`),
      sigma: (a, b) => b.messagePrecision - a.messagePrecision,
      beta: (a, b) => Math.abs(b.betaAtmVol) - Math.abs(a.betaAtmVol),
    };
    return list.slice().sort(by[sort]);
  }, [draft.rows, query, cls, sort]);

  const counts = useMemo(() => {
    const c: Partial<Record<RelationClass, number>> = {};
    for (const r of draft.rows) c[r.relationClass] = (c[r.relationClass] ?? 0) + 1;
    return c;
  }, [draft.rows]);

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="relations-tab">
      {/* Toolbar */}
      <div className="mb-1.5 flex shrink-0 flex-wrap items-center gap-1.5">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search ticker / expiry"
          className="w-40 rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] text-slate-200 outline-none focus:border-accent-500"
          data-testid="relations-search"
        />
        <span className="flex items-center gap-0.5 rounded-md border border-slate-800 p-0.5">
          <button className={chip(cls === "all")} onClick={() => setCls("all")}>all {draft.rows.length}</button>
          {(Object.keys(CLASS_LABEL) as RelationClass[])
            .filter((c) => (counts[c] ?? 0) > 0)
            .map((c) => (
              <button key={c} className={chip(cls === c)} onClick={() => setCls(c)}>
                {CLASS_LABEL[c]} {counts[c]}
              </button>
            ))}
        </span>
        <select
          className="rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 font-mono text-[10px] text-slate-300 outline-none focus:border-accent-500"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          title="Sort"
        >
          <option value="informer">by informer</option>
          <option value="receiver">by receiver</option>
          <option value="sigma">by confidence</option>
          <option value="beta">by |β|</option>
        </select>
        <span className="rounded bg-surface-800 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-slate-500" title="Where the rows on screen come from: the staged draft, the active config, or the auto relations the solve would build">
          {draft.source}
          {draft.saving ? " · saving…" : ""}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <button className={btn} disabled={!draft.canUndo} onClick={draft.undo} title="Undo (Ctrl+Z)" data-testid="relations-undo">
            <Undo2 size={12} strokeWidth={1.75} />
          </button>
          <button className={btn} disabled={!draft.canRedo} onClick={draft.redo} title="Redo (Ctrl+Y)" data-testid="relations-redo">
            <Redo2 size={12} strokeWidth={1.75} />
          </button>
          <button className={btn} onClick={() => void draft.seedAuto()} title="Load the auto relations (calendar ladders + cross pairs) as editable rows">
            Seed auto
          </button>
          <button className={btn} onClick={() => void draft.resetAuto()} title="Stage an empty draft — the solve goes back to the auto relations">
            Reset to auto
          </button>
          <RelationTemplatesMenu
            ctx={{ nodes, rows: draft.rows, crossPrecision: params.crossPrecision }}
            onApply={(rows) => draft.replaceAll(rows)}
          />
          <button className={btn} onClick={onOpenFullEditor} title="The full relation grid: per-handle β, the golden scenario preview">
            Full editor
          </button>
        </span>
      </div>
      {draft.error !== null && (
        <p className="mb-1 truncate text-[10px] text-amber-400/80" title={draft.error}>{draft.error}</p>
      )}

      {/* Rows */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <p className="py-2 text-[11px] text-slate-500">
            {draft.rows.length === 0
              ? "No relations — use the Connect tool on the canvas, seed the auto relations, or apply a template."
              : "No relation matches the filter."}
          </p>
        ) : (
          <table className="w-full border-collapse font-mono text-[10px]">
            <thead className="sticky top-0 bg-surface-900 text-[9px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-0.5 text-left font-normal">informer → receiver</th>
                <th className="py-0.5 text-left font-normal">class</th>
                <th className="py-0.5 text-right font-normal" title="Relationship uncertainty σ (vol pts) or raw precision p">{raw ? "p" : "σ pt"}</th>
                <th className="py-0.5 text-right font-normal">β</th>
                <th className="py-0.5 text-right font-normal" title="auto = precision follows the maturity-distance rule">rule</th>
                <th className="w-5" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const key = relationKey(r);
                const selected = key === selectedKey;
                const capped = Math.abs(r.betaAtmVol) > BETA_CAP;
                return (
                  <tr
                    key={key}
                    onClick={() => onSelect(key)}
                    data-relation-row={key}
                    className={
                      "cursor-pointer border-t border-slate-800/60 transition-colors hover:bg-surface-800/50 " +
                      (selected ? "bg-accent-600/15" : "")
                    }
                  >
                    <td className="py-1 text-slate-300">
                      {short(r.sourceTicker, r.sourceExpiry)} <span className="text-accent-400">→</span>{" "}
                      {short(r.targetTicker, r.targetExpiry)}
                    </td>
                    <td className="py-1 text-slate-500">{CLASS_LABEL[r.relationClass]}</td>
                    <td className="py-1 text-right text-slate-300">
                      {raw ? Math.round(r.messagePrecision) : fmtSigmaPts(r.messagePrecision)}
                    </td>
                    <td className={"py-1 text-right " + (capped ? "text-amber-300" : "text-slate-300")}>
                      {r.betaAtmVol.toFixed(2)}
                      {(r.betaSkew !== r.betaAtmVol || r.betaCurv !== r.betaAtmVol) && (
                        <span className="text-slate-600" title={`β skew ${r.betaSkew.toFixed(2)} · β curv ${r.betaCurv.toFixed(2)}`}>*</span>
                      )}
                    </td>
                    <td className="py-1 text-right text-slate-600">{r.precisionRule === "calendar_distance" ? "auto" : "expl"}</td>
                    <td className="py-1 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          draft.remove(key);
                        }}
                        title="Remove relation"
                        className="px-0.5 text-slate-500 hover:text-rose-300"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
