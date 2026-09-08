// Scene extras of the smile-universe canvas (GRAPH ERGONOMICS ARC, size
// split of GraphNetworkChart): the ticker PODS (faint circle + a label that
// collapses / expands the pod) and the CONNECT rubber band (source node →
// pointer, with a head) drawn while a node → node gesture is in flight. Both
// live in world coordinates inside the chart's pan/zoom group.
import { arrowHeadPoints } from "../lib/edgeStyle";
import type { GraphLayout } from "../lib/graphLayout";
import type { FocusSet } from "./GraphNetworkChart.helpers";

export function GraphPodLayer({
  layout,
  focus,
  collapsed,
  onTogglePod,
}: {
  layout: GraphLayout;
  focus: FocusSet | null;
  collapsed: ReadonlySet<string>;
  onTogglePod: (ticker: string) => void;
}) {
  return (
    <>
      {layout.pods.map((pod) => (
        <g key={pod.ticker} opacity={focus === null || focus.tickers.has(pod.ticker) ? 1 : 0.15}>
          <circle cx={pod.cx} cy={pod.cy} r={pod.radius} fill="none" stroke="rgb(51 65 85)" />
          <text
            x={pod.cx}
            y={pod.cy - pod.radius - 8}
            textAnchor="middle"
            className="cursor-pointer fill-slate-300 text-[11px] font-semibold tracking-wide hover:fill-slate-100"
            data-pod={pod.ticker}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onTogglePod(pod.ticker)}
          >
            {pod.ticker}
            {collapsed.has(pod.ticker) ? " ▸" : ""}
            <title>{collapsed.has(pod.ticker) ? "Expand this ticker's expiries" : "Collapse this ticker to one node"}</title>
          </text>
        </g>
      ))}
    </>
  );
}

/** The connect gesture's rubber band: source node → pointer, dashed accent. */
export function ConnectBand({
  from,
  to,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
}) {
  return (
    <g pointerEvents="none" data-testid="connect-band">
      <line
        x1={from.x} y1={from.y} x2={to.x} y2={to.y}
        stroke="var(--color-accent-400)" strokeWidth={2} strokeDasharray="5 4" opacity={0.9}
      />
      <polygon points={arrowHeadPoints(from.x, from.y, to.x, to.y)} fill="var(--color-accent-400)" />
    </g>
  );
}
