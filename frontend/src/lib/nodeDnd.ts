// Drag-and-drop of a smile NODE (UI SHELL v2 wave 3, C5) — pure helpers.
//
// A nodes-pane row starts an HTML5 drag carrying the node as
// `application/x-volfit-node` (JSON {ticker, expiry}). Drop zones:
//   canvas    the Graph lens: calibrations mode → the node's designation
//             becomes LIT; manual what-if → a pulse at the default +1 vol pt
//   tabstrip  the main pane's tab strip → open the node as a PINNED tab
//   split     the other editor group (C3) → open it there
// routeNodeDrop turns (zone, node, mode) into the one action the shell
// applies; the components stay thin. Vitest-locked in nodeDnd.test.ts.

export const NODE_MIME = "application/x-volfit-node";

/** Default what-if pulse (decimal vol): +1 vol point (state/useGraph). */
export const DEFAULT_PULSE = 0.01;

export interface DragNode { ticker: string; expiry: string }

export type DropZone = "canvas" | "tabstrip" | "split";

export type DropAction =
  | { type: "light"; ticker: string; expiry: string; key: string }
  | { type: "pulse"; ticker: string; expiry: string; key: string; dAtmVol: number }
  | { type: "openTab"; ticker: string; expiry: string; pinned: true }
  | { type: "openSplit"; ticker: string; expiry: string };

/** dataTransfer payload of a node drag. */
export function encodeNodeDrag(node: DragNode): string {
  return JSON.stringify({ ticker: node.ticker, expiry: node.expiry });
}

/** True when a drag carries a node (dragover gating). */
export function isNodeDrag(types: ArrayLike<string> | undefined | null): boolean {
  return types !== undefined && types !== null && Array.from(types).includes(NODE_MIME);
}

/** Parse the payload back (null for anything else / malformed). */
export function decodeNodeDrag(payload: string | null | undefined): DragNode | null {
  if (!payload) return null;
  try {
    const p = JSON.parse(payload) as Partial<DragNode>;
    if (typeof p.ticker !== "string" || typeof p.expiry !== "string" || p.ticker === "" || p.expiry === "") return null;
    return { ticker: p.ticker, expiry: p.expiry };
  } catch {
    return null;
  }
}

/** The action a drop performs (see the module comment). */
export function routeNodeDrop(zone: DropZone, node: DragNode, ctx: { manual: boolean }): DropAction {
  const key = `${node.ticker}|${node.expiry}`;
  switch (zone) {
    case "canvas":
      return ctx.manual
        ? { type: "pulse", ...node, key, dAtmVol: DEFAULT_PULSE }
        : { type: "light", ...node, key };
    case "tabstrip":
      return { type: "openTab", ...node, pinned: true };
    case "split":
      return { type: "openSplit", ...node };
  }
}
