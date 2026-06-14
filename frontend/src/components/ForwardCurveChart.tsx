// Forward-curve chart for the Forwards workspace (ROADMAP item 9).
//
// Plots the active forward across the expiry ladder (T or √T axis) with dashed
// vertical lines at each discrete dividend ex-date. Click an empty spot to drop
// a new dividend at that date; click a line to select it; a slider then sets the
// amount. Apply PUTs the schedule (GET/PUT /settings/market/{ticker}) — when the
// ticker is on continuous dividends, the first manual div switches it to
// discrete cash so the divs actually move the theoretical forward.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { api } from "../state/api";
import { clamp, linearScale, niceTicks } from "../lib/chartScale";
import { formatYears, timeAxisValue } from "../lib/timeAxis";
import type { TimeAxisMode } from "../lib/timeAxis";
import type { DividendItem, ForwardEntry, MarketSettings } from "./ForwardPanel";

const MARGIN = { top: 16, right: 16, bottom: 34, left: 56 } as const;
const YEAR_MS = 365.25 * 24 * 3600 * 1000;

interface Props {
  ticker: string;
  disabled: boolean;
  entries: ForwardEntry[];
  spot: number;
  /** Bumped by the parent after any forward/dividend edit, to refetch. */
  refreshKey: number;
  onApplied: () => void;
}

function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

