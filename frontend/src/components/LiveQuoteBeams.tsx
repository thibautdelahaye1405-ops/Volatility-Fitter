// Live market layer of the SmileChart: the node's live bid/ask bands (one SSE
// stream per viewed node, state/useLiveTicks — shared with the Quote Table)
// drawn as thin teal I-beams with a mid tick, OVER the red calibration beams.
// Each live row is placed at log(strike / the chart's own forward), so the
// layer follows the chart under any axis mode and under a spot-move
// re-expression of moneyness (the backend keys rows by strike for that
// reason). Rows whose band moved in the last frame are drawn brighter; the
// layer is purely informational (no hit-testing — clicks still select the
// calibration quote underneath) and never widens the y-domain, so a ticking
// wing cannot make the axis jitter.
import type { LiveTicksState } from "../state/useLiveTicks";

interface LiveQuoteBeamsProps {
  ticks: LiveTicksState;
  /** The chart's forward (its quotes' k reference) — live k = log(strike / forward). */
  forward: number;
  /** k -> pixel x (the chart's axis transform + x scale). */
  toX: (k: number) => number;
  /** iv -> pixel y. */
  toY: (iv: number) => number;
  plotW: number;
}

/** Log-moneyness of a live row against the chart's forward (pure). */
export const liveK = (strike: number, forward: number): number => Math.log(strike / forward);

export default function LiveQuoteBeams({ ticks, forward, toX, toY, plotW }: LiveQuoteBeamsProps) {
  if (!ticks.ready || ticks.rows.size === 0 || !(forward > 0)) return null;
  const cap = 2.5;
  return (
    <g data-testid="live-quote-beams">
      {[...ticks.rows.values()].map((r) => {
        const x = toX(liveK(r.strike, forward));
        if (!Number.isFinite(x) || x < -20 || x > plotW + 20) return null;
        const yb = toY(r.bidIv);
        const ya = toY(r.askIv);
        const ym = toY(r.midIv);
        const hot = ticks.flash.has(r.key);
        return (
          <g
            key={r.key}
            stroke={hot ? "rgb(94 234 212 / 0.95)" : "rgb(45 212 191 / 0.55)"}
            strokeWidth={hot ? 1.3 : 1}
            pointerEvents="none"
          >
            <line x1={x} x2={x} y1={yb} y2={ya} />
            <line x1={x - cap} x2={x + cap} y1={ya} y2={ya} />
            <line x1={x - cap} x2={x + cap} y1={yb} y2={yb} />
            <line x1={x - 2} x2={x + 2} y1={ym} y2={ym} strokeWidth={hot ? 2.2 : 1.6} />
          </g>
        );
      })}
    </g>
  );
}
