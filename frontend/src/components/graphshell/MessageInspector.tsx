// Message inspector (P5b U4): the selected RECEIVER's incoming messages and
// the local-vs-global story, plus the edge-click relation card.
//
//   Incoming messages — one row per effective relation factor reaching the
//     receiver (direct or the ⇐ implied reverse of a one-factor row):
//     informer, its posterior innovation z, β, the mapped vote β·z, and the
//     relationship uncertainty σ_edge.
//   Local consensus — the EXACT receiver conditional over those messages
//     (lib/messageInspector → golden-locked receiverPreview math).
//   Global posterior — what the solved field actually says (the marginal is
//     authoritative), with the divergence explainer when the two differ.
import { Grid3x3 } from "lucide-react";
import { crossCell } from "./CrossMatrixCard";
import {
  incomingRelations,
  receiverConsensus,
  rhoOfClass,
} from "../../lib/messageInspector";
import { calendarBeta, calendarPrecision } from "../../lib/messagePreview";
import { effectiveCalendarPolicy } from "../../lib/calendarPolicy";
import { fmtSigmaPts, relationSentence } from "../../lib/precisionUnits";
import { nodeKey, type SolverParams } from "../../state/useGraph";
import type { ExtrapolateNode } from "../../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../../state/useMessageEdges";
import type { GraphEdgeSelection } from "../GraphNetworkChart";

const short = (ticker: string, expiry: string) => `${ticker} ${expiry.slice(5)}`;

/** The receiver-side message view for one selected node. */
export function MessageInspector({
  receiver,
  rows,
  nodes,
  params,
}: {
  receiver: ExtrapolateNode;
  rows: MessageEdgeRow[];
  nodes: ExtrapolateNode[];
  params: SolverParams;
}) {
  const relations = incomingRelations(receiver, rows, nodes, params);
  if (relations.length === 0) return null;
  const consensus = receiverConsensus(relations);
  const condMeanBp = consensus.mean * 1e4;
  const diverges = Math.abs(condMeanBp - receiver.shiftBp) > 0.5;

  return (
    <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/50 p-2">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Incoming messages · {relations.length}
      </p>
      <div className="mb-2 divide-y divide-slate-800/60">
        {relations.map((r, i) => (
          <p
            key={i}
            className="truncate py-0.5 font-mono text-[10px] text-slate-400"
            title={
              relationSentence({
                sourceLabel: short(r.informerTicker, r.informerExpiry),
                targetLabel: short(receiver.ticker, receiver.expiry),
                beta: r.beta,
                precision: r.precision,
                rho: r.rho,
              }) +
              ` · ${r.relationClass.replace("_", " ")}` +
              (r.implied ? " · implied reverse of the persisted factor (1/β, p·β²)" : "")
            }
          >
            {r.implied && <span className="text-slate-600">⇐ </span>}
            <span className="text-slate-300">{short(r.informerTicker, r.informerExpiry)}</span>
            {" · z "}
            {r.z === null ? "—" : `${r.z >= 0 ? "+" : ""}${(r.z * 100).toFixed(2)}`}
            {" · β "}
            {r.beta.toFixed(2)}
            {r.mappedPts !== null && (
              <>
                {" → "}
                <span className={r.mappedPts >= 0 ? "text-emerald-400" : "text-rose-400"}>
                  {r.mappedPts >= 0 ? "+" : ""}
                  {r.mappedPts.toFixed(2)}pt
                </span>
              </>
            )}
            {" · σ "}
            {fmtSigmaPts(r.precision)}pt
          </p>
        ))}
      </div>

      {/* Local conditional vs the solved global — the U1 taxonomy verbatim. */}
      <p
        className="font-mono text-[10px] text-slate-300"
        title="The exact receiver conditional over the messages above (informers without a solved innovation vote 0; their precision still counts)."
      >
        local{" "}
        <span className="text-accent-300">
          {condMeanBp >= 0 ? "+" : ""}
          {condMeanBp.toFixed(1)} bp
        </span>
        {" · incoming confidence q "}
        <span className="text-slate-200">{consensus.q.toFixed(0)}</span>
        {" · cond σ "}
        <span className="text-slate-200">
          {(consensus.conditionalSd * 100).toFixed(2)} pt
        </span>
      </p>
      <p
        className="font-mono text-[10px] text-slate-300"
        title="Final posterior confidence — the solved marginal (authoritative)."
      >
        final{" "}
        <span className="text-accent-300">
          {receiver.shiftBp >= 0 ? "+" : ""}
          {receiver.shiftBp.toFixed(1)} bp
        </span>
        {" · ±"}
        <span className="text-slate-200">{(receiver.sd * 1e4).toFixed(0)} bp</span>
        {" · 95% ["}
        {(receiver.bandLo * 100).toFixed(1)}–{(receiver.bandHi * 100).toFixed(1)}%]
        {receiver.qIncoming !== null && (
          <span className="text-slate-500"> · wire q {receiver.qIncoming.toFixed(0)}</span>
        )}
      </p>
      {diverges && (
        <p className="mt-1 text-[9px] text-slate-500">
          Local ≠ final: the marginal folds in informer (source) uncertainty
          and shared-route covariance — trust the final.
        </p>
      )}
    </div>
  );
}