export default function ForwardCurveChart({ ticker, disabled, entries, spot, refreshKey, onApplied }: Props) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [timeMode, setTimeMode] = useState<TimeAxisMode>("linear");
  const [market, setMarket] = useState<MarketSettings | null>(null);
  const [divs, setDivs] = useState<DividendItem[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);

  // (Re)load the schedule whenever the ticker or an external edit changes it.
  useEffect(() => {
    if (disabled || ticker === "") return;
    const controller = new AbortController();
    api
      .get<MarketSettings>(`/settings/market/${ticker}`, { signal: controller.signal })
      .then((m) => {
        setMarket(m);
        setDivs(m.dividends);
        setSel(null);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [ticker, disabled, refreshKey]);

  const dirty =
    market !== null &&
    (divs.length !== market.dividends.length ||
      divs.some((d, i) => d.exDate !== market.dividends[i]?.exDate || d.amount !== market.dividends[i]?.amount));

  // Reference epoch so a dividend ex-date lands on the same t-scale as the curve.
  const ref0 =
    entries.length > 0 ? Date.parse(entries[0].expiry) - entries[0].t * YEAR_MS : Date.now();
  const tOfDate = (iso: string) => (Date.parse(iso) - ref0) / YEAR_MS;
  const dateOfT = (t: number) => new Date(ref0 + t * YEAR_MS).toISOString().slice(0, 10);

  const innerW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  const sorted = [...entries].sort((a, b) => a.t - b.t);
  const tMax = sorted.length ? sorted[sorted.length - 1].t : 1;
  const fwds = sorted.map((e) => e.activeForward);
  let yLo = Math.min(spot, ...(fwds.length ? fwds : [spot]));
  let yHi = Math.max(spot, ...(fwds.length ? fwds : [spot]));
  if (!(yHi > yLo)) { yLo -= 1; yHi += 1; }
  // Floor the padding by a fraction of the level so a near-flat forward curve
  // (e.g. zero-carry synthetic) still gets a visible, well-formed axis band.
  const yPad = Math.max((yHi - yLo) * 0.08, Math.abs(yHi) * 1e-4, 0.01);

  const xpos = (t: number) => timeAxisValue(t, timeMode);
  const xposInv = (p: number) => (timeMode === "sqrt" ? p * p : p);
  const xScale = linearScale([0, xpos(tMax) || 1], [0, innerW]);
  const X = (t: number) => xScale.map(xpos(t));
  const yScale = linearScale([yLo - yPad, yHi + yPad], [innerH, 0]);

  const xTicks = niceTicks(0, tMax, 6);
  const yTicks = niceTicks(yLo - yPad, yHi + yPad, 5);

  const curvePath = sorted
    .map((e, i) => `${i === 0 ? "M" : "L"}${X(e.t).toFixed(1)},${yScale.map(e.activeForward).toFixed(1)}`)
    .join("");

  const amtMax = Math.max(spot * 0.04, 5);

  // Click the plot: select a nearby dividend, else drop a new one at that date.
  const onClick = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (disabled || svgRef.current === null) return;
    const rect = svgRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    if (px < 0 || px > innerW) return;
    const t = clamp(xposInv(xScale.invert(px)), 0, tMax * 1.5);
    // Select an existing div if the click is within ~8px of its line.
    let nearest = -1;
    let nearestDist = 9;
    divs.forEach((d, i) => {
      const dist = Math.abs(X(tOfDate(d.exDate)) - px);
      if (dist < nearestDist) { nearestDist = dist; nearest = i; }
    });
    if (nearest >= 0) { setSel(nearest); return; }
    const next = [...divs, { exDate: dateOfT(t), amount: Number((spot * 0.005).toFixed(2)) }];
    next.sort((a, b) => Date.parse(a.exDate) - Date.parse(b.exDate));
    setDivs(next);
    setSel(next.findIndex((d) => d.exDate === dateOfT(t)));
  };

  const setSelAmount = (amount: number) => {
    if (sel === null) return;
    setDivs((prev) => prev.map((d, i) => (i === sel ? { ...d, amount } : d)));
  };
  const removeSel = () => {
    if (sel === null) return;
    setDivs((prev) => prev.filter((_, i) => i !== sel));
    setSel(null);
  };

  const apply = async () => {
    if (!dirty || busy || market === null) return;
    setBusy(true);
    try {
      // Continuous ticker + manual divs => switch to discrete cash so they bite.
      const mode =
        market.dividendMode === "continuous" && divs.length > 0 ? "discrete_absolute" : market.dividendMode;
      const m = await api.put<MarketSettings>(`/settings/market/${ticker}`, {
        body: {
          rate: market.rate,
          dividendMode: mode,
          dividendYield: market.dividendYield,
          dividends: divs,
          switchYears: market.switchYears,
        },
      });
      setMarket(m);
      setDivs(m.dividends);
      setFlash(true);
      setTimeout(() => setFlash(false), 1200);
      onApplied();
    } catch {
      /* keep the draft so the user can retry */
    } finally {
      setBusy(false);
    }
  };

  const selDiv = sel !== null ? divs[sel] : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-1 flex shrink-0 items-center gap-4 px-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-accent-400" /> Active forward
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-0 border-l border-dashed border-emerald-400/70" /> Dividend
        </span>
        <span className="text-[10px] text-slate-600">click chart: add div · click a line: select</span>
        <div className="ml-auto flex overflow-hidden rounded border border-slate-700">
          {(["linear", "sqrt"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setTimeMode(m)}
              className={[
                "px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                timeMode === m ? "bg-accent-600/25 text-accent-400" : "text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {m === "sqrt" ? "√T" : "T"}
            </button>
          ))}
        </div>
      </div>

      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className={`absolute inset-0 ${disabled ? "" : "cursor-crosshair"}`}
            onClick={onClick}
          >
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {yTicks.map((v) => (
                <g key={`y${v}`}>
                  <line x1={0} x2={innerW} y1={yScale.map(v)} y2={yScale.map(v)} stroke="rgb(255 255 255 / 0.05)" />
                  <text x={-8} y={yScale.map(v)} dy="0.32em" textAnchor="end" className="fill-slate-500 font-mono text-[10px]">
                    {v.toFixed(2)}
                  </text>
                </g>
              ))}
              {xTicks.map((tk) => (
                <g key={`x${tk}`}>
                  <line x1={X(tk)} x2={X(tk)} y1={0} y2={innerH} stroke="rgb(255 255 255 / 0.04)" />
                  <text x={X(tk)} y={innerH + 16} textAnchor="middle" className="fill-slate-500 font-mono text-[10px]">
                    {formatYears(tk)}
                  </text>
                </g>
              ))}

              {/* Spot reference */}
              {spot >= yScale.domain[0] && spot <= yScale.domain[1] && (
                <line x1={0} x2={innerW} y1={yScale.map(spot)} y2={yScale.map(spot)}
                  stroke="rgb(148 163 184 / 0.3)" strokeDasharray="2 4" />
              )}

              {/* Dividend ex-date verticals */}
              {divs.map((d, i) => {
                const x = X(tOfDate(d.exDate));
                if (x < 0 || x > innerW) return null;
                const seld = i === sel;
                return (
                  <g key={`${d.exDate}-${i}`} pointerEvents="none">
                    <line x1={x} x2={x} y1={0} y2={innerH}
                      stroke={seld ? "rgb(45 212 191 / 0.95)" : "rgb(52 211 153 / 0.4)"}
                      strokeWidth={seld ? 1.6 : 1} strokeDasharray="3 4" />
                    <text x={x + 3} y={11} className="fill-emerald-400/80 font-mono text-[9px]">
                      ${d.amount}
                    </text>
                  </g>
                );
              })}

              {/* Forward curve + markers */}
              <path d={curvePath} fill="none" stroke="var(--color-accent-400)" strokeWidth={2} strokeLinejoin="round" />
              {sorted.map((e) => (
                <circle key={e.expiry} cx={X(e.t)} cy={yScale.map(e.activeForward)} r={2.5}
                  fill="var(--color-accent-400)" pointerEvents="none" />
              ))}

              <text x={2} y={-5} className="fill-slate-600 font-mono text-[10px]">forward</text>
              <text x={innerW} y={innerH + 30} textAnchor="end" className="fill-slate-600 font-mono text-[10px]">
                maturity{timeMode === "sqrt" ? " · √T" : ""} (years)
              </text>
            </g>
          </svg>
        )}
      </div>

      {/* Selected-dividend amount slider + Apply */}
      <div className="mt-2 flex shrink-0 items-center gap-3 px-1">
        {selDiv ? (
          <>
            <span className="font-mono text-[11px] text-slate-300">{selDiv.exDate}</span>
            <input
              type="range" min={0} max={amtMax} step={0.01} value={selDiv.amount} disabled={disabled}
              onChange={(e) => setSelAmount(Number(e.target.value))}
              className="h-1 flex-1 cursor-pointer accent-accent-500"
            />
            <input
              type="number" min={0} step={0.01} value={selDiv.amount} disabled={disabled}
              onChange={(e) => setSelAmount(Number(e.target.value))}
              className="w-20 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-200 outline-none focus:border-accent-500"
            />
            <button onClick={removeSel} disabled={disabled}
              className="rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-400 hover:text-rose-300">
              Remove
            </button>
          </>
        ) : (
          <span className="text-[11px] text-slate-500">Click the chart to add a dividend, or a line to select one.</span>
        )}
        <button
          onClick={() => void apply()}
          disabled={disabled || !dirty || busy}
          className={[
            "ml-auto rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            flash
              ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
              : dirty && !disabled
                ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
                : "cursor-not-allowed border-slate-700 text-slate-600",
          ].join(" ")}
        >
          {flash ? "Applied ✓" : busy ? "Saving…" : "Apply dividends"}
        </button>
      </div>
    </div>
  );
}
