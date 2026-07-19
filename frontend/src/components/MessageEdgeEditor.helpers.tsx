// Row + scenario-preview subcomponents of the MessageEdgeEditor (split out to
// keep both files under the size policy).
//
// Direction is UNAMBIGUOUS everywhere here: source (informer) → target
// (receiver), arrows drawn in the direction information flows. Confidence is
// entered in the U1 default lens — relationship uncertainty σ_edge = 1/√p in
// VOL POINTS (raw precision behind the editor's units toggle). Calendar rows
// surface the reciprocal reverse identities (spec §7.6/§8.3): implied reverse
// amplitude 1/β and implied reverse uncertainty σ/|β| (= precision p·β²).
import { useMemo, useState } from "react";
import PrecisionField from "./PrecisionField";
import {
  receiverPreview,
  reverseBeta,
  reversePrecision,
  type PreviewMessage,
} from "../lib/messagePreview";
import { fmtSigmaPts, relationSentence } from "../lib/precisionUnits";
import type { SolverParams } from "../state/useGraph";
import {
  RELATION_CLASSES,
  type MessageEdgeRow,
  type RelationClass,
} from "../state/useMessageEdges";

export const numCls =
  "w-14 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right " +
  "font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500";
export const selCls =
  "rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono " +
  "text-[10px] text-slate-100 outline-none focus:border-accent-500";

export const short = (ticker: string, expiry: string) =>
  `${ticker} ${expiry.slice(5)}`;
export const rowKey = (r: MessageEdgeRow) =>
  `${r.sourceTicker}|${r.sourceExpiry}>${r.targetTicker}|${r.targetExpiry}`;

/** ρ of a relation class under the current amplitude knobs (spec §8.4). */
export function rhoOf(cls: RelationClass, params: SolverParams): number {
  return cls === "calendar" ? params.ampCal : params.ampCross;
}

/** One editable relation row. `inherited` = seeded from auto and untouched;
 *  `raw` = show precisions instead of the σ-pts default lens. */
export function EdgeRow({
  row,
  inherited,
  params,
  raw,
  onChange,
  onDelete,
}: {
  row: MessageEdgeRow;
  inherited: boolean;
  params: SolverParams;
  raw: boolean;
  onChange: (patch: Partial<MessageEdgeRow>) => void;
  onDelete: () => void;
}) {
  const derived = row.precisionRule === "calendar_distance";
  const sentence = relationSentence({
    sourceLabel: short(row.sourceTicker, row.sourceExpiry),
    targetLabel: short(row.targetTicker, row.targetExpiry),
    beta: row.betaAtmVol,
    precision: row.messagePrecision,
    rho: rhoOf(row.relationClass, params),
  });
  const num = (
    value: number,
    patch: (v: number) => Partial<MessageEdgeRow>,
    step: number,
    title: string,
    disabled = false,
  ) => (
    <input
      type="number"
      step={step}
      value={value}
      title={title}
      disabled={disabled}
      onChange={(e) => {
        const v = e.target.valueAsNumber;
        if (Number.isFinite(v)) onChange(patch(v));
      }}
      className={numCls + (disabled ? " italic opacity-50" : "")}
    />
  );
  return (
    <div className="flex items-center gap-1 py-1">
      {/* Sentence tooltip (U1): what a +1pt informer move does through THIS
          factor, and how uncertain the relationship is. */}
      <span
        className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-300"
        title={sentence}
      >
        {short(row.sourceTicker, row.sourceExpiry)}{" "}
        <span className="text-accent-400">→</span>{" "}
        {short(row.targetTicker, row.targetExpiry)}
        {inherited && (
          <span className="ml-1 rounded bg-surface-800 px-1 text-[8px] uppercase tracking-wide text-slate-500">
            auto
          </span>
        )}
      </span>
      <select
        className={selCls}
        value={row.relationClass}
        title="Relation class (drives the amplitude multiplier ρ)"
        onChange={(e) => onChange({ relationClass: e.target.value as RelationClass })}
      >
        {RELATION_CLASSES.map((c) => (
          <option key={c} value={c}>
            {c.replace("_", " ")}
          </option>
        ))}
      </select>
      <button
        className={
          "rounded px-1 py-0.5 text-[9px] " +
          (derived
            ? "bg-accent-600/20 text-accent-300"
            : "bg-surface-800 text-slate-500 hover:text-slate-300")
        }
        title={
          derived
            ? "Precision derives from the maturity-gap rule at solve time (click to lock the shown number)"
            : "Explicit precision (click to derive from the maturity-gap rule instead)"
        }
        onClick={() =>
          onChange({
            precisionRule: derived ? "explicit" : "calendar_distance",
          })
        }
      >
        {derived ? "dist" : "expl"}
      </button>
      <PrecisionField
        precision={row.messagePrecision}
        raw={raw}
        onChange={(p) => onChange({ messagePrecision: p, precisionRule: "explicit" })}
        className={numCls}
        titleSigma={
          derived
            ? "Distance-derived relationship uncertainty σ = 1/√p, vol pts (today's value; editing locks it explicit)"
            : "Relationship uncertainty σ_edge = 1/√p (vol pts) — lower = tighter coupling"
        }
        titleRaw={
          derived
            ? "Distance-derived precision (today's value; editing locks it explicit)"
            : "Conditional relation precision p (receiver ATM-vol units, 1/vol²)"
        }
      />
      {num(row.betaAtmVol, (v) => ({ betaAtmVol: v }), 0.1, "β ATM vol")}
      {num(row.betaSkew, (v) => ({ betaSkew: v }), 0.1, "β skew")}
      {num(row.betaCurv, (v) => ({ betaCurv: v }), 0.1, "β curvature")}
      <span
        className="w-20 shrink-0 truncate text-right font-mono text-[9px] text-slate-600"
        title="Implied reverse identities of this ONE-factor relation: amplitude 1/β, relationship uncertainty σ/|β| (= precision p·β²; spec §7.6/§8.3)"
      >
        ⇐ {reverseBeta(row.betaAtmVol).toFixed(2)} ·{" "}
        {raw
          ? Math.round(reversePrecision(row.messagePrecision, row.betaAtmVol))
          : `${fmtSigmaPts(reversePrecision(row.messagePrecision, row.betaAtmVol))}pt`}
      </span>
      <button
        className="w-4 text-slate-500 hover:text-rose-300"
        title="Remove relation"
        onClick={onDelete}
      >
        ×
      </button>
    </div>
  );
}

