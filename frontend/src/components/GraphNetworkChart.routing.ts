// Edge-click routing of the smile-universe canvas (GRAPH ERGONOMICS ARC,
// size split of GraphNetworkChart): what a click on a calendar hop or on a
// ticker-pair bundle reports to the shell.
//
//   calendar hop   ONE stored direction → that relation; both directions →
//                  the pair card (the shell lists the rows).
//   bundle         expanding opens the pair card; collapsing tells the shell
//                  so it drops that pair's card (user report 2026-09-08 — a
//                  second click must hide the inventory as well as the arrows).
import { useCallback, type Dispatch, type SetStateAction } from "react";
import type { CalendarEdge } from "../lib/graphLayout";
import { calendarKeys } from "./GraphEdgeLayer";
import type { BundleGeo } from "./GraphNetworkChart.helpers";
import type { GraphEdgeSelection } from "./GraphNetworkChart";

interface RoutingArgs {
  expanded: Set<string>;
  setExpanded: Dispatch<SetStateAction<Set<string>>>;
  onEdgeClick?: (sel: GraphEdgeSelection) => void;
  onBundleCollapse?: (a: string, b: string) => void;
}

export function useEdgeClickRouting({ expanded, setExpanded, onEdgeClick, onBundleCollapse }: RoutingArgs) {
  const onCalendarClick = useCallback(
    (c: CalendarEdge) => {
      if (onEdgeClick === undefined) return;
      const keys = calendarKeys(c);
      if (c.toEarlier !== c.toLater)
        onEdgeClick({ kind: "relation", key: c.toEarlier ? keys.toEarlier : keys.toLater });
      else onEdgeClick({ kind: "calendar", ticker: c.ticker, aExpiry: c.fromExpiry, bExpiry: c.toExpiry });
    },
    [onEdgeClick],
  );
  const onBundleClick = useCallback(
    (g: BundleGeo) => {
      const opening = !expanded.has(g.key);
      setExpanded((prev) => {
        const next = new Set(prev);
        if (opening) next.add(g.key);
        else next.delete(g.key);
        return next;
      });
      if (opening) onEdgeClick?.({ kind: "cross", a: g.b.fromTicker, b: g.b.toTicker });
      else onBundleCollapse?.(g.b.fromTicker, g.b.toTicker);
    },
    [expanded, setExpanded, onEdgeClick, onBundleCollapse],
  );
  return { onCalendarClick, onBundleClick };
}
