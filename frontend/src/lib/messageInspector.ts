// Message-inspector math (P5b U4): the client-side view of ONE receiver's
// incoming messages, computed from the effective relation rows (persisted
// else auto) + the extrapolate response — the same quantities the solver
// uses, so the inspector's local consensus is the EXACT receiver conditional
// (lib/messagePreview.receiverPreview, golden-locked) and any gap to the
// solved field is genuinely "source uncertainty + shared routes".
//
// One-factor semantics honored: a row whose SOURCE is the receiver is read in
// reverse (amplitude 1/β, precision p·β² — spec §7.6/§8.3). Distance-rule
// precisions derive with the RECEIVER ticker's effective calendar policy
// (U2), and a policy-disabled ticker suppresses its calendar factors —
// mirroring backend graph_message exactly.
import { effectiveCalendarPolicy } from "./calendarPolicy";
import {
  calendarPrecision,
  receiverPreview,
  type PreviewResult,
} from "./messagePreview";
import { sigmaPtsFromPrecision } from "./precisionUnits";
import { nodeKey, type SolverParams } from "../state/useGraph";
import type { ExtrapolateNode } from "../state/useGraphExtrapolation";
import type { MessageEdgeRow, RelationClass } from "../state/useMessageEdges";

/** One incoming message at the inspected receiver, display-ready. */
export interface IncomingRelation {
  informerTicker: string;
  informerExpiry: string;
  relationClass: RelationClass;
  /** Directed ATM amplitude toward the receiver. */
  beta: number;
  /** Effective conditional precision (distance rules derived; reverse p·β²). */
  precision: number;
  sigmaPts: number;
  /** Amplitude multiplier ρ of the class (§8.4). */
  rho: number;
  /** True when this is the reverse read of a persisted one-factor row. */
  implied: boolean;
  /** Informer's posterior ATM innovation (decimal vol), or null if unknown. */
  z: number | null;
  /** The raw vote β·z in vol points, or null without an innovation. */
  mappedPts: number | null;
}

/** ρ of a relation class under the current amplitude knobs (spec §8.4). */
export function rhoOfClass(cls: RelationClass, params: SolverParams): number {
  return cls === "calendar" ? params.ampCal : params.ampCross;
}

/** Effective precision of a row read TOWARD its target (receiver units). */
function effectivePrecision(
  row: MessageEdgeRow,
  tReceiver: number | undefined,
  tInformer: number | undefined,
  params: SolverParams,
): number {
  if (
    row.precisionRule === "calendar_distance" &&
    tReceiver !== undefined &&
    tInformer !== undefined
  ) {
    const policy = effectiveCalendarPolicy(params, row.targetTicker);
    return calendarPrecision(
      tReceiver, tInformer, policy.scale, params.calEpsilon, params.calDecay,
    );
  }
  return row.messagePrecision;
}

/**
 * The receiver's incoming messages from the effective relation rows + the
 * solved response nodes (t lookup + informer innovations).
 */
export function incomingRelations(
  receiver: { ticker: string; expiry: string },
  rows: MessageEdgeRow[],
  nodes: ExtrapolateNode[],
  params: SolverParams,
): IncomingRelation[] {
  const byKey = new Map(nodes.map((n) => [nodeKey(n.ticker, n.expiry), n]));
  const out: IncomingRelation[] = [];
  const push = (
    informerTicker: string,
    informerExpiry: string,
    row: MessageEdgeRow,
    implied: boolean,
  ) => {
    // Policy suppression mirrors the backend: a disabled calendar policy on
    // the RECEIVER's ticker kills its calendar-class factors.
    if (
      row.relationClass === "calendar" &&
      !effectiveCalendarPolicy(params, receiver.ticker).enabled
    ) {
      return;
    }
    const tR = byKey.get(nodeKey(receiver.ticker, receiver.expiry))?.t;
    const tI = byKey.get(nodeKey(informerTicker, informerExpiry))?.t;
    // Effective precision is quoted toward the ROW's target; the reverse
    // read then applies the §7.6 identity p·β² (and amplitude 1/β).
    const pForward = effectivePrecision(row, implied ? tI : tR, implied ? tR : tI, params);
    const beta = implied
      ? row.betaAtmVol === 0
        ? 0
        : 1 / row.betaAtmVol
      : row.betaAtmVol;
    const precision = implied ? pForward * row.betaAtmVol * row.betaAtmVol : pForward;
    const informer = byKey.get(nodeKey(informerTicker, informerExpiry));
    const z = informer !== undefined ? (informer.postAtmVol - informer.priorAtmVol) : null;
    out.push({
      informerTicker,
      informerExpiry,
      relationClass: row.relationClass,
      beta,
      precision,
      sigmaPts: sigmaPtsFromPrecision(precision),
      rho: rhoOfClass(row.relationClass, params),
      implied,
      z,
      mappedPts: z === null ? null : beta * z * 100,
    });
  };

  for (const row of rows) {
    const isTarget =
      row.targetTicker === receiver.ticker && row.targetExpiry === receiver.expiry;
    const isSource =
      row.sourceTicker === receiver.ticker && row.sourceExpiry === receiver.expiry;
    if (isTarget && !isSource) push(row.sourceTicker, row.sourceExpiry, row, false);
    else if (isSource && !isTarget) push(row.targetTicker, row.targetExpiry, row, true);
  }
  return out;
}

/** The exact receiver conditional over the incoming messages (informers with
 *  no known innovation vote 0 — their precision still counts toward q). */
export function receiverConsensus(relations: IncomingRelation[]): PreviewResult {
  return receiverPreview(
    relations.map((r) => ({
      beta: r.beta,
      precision: r.precision,
      z: r.z ?? 0,
      rho: r.rho,
    })),
  );
}
