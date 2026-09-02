// One quote frame of the SmileChart: bid/ask I-beams with a mid tick, plus the
// fit-target overlay of that frame (mid polyline / bid-ask ribbon / haircut
// ribbon, lib/smileTarget), in one of two visual variants:
//
//   "market"  the PREVAILING market (layer 1) — bright red, the unmistakable
//             "this is the market now" layer; live-ticked strikes flash teal;
//   "calib"   the quotes + target the last calibration used (layer 2) — muted
//             slate, dashed ribbons, excluded strikes crossed, amended mids amber.
//
// The layer receives a `toX` already bound to ITS OWN forward (the chart builds
// one axis transform per frame), so each frame is drawn in its own moneyness
// and two frames with different forwards sit correctly on one axis in every
// axis mode. Clicks select by the quote's `index` (the calibration quote; a
// market quote carries the calibration index at the same strike, -1 = none).
import type { FitMode } from "../state/useSmile";
import type { QuoteBand } from "../lib/mockData";
import { midLinePath, ribbonPath } from "../lib/smileTarget";

export type QuoteVariant = "market" | "calib";

interface QuoteLayerProps {
  quotes: readonly QuoteBand[];
  variant: QuoteVariant;
  /** k (relative to THIS frame's forward) -> pixel x. */
  toX: (k: number) => number;
  toY: (vol: number) => number;
  plotW: number;
  fitMode: FitMode;
  showTarget: boolean;
  selectedIndex: number | null;
  onQuoteSelect?: (index: number | null) => void;
  /** Strike keys (4 dp) whose band moved in the last live frame (market only). */
  flash?: Set<string>;
  /** The quotes are MARKS (bid = ask closes, no spread): draw a hollow diamond
   *  per contract instead of a zero-length beam that reads as "no bid/ask". */
  marks?: boolean;
}

const STYLE = {
  market: {
    beam: "rgb(248 113 113 / 0.95)",
    mid: "rgb(248 113 113)",
    hot: "rgb(94 234 212 / 0.95)",
    ribbon: "rgb(248 113 113 / 0.10)",
    haircut: "rgb(248 113 113 / 0.35)",
    midLine: "rgb(248 113 113 / 0.6)",
    width: 1.4,
    dash: undefined as string | undefined,
  },
  calib: {
    beam: "rgb(148 163 184 / 0.75)",
    mid: "rgb(148 163 184 / 0.95)",
    hot: "rgb(148 163 184 / 0.75)",
    ribbon: "rgb(148 163 184 / 0.12)",
    haircut: "rgb(148 163 184 / 0.28)",
    midLine: "rgb(148 163 184 / 0.55)",
    width: 1.1,
    dash: "3 3" as string | undefined,
  },
};

/** `M x,y` path head (2-dp pixels, like the curve paths). */
const pathAt = (x: number, y: number): string => `M${x.toFixed(2)},${y.toFixed(2)}`;

export default function QuoteLayer({
  quotes, variant, toX, toY, plotW, fitMode, showTarget, selectedIndex, onQuoteSelect, flash, marks = false,
}: QuoteLayerProps) {
  const st = STYLE[variant];
  const bidAsk = showTarget && !marks ? ribbonPath(quotes, (q) => q.bid, (q) => q.ask, toX, toY) : "";
  const haircut =
    showTarget && fitMode === "haircut"
      ? ribbonPath(quotes, (q) => q.targetLo, (q) => q.targetHi, toX, toY)
      : "";
  const midLine = showTarget ? midLinePath(quotes, toX, toY) : "";
  const cap = variant === "market" ? 3.5 : 2.5;
  return (
    <g data-testid={`quote-layer-${variant}`}>
      {bidAsk !== "" && (
        <path d={bidAsk} fill={st.ribbon} stroke="none" pointerEvents="none" />
      )}
      {haircut !== "" && (
        <path d={haircut} fill={st.haircut} stroke="none" pointerEvents="none" />
      )}
      {midLine !== "" && (
        <path d={midLine} fill="none" stroke={st.midLine} strokeWidth={1}
          strokeDasharray={st.dash} pointerEvents="none" />
      )}
      {quotes.map((q) => {
        const x = toX(q.k);
        if (!Number.isFinite(x) || x < -20 || x > plotW + 20) return null;
        const yb = toY(q.bid);
        const ya = toY(q.ask);
        const ym = toY(q.mid);
        const selected = selectedIndex !== null && q.index >= 0 && q.index === selectedIndex;
        const hot = !!flash && q.strike != null && flash.has(q.strike.toFixed(4));
        const beamStroke = selected ? "var(--color-accent-400)" : hot ? st.hot : st.beam;
        const midStroke = q.amended
          ? "rgb(251 191 36 / 0.95)"
          : selected
            ? "var(--color-accent-400)"
            : hot
              ? st.hot
              : st.mid;
        const midHalf = q.amended ? 4 : 2.5;
        const key = `${variant}-${q.strike ?? q.k}`;
        // One PATH per beam (stem + two caps) and one for the mid tick, not four
        // <line>s: a path's `d` change is repainted reliably by every engine
        // (like the curves), whereas in-place x/y attribute mutation of many
        // <line>s inside the clipped group left ghost beams at the old positions
        // in Chrome while live ticks streamed (until the next tick rebuilt them).
        const beamD = `${pathAt(x, yb)}V${ya.toFixed(2)}M${(x - cap).toFixed(2)},${ya.toFixed(2)}H${(x + cap).toFixed(2)}M${(x - cap).toFixed(2)},${yb.toFixed(2)}H${(x + cap).toFixed(2)}`;
        const midD = `${pathAt(x - midHalf, ym)}H${(x + midHalf).toFixed(2)}`;
        // A mark (bid = ask close): a hollow diamond, so it never reads as a
        // collapsed bid/ask beam.
        const d = 3.2;
        const markD = `${pathAt(x, ym - d)}L${(x + d).toFixed(2)},${ym.toFixed(2)}L${x.toFixed(2)},${(ym + d).toFixed(2)}L${(x - d).toFixed(2)},${ym.toFixed(2)}Z`;
        return (
          <g key={key}>
            {selected && <circle cx={x} cy={ym} r={7} fill="var(--color-accent-400)" opacity={0.18} />}
            <g opacity={q.excluded ? 0.25 : 1}>
              {marks ? (
                <path d={markD} fill="var(--color-surface-900)" stroke={midStroke} strokeWidth={1.4} data-mark="1" />
              ) : (
                <>
                  <path d={beamD} fill="none" stroke={beamStroke} strokeWidth={st.width}
                    strokeDasharray={variant === "calib" ? "2 2" : undefined} />
                  <path d={midD} fill="none" stroke={midStroke} strokeWidth={2.2} />
                </>
              )}
            </g>
            {q.excluded && (
              <path
                d={`${pathAt(x - 3, ym - 3)}L${(x + 3).toFixed(2)},${(ym + 3).toFixed(2)}${pathAt(x - 3, ym + 3)}L${(x + 3).toFixed(2)},${(ym - 3).toFixed(2)}`}
                fill="none" stroke="rgb(148 163 184 / 0.8)" strokeWidth={1.2}
              />
            )}
            {onQuoteSelect && q.index >= 0 && (
              <rect
                x={x - 6}
                y={Math.min(ya, yb) - 8}
                width={12}
                height={Math.abs(yb - ya) + 16}
                fill="transparent"
                className="cursor-pointer"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  onQuoteSelect(q.index);
                }}
              />
            )}
          </g>
        );
      })}
    </g>
  );
}