/** The edge-click relation card: a calendar pair or a cross ticker pair. */
export function EdgeInspectorCard({
  edge,
  rows,
  nodes,
  params,
  messages,
  onClose,
  onEditRelations,
}: {
  edge: GraphEdgeSelection;
  rows: MessageEdgeRow[];
  nodes: ExtrapolateNode[] | null;
  params: SolverParams;
  messages: boolean;
  onClose: () => void;
  onEditRelations: () => void;
}) {
  let body: React.ReactNode;
  if (!messages) {
    body = (
      <p className="text-[10px] text-slate-500">
        Smooth-field coupling — weights live in the Relationships cards;
        per-edge overrides under Edges.
      </p>
    );
  } else if (edge.kind === "cross") {
    // Both directions of the ticker pair via the U2 matrix resolution.
    body = (
      <div className="space-y-0.5">
        {[
          { receiver: edge.a, informer: edge.b },
          { receiver: edge.b, informer: edge.a },
        ].map(({ receiver, informer }) => {
          const cell = crossCell(rows, receiver, informer, params.crossPrecision);
          return (
            <p
              key={receiver}
              className="font-mono text-[10px] text-slate-400"
              title={relationSentence({
                sourceLabel: informer,
                targetLabel: receiver,
                beta: cell.beta,
                precision: cell.precision,
                rho: params.ampCross,
              })}
            >
              <span className="text-slate-300">{receiver}</span>
              {" ← "}
              {informer} · β {cell.beta.toFixed(2)} · σ {fmtSigmaPts(cell.precision)}pt
              <span className="text-slate-600"> · {cell.provenance}</span>
            </p>
          );
        })}
      </div>
    );
  } else {
    // Calendar pair: canonical receiver = the SHORTER expiry (ISO sorts
    // chronologically). Persisted row wins; else the auto policy relation.
    const [shortIso, longIso] = [edge.aExpiry, edge.bExpiry].sort();
    const row = rows.find(
      (r) =>
        r.relationClass === "calendar" &&
        ((r.targetTicker === edge.ticker &&
          r.targetExpiry === shortIso &&
          r.sourceExpiry === longIso) ||
          (r.sourceTicker === edge.ticker &&
            r.sourceExpiry === shortIso &&
            r.targetExpiry === longIso)),
    );
    const byKey = new Map((nodes ?? []).map((n) => [nodeKey(n.ticker, n.expiry), n]));
    const tS = byKey.get(nodeKey(edge.ticker, shortIso ?? ""))?.t;
    const tL = byKey.get(nodeKey(edge.ticker, longIso ?? ""))?.t;
    const policy = effectiveCalendarPolicy(params, edge.ticker);
    const beta =
      row !== undefined
        ? row.betaAtmVol
        : tS !== undefined && tL !== undefined
          ? calendarBeta(tS, tL, policy.alphaT)
          : 1;
    const precision =
      row !== undefined && row.precisionRule === "explicit"
        ? row.messagePrecision
        : tS !== undefined && tL !== undefined
          ? calendarPrecision(tS, tL, policy.scale, params.calEpsilon, params.calDecay)
          : params.calPrecision;
    body = !policy.enabled ? (
      <p className="text-[10px] text-slate-500">
        Calendar messages are OFF for {edge.ticker} (policy) — this relation
        carries nothing.
      </p>
    ) : (
      <p
        className="font-mono text-[10px] text-slate-400"
        title={relationSentence({
          sourceLabel: short(edge.ticker, longIso ?? ""),
          targetLabel: short(edge.ticker, shortIso ?? ""),
          beta,
          precision,
          rho: rhoOfClass("calendar", params),
        })}
      >
        <span className="text-slate-300">{short(edge.ticker, shortIso ?? "")}</span>
        {" ← "}
        {short(edge.ticker, longIso ?? "")} · β {beta.toFixed(2)} · σ{" "}
        {fmtSigmaPts(precision)}pt
        <span className="text-slate-600">
          {" "}
          · {row !== undefined ? "persisted" : "auto"} · ⇐ {beta === 0 ? "—" : (1 / beta).toFixed(2)}
        </span>
      </p>
    );
  }

  return (
    <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/60 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-slate-200">
          {edge.kind === "cross"
            ? `Relation · ${edge.a} ↔ ${edge.b}`
            : `Relation · ${edge.ticker} calendar`}
        </span>
        <button
          onClick={onClose}
          title="Close relation card"
          className="shrink-0 px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
        >
          ×
        </button>
      </div>
      {body}
      {messages && (
        <button
          onClick={onEditRelations}
          className="mt-1.5 flex items-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[10px] font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
          title="Open the row-level relation editor"
        >
          <Grid3x3 size={11} strokeWidth={1.75} className="opacity-80" />
          Edit relations
        </button>
      )}
    </div>
  );
}
