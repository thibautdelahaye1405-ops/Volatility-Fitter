// U6 message-config lifecycle client: the draft/active envelope pair
// (GET /graph/config/messages), the Activate/Revert actions, and the
// client-side draft-vs-active row diff that drives the config chip's dirty
// badge. The editor keeps its own row endpoints (they read/write the DRAFT
// since U6); the SOLVE uses the active rows unless the run-draft toggle ships
// useDraftConfig.
import { api } from "./api";
import type { MessageEdgeRow } from "./useMessageEdges";

export interface MessageConfigEnvelope {
  name: string;
  version: number;
  createdAt: string;
  author: string;
  parentVersion: number | null;
  notes: string;
  rows: MessageEdgeRow[];
}

export interface MessageConfigPair {
  draft: MessageConfigEnvelope | null;
  active: MessageConfigEnvelope | null;
}

export function fetchMessageConfig(): Promise<MessageConfigPair> {
  return api.get<MessageConfigPair>("/graph/config/messages");
}

export function activateMessageConfig(notes: string): Promise<MessageConfigPair> {
  return api.post<MessageConfigPair>("/graph/config/messages/activate", {
    body: { notes },
  });
}

export function revertMessageConfig(): Promise<MessageConfigPair> {
  return api.post<MessageConfigPair>("/graph/config/messages/revert", { body: {} });
}

/** Draft-vs-active row diff (keyed by the directed relation identity). */
export interface ConfigDiff {
  added: number;
  removed: number;
  changed: number;
}

const rowKey = (r: MessageEdgeRow) =>
  `${r.sourceTicker}|${r.sourceExpiry}>${r.targetTicker}|${r.targetExpiry}`;

const rowEqual = (a: MessageEdgeRow, b: MessageEdgeRow) =>
  a.messagePrecision === b.messagePrecision &&
  a.betaAtmVol === b.betaAtmVol &&
  a.betaSkew === b.betaSkew &&
  a.betaCurv === b.betaCurv &&
  a.relationClass === b.relationClass &&
  a.precisionRule === b.precisionRule;

export function diffRows(
  draft: MessageEdgeRow[],
  active: MessageEdgeRow[],
): ConfigDiff {
  const byKey = new Map(active.map((r) => [rowKey(r), r]));
  let added = 0;
  let changed = 0;
  const seen = new Set<string>();
  for (const r of draft) {
    const key = rowKey(r);
    seen.add(key);
    const other = byKey.get(key);
    if (other === undefined) added += 1;
    else if (!rowEqual(r, other)) changed += 1;
  }
  const removed = active.filter((r) => !seen.has(rowKey(r))).length;
  return { added, removed, changed };
}

/** True when activating the draft would change what runs. */
export function configDirty(pair: MessageConfigPair | null): boolean {
  if (pair === null || pair.draft === null) return false;
  if (pair.active === null) return true; // anything staged vs "never activated"
  const d = diffRows(pair.draft.rows, pair.active.rows);
  return d.added + d.removed + d.changed > 0;
}
