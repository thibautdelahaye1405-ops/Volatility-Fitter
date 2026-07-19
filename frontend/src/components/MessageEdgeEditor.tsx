// Message relation editor (message arc P5 — the full spec-§20 scope): every
// relation factor is one row with explicit precision, per-handle betas,
// relation class, and inherited-vs-explicit provenance; grouped by class,
// seeded from the auto relations, with the deterministic scenario preview
// (spec §20.4) showing the exact conditional mean/precision a configuration
// implies BEFORE saving — the Phase-5 exit gate.
//
// Persisted under its own blob (PUT /graph/edges/messages); an empty save
// clears back to the auto relations. The legacy weight/beta matrix editor
// remains the smooth-field surface — the two topologies never mix.
import { useEffect, useMemo, useState } from "react";
import {
  EdgeRow,
  ScenarioPreview,
  selCls,
  short,
} from "./MessageEdgeEditor.helpers";
import type { SolverParams } from "../state/useGraph";
import {
  useMessageEdges,
  type MessageEdgeRow,
  type RelationClass,
} from "../state/useMessageEdges";

interface MessageEdgeEditorProps {
  /** Selected-universe nodes, for the add-relation pickers. */
  nodes: { ticker: string; expiry: string }[];
  params: SolverParams;
  /** Called after a successful save/clear so the parent can re-solve. */
  onSaved?: () => void;
  onClose: () => void;
}

const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

const CLASS_ORDER: RelationClass[] = [
  "calendar",
  "broad_index",
  "sector_etf",
  "sector_peer",
  "custom",
];

interface EditRow {
  row: MessageEdgeRow;
  /** Seeded from the auto relations and not yet touched. */
  inherited: boolean;
}

const nodeKeyOf = (n: { ticker: string; expiry: string }) =>
  `${n.ticker}|${n.expiry}`;

