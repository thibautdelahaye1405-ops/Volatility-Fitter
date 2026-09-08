// Relation actions of the Graph shell (GRAPH ERGONOMICS ARC, size split of
// GraphViewer): the connect gesture (informer → receiver becomes a draft row,
// or an existing arrow is simply selected — never overwritten), "+ reverse"
// (the explicit opposite arrow, flipped with the §7.6/§8.3 identities),
// flip and delete of the selected relation. Every action edits the draft
// (useRelationDraft) and moves the shell's selection.
import { useCallback } from "react";
import type { GraphEdgeSelection } from "../components/GraphNetworkChart";
import { flipRelation, newRelationRow, relationKey, type NodeRef } from "../lib/relationRows";
import type { MessageEdgeRow } from "./useMessageEdges";
import type { RelationDraft } from "./useRelationDraft";

interface RelationActionsArgs {
  draft: RelationDraft;
  scales: { calPrecision: number; crossPrecision: number };
  selectedKey: string | null;
  selectedRow: MessageEdgeRow | null;
  selectRelation: (key: string) => void;
  setSelectedEdge: (sel: GraphEdgeSelection | null) => void;
}

/** The selection after a bundle (ticker pair a, b) COLLAPSED: the pair's own
 *  card and any relation between the two tickers are dropped; anything else
 *  (a calendar relation, another pair) is kept. */
export function dropPairSelection(
  cur: GraphEdgeSelection | null,
  a: string,
  b: string,
): GraphEdgeSelection | null {
  if (cur === null) return null;
  const pair = new Set([a, b]);
  if (cur.kind === "cross") return pair.has(cur.a) && pair.has(cur.b) ? null : cur;
  if (cur.kind === "relation") {
    const [src = "", tgt = ""] = cur.key.split(">");
    const s = src.split("|")[0] ?? "";
    const t = tgt.split("|")[0] ?? "";
    return s !== t && pair.has(s) && pair.has(t) ? null : cur;
  }
  return cur;
}

export interface RelationActions {
  onConnect: (source: NodeRef, target: NodeRef) => void;
  onAddReverse: () => void;
  onFlipSelected: () => void;
  onDeleteSelected: () => void;
}

export function useRelationActions({
  draft,
  scales,
  selectedKey,
  selectedRow,
  selectRelation,
  setSelectedEdge,
}: RelationActionsArgs): RelationActions {
  const onConnect = useCallback(
    (source: NodeRef, target: NodeRef) => {
      const row = newRelationRow(source, target, scales);
      if (row === null) return;
      const key = relationKey(row);
      if (draft.byKey(key) === undefined) draft.add(row);
      selectRelation(key);
    },
    [draft, scales, selectRelation],
  );
  const onAddReverse = useCallback(() => {
    if (selectedRow === null) return;
    const reverse = flipRelation(selectedRow);
    const key = relationKey(reverse);
    if (draft.byKey(key) === undefined) draft.add(reverse);
    selectRelation(key);
  }, [selectedRow, draft, selectRelation]);
  const onFlipSelected = useCallback(() => {
    if (selectedKey === null) return;
    const nk = draft.flip(selectedKey);
    if (nk !== null) selectRelation(nk);
  }, [draft, selectedKey, selectRelation]);
  const onDeleteSelected = useCallback(() => {
    if (selectedKey === null) return;
    draft.remove(selectedKey);
    setSelectedEdge(null);
  }, [draft, selectedKey, setSelectedEdge]);
  return { onConnect, onAddReverse, onFlipSelected, onDeleteSelected };
}
