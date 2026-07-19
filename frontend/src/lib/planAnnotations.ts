// Observation-plan annotations (P5b U7): WHY a ranked next-quote candidate is
// valuable, derived from the solved field + the effective relations —
//
//   bridges   — the candidate sits in a no-lit-path component (§14.3): quoting
//               it lights an otherwise unobserved region.
//   weak      — its incoming message confidence q is far below the field's
//               typical level (bottom of the distribution): the posterior
//               there leans on little.
//   competing — its incoming messages disagree (opposite-sign votes of real
//               size): observing it adjudicates the §21.2/§21.3 average.
import { incomingRelations } from "./messageInspector";
import type { SolverParams } from "../state/useGraph";
import type { ExtrapolateNode } from "../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../state/useMessageEdges";

export interface PlanAnnotation {
  id: "bridges" | "weak" | "competing";
  label: string;
  title: string;
}

/** q below this fraction of the non-observed median counts as weak. */
const WEAK_Q_FRACTION = 0.25;
/** Opposite-sign votes must both exceed this size (vol pts) to "compete". */
const COMPETING_MIN_PTS = 0.1;

export function planAnnotations(
  candidate: { ticker: string; expiry: string },
  nodes: ExtrapolateNode[] | null,
  rows: MessageEdgeRow[],
  params: SolverParams,
  messages: boolean,
): PlanAnnotation[] {
  if (nodes === null) return [];
  const node = nodes.find(
    (n) => n.ticker === candidate.ticker && n.expiry === candidate.expiry,
  );
  if (node === undefined) return [];
  const out: PlanAnnotation[] = [];

  if (node.noLitPath === true) {
    out.push({
      id: "bridges",
      label: "bridges",
      title:
        "Bridges an unobserved region: this node's component has no path to " +
        "an observation (§14.3) — quoting it lights the whole island.",
    });
  } else if (messages && node.qIncoming !== null) {
    const qs = nodes
      .filter((n) => !n.calibrated && n.qIncoming !== null)
      .map((n) => n.qIncoming as number)
      .sort((a, b) => a - b);
    const median = qs.length > 0 ? (qs[Math.floor(qs.length / 2)] as number) : 0;
    if (median > 0 && node.qIncoming < median * WEAK_Q_FRACTION) {
      out.push({
        id: "weak",
        label: "weakly connected",
        title:
          "Weakly connected: incoming message confidence q far below the " +
          "field's typical level — the posterior here leans on little.",
      });
    }
  }

  if (messages) {
    const votes = incomingRelations(candidate, rows, nodes, params)
      .map((r) => r.mappedPts)
      .filter((v): v is number => v !== null);
    const pos = votes.some((v) => v > COMPETING_MIN_PTS);
    const neg = votes.some((v) => v < -COMPETING_MIN_PTS);
    if (pos && neg) {
      out.push({
        id: "competing",
        label: "resolves competing signals",
        title:
          "Its incoming messages disagree (opposite-sign votes) — the " +
          "posterior is a precision-weighted average (§21.2/§21.3); observing " +
          "this node adjudicates.",
      });
    }
  }
  return out;
}