export default function MessageEdgeEditor({
  nodes,
  params,
  onSaved,
  onClose,
}: MessageEdgeEditorProps) {
  const { fetchEdges, fetchAuto, putEdges } = useMessageEdges();
  const [rows, setRows] = useState<EditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [cls, setCls] = useState<RelationClass>("custom");
  // U1 units lens: default = relationship uncertainty σ_edge (vol pts);
  // the raw conditional precision p sits behind this toggle.
  const [raw, setRaw] = useState(false);

  useEffect(() => {
    fetchEdges()
      .then((e) => setRows(e.map((row) => ({ row, inherited: false }))))
      .catch((e: unknown) => setError(String(e)));
  }, [fetchEdges]);

  useEffect(() => {
    if (source === "" && nodes[0]) setSource(nodeKeyOf(nodes[0]));
    if (target === "" && nodes[1]) setTarget(nodeKeyOf(nodes[1]));
  }, [nodes, source, target]);

  const run = (p: Promise<MessageEdgeRow[]>, opts: { persisted?: boolean; inherited?: boolean }) => {
    setBusy(true);
    setError(null);
    p.then((e) => {
      setRows(e.map((row) => ({ row, inherited: opts.inherited === true })));
      if (opts.persisted === true) onSaved?.();
    })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setBusy(false));
  };

  const update = (index: number, patch: Partial<MessageEdgeRow>) =>
    setRows((r) =>
      r.map((e, j) =>
        j === index ? { row: { ...e.row, ...patch }, inherited: false } : e,
      ),
    );

  const addRow = () => {
    const [st, se] = source.split("|");
    const [tt, te] = target.split("|");
    if (!st || !se || !tt || !te || (st === tt && se === te)) return;
    setRows((r) => [
      ...r,
      {
        inherited: false,
        row: {
          sourceTicker: st, sourceExpiry: se,
          targetTicker: tt, targetExpiry: te,
          messagePrecision: cls === "calendar" ? 1000 : 13000,
          betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
          relationClass: cls,
          precisionRule: cls === "calendar" ? "calendar_distance" : "explicit",
        },
      },
    ]);
  };

  const grouped = useMemo(() => {
    const by = new Map<RelationClass, { index: number; entry: EditRow }[]>();
    rows.forEach((entry, index) => {
      const list = by.get(entry.row.relationClass) ?? [];
      list.push({ index, entry });
      by.set(entry.row.relationClass, list);
    });
    return CLASS_ORDER.filter((c) => by.has(c)).map((c) => ({
      cls: c,
      items: by.get(c) ?? [],
    }));
  }, [rows]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6">
      <div className="flex max-h-[85vh] w-[860px] max-w-full flex-col rounded-xl border border-slate-700 bg-surface-900 p-4 shadow-2xl shadow-black/50">
        <div className="mb-2 flex shrink-0 items-center gap-2">
          <span className="text-sm font-semibold text-slate-100">
            Message relations
          </span>
          <span className="text-[10px] text-slate-500">
            source (informer) → target (receiver) · one factor per relation
          </span>
          <button
            className="ml-auto rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[9px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
            onClick={() => setRaw((v) => !v)}
            title="Confidence units: relationship uncertainty σ = 1/√p in vol points (default) vs the raw conditional precision p (1/vol²)"
          >
            {raw ? "units: raw p" : "units: σ pts"}
          </button>
          <button
            className="text-slate-500 hover:text-slate-200"
            onClick={onClose}
            title="Close"
          >
            ✕
          </button>
        </div>

        <div className="mb-2 flex shrink-0 flex-wrap gap-1.5">
          <button
            className={btn}
            disabled={busy}
            onClick={() => run(fetchAuto(), { inherited: true })}
            title="Load the auto relations (calendar ladders + cross pairs) as editable rows"
          >
            Seed from auto relations
          </button>
          <button
            className={btn}
            disabled={busy}
            onClick={() => run(putEdges(rows.map((r) => r.row)), { persisted: true })}
          >
            Save
          </button>
          <button
            className={btn}
            disabled={busy}
            onClick={() => run(putEdges([]), { persisted: true })}
            title="Clear the persisted rules — the solve builds its auto relations again"
          >
            Reset to auto
          </button>
        </div>
        {error !== null && (
          <p className="mb-1 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </p>
        )}

        {/* Column header */}
        <div className="flex shrink-0 items-center gap-1 px-0.5 text-[9px] uppercase tracking-wide text-slate-500">
          <span className="flex-1">relation (informer → receiver)</span>
          <span className="w-20">class</span>
          <span className="w-8">rule</span>
          <span
            className="w-14 text-right"
            title="Relationship uncertainty σ_edge = 1/√p of this ONE factor (vol pts); toggle for the raw precision p"
          >
            {raw ? "precision" : "uncert (pt)"}
          </span>
          <span className="w-14 text-right">β atm</span>
          <span className="w-14 text-right">β skew</span>
          <span className="w-14 text-right">β curv</span>
          <span className="w-20 text-right" title="Implied reverse amplitude 1/β and precision p·β²">
            implied ⇐
          </span>
          <span className="w-4" />
        </div>

        {/* Rows, grouped by relation class */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {rows.length === 0 ? (
            <p className="py-2 text-[11px] text-slate-500">
              No persisted rules — the solve builds its auto relations
              (calendar ladders + same-expiry cross pairs). Seed from them to
              edit, or add relations below.
            </p>
          ) : (
            grouped.map((g) => (
              <div key={g.cls}>
                <p className="mt-1.5 text-[9px] font-semibold uppercase tracking-wide text-slate-600">
                  {g.cls.replace("_", " ")} · {g.items.length}
                </p>
                <div className="divide-y divide-slate-800/60">
                  {g.items.map(({ index, entry }) => (
                    <EdgeRow
                      key={index}
                      row={entry.row}
                      inherited={entry.inherited}
                      params={params}
                      raw={raw}
                      onChange={(patch) => update(index, patch)}
                      onDelete={() =>
                        setRows((r) => r.filter((_, j) => j !== index))
                      }
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Add relation */}
        <div className="mt-2 flex shrink-0 items-center gap-1 border-t border-slate-800 pt-2">
          <select
            className={selCls + " flex-1"}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            title="Source (informer)"
          >
            {nodes.map((n) => (
              <option key={nodeKeyOf(n)} value={nodeKeyOf(n)}>
                {short(n.ticker, n.expiry)}
              </option>
            ))}
          </select>
          <span className="text-[10px] text-accent-400" title="information flow">
            →
          </span>
          <select
            className={selCls + " flex-1"}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            title="Target (receiver)"
          >
            {nodes.map((n) => (
              <option key={nodeKeyOf(n)} value={nodeKeyOf(n)}>
                {short(n.ticker, n.expiry)}
              </option>
            ))}
          </select>
          <select
            className={selCls}
            value={cls}
            onChange={(e) => setCls(e.target.value as RelationClass)}
            title="Relation class"
          >
            {CLASS_ORDER.map((c) => (
              <option key={c} value={c}>
                {c.replace("_", " ")}
              </option>
            ))}
          </select>
          <button className={btn} onClick={addRow}>
            Add
          </button>
        </div>

        {/* Deterministic scenario preview (the exit-gate surface) */}
        <ScenarioPreview rows={rows.map((r) => r.row)} params={params} raw={raw} />
      </div>
    </div>
  );
}