/**
 * Deterministic scenario preview (spec §20.4, the Phase-5 exit gate): pick a
 * receiver, type informer innovations, read the EXACT conditional mean and
 * incoming precision the configured rows imply — the same math the solver
 * runs (lib/messagePreview, vitest-locked to the golden §21 numbers).
 */
export function ScenarioPreview({
  rows,
  params,
  raw,
}: {
  rows: MessageEdgeRow[];
  params: SolverParams;
  raw: boolean;
}) {
  const receivers = useMemo(() => {
    const seen = new Map<string, { ticker: string; expiry: string }>();
    for (const r of rows)
      seen.set(`${r.targetTicker}|${r.targetExpiry}`, {
        ticker: r.targetTicker,
        expiry: r.targetExpiry,
      });
    return [...seen.entries()];
  }, [rows]);
  const [receiver, setReceiver] = useState<string>("");
  const active = receiver !== "" ? receiver : (receivers[0]?.[0] ?? "");
  const incoming = useMemo(
    () => rows.filter((r) => `${r.targetTicker}|${r.targetExpiry}` === active),
    [rows, active],
  );
  // Informer innovations in VOL POINTS, keyed by the incoming row.
  const [z, setZ] = useState<Record<string, number>>({});

  if (receivers.length === 0) return null;
  const messages: PreviewMessage[] = incoming.map((r) => ({
    beta: r.betaAtmVol,
    precision: r.messagePrecision,
    z: (z[rowKey(r)] ?? 0) / 100,
    rho: rhoOf(r.relationClass, params),
  }));
  const out = receiverPreview(messages);

  return (
    <div className="mt-2 rounded-md border border-slate-800 bg-surface-800/50 p-2">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Scenario preview
        </span>
        <select
          className={selCls}
          value={active}
          onChange={(e) => setReceiver(e.target.value)}
          title="The previewed receiver node"
        >
          {receivers.map(([k, n]) => (
            <option key={k} value={k}>
              {short(n.ticker, n.expiry)}
            </option>
          ))}
        </select>
      </div>
      <div className="mb-1.5 space-y-1">
        {incoming.map((r) => (
          <label
            key={rowKey(r)}
            className="flex items-center justify-between gap-2 text-[10px] text-slate-400"
          >
            <span className="min-w-0 truncate font-mono">
              z({short(r.sourceTicker, r.sourceExpiry)}) · β{" "}
              {r.betaAtmVol.toFixed(2)} ·{" "}
              {raw
                ? `p ${Math.round(r.messagePrecision)}`
                : `σ ${fmtSigmaPts(r.messagePrecision)}pt`}
            </span>
            <span className="flex items-center gap-1">
              <input
                type="number"
                step={0.5}
                value={z[rowKey(r)] ?? 0}
                onChange={(e) => {
                  const v = e.target.valueAsNumber;
                  if (Number.isFinite(v))
                    setZ((prev) => ({ ...prev, [rowKey(r)]: v }));
                }}
                className={numCls}
              />
              <span className="text-slate-600">pts</span>
            </span>
          </label>
        ))}
      </div>
      <p className="font-mono text-[10px] text-slate-300" data-testid="preview-out">
        mean{" "}
        <span className="text-accent-300">
          {(out.mean * 100).toFixed(3)} pts
        </span>
        <span title="Incoming message confidence q = Σp — the receiver conditional (§7.6)">
          {" · incoming confidence q "}
          <span className="text-slate-200">{out.q.toFixed(0)}</span>
        </span>
        {" · anchor κ "}
        <span className="text-slate-200">{out.kappa.toFixed(0)}</span>
        {" · cond sd "}
        <span className="text-slate-200">
          {(out.conditionalSd * 100).toFixed(2)} pts
        </span>
      </p>
      <p className="mt-1 text-[9px] text-slate-600">
        Conditional on the typed informers (clamped); the FINAL posterior
        confidence is the solved marginal — it adds source uncertainty and
        cross-route covariance on top.
      </p>
    </div>
  );
}
