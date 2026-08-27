// Drop-from-the-Nodes-pane handler of the Graph lens (UI SHELL v2 wave 3,
// C5): routes a dropped node through lib/nodeDnd — calibrations mode sets the
// SHARED lit designation (the LitMap context; useGraph's persisted lit
// off-shell), manual what-if adds the default +1 vol pt pulse.
import { useCallback } from "react";
import { routeNodeDrop } from "../lib/nodeDnd";
import type { DragNode } from "../lib/nodeDnd";
import { useOptionalLitMap } from "./litMap";
import type { UseGraphResult } from "./useGraph";

export function useNodeDrop(graph: UseGraphResult, manual: boolean): (node: DragNode) => void {
  const litMap = useOptionalLitMap();
  return useCallback(
    (node: DragNode) => {
      const a = routeNodeDrop("canvas", node, { manual });
      if (a.type === "pulse") graph.lightMany([a.key]);
      else if (a.type === "light") {
        if (litMap !== null) litMap.setNode(a.ticker, a.expiry, true);
        else graph.lightMany([a.key]);
      }
    },
    [graph, manual, litMap],
  );
}
