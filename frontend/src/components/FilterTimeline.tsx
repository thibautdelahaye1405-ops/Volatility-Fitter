// FilterTimeline — per-node Kalman filter evidence over time (V3.9 item 7).
//
// Fed by /smiles/{t}/{e}/filter/history (the 64-step ring), per handle (ATM
// default): the three-band chart (prediction m⁻±σ, observation z±σR,
// posterior line), a ζ strip with ±1/±2 guides (std(ζ) ≈ 1 = healthy Q), a
// gain sparkline, a stacked Q-breakdown area (the adaptive component is where
// surprises show) and reset/provenance/contamination tick markers. Hand-rolled
// SVG on the chartScale idiom; native <title> hovers (the repo's tooltip
// convention). Colors are the CVD-validated series set (see the dataviz
// palette run in the V3.9 session); stacked layers carry a surface-colored
// separator (the spacer rule) so the one 6.9-ΔE pair stays legal.
import { useEffect, useState } from "react";

import { formatPct, linearScale, niceTicks } from "../lib/chartScale";
import {
  bandPath,
  gainSeries,
  handleSeries,
  linePath,
  Q_KEYS,
  qStack,
  spansDays,
  stepLabel,
  stepMarkers,
  tickIndices,
  yDomain,
  zetaSeries,
  type FilterStepWire,
  type StepMarker,
} from "../lib/filterTimeline";
import { useElementSize } from "../lib/useElementSize";
import { api } from "../state/api";
import { useFilterHistory } from "../state/useFilterHistory";
import type { FitMode } from "../state/useSmile";

const HANDLES = ["ATM", "skew", "curv"] as const;

// Series colors (validated on surface-800 with the dataviz six-checks script).
const C = {
  pred: "#3987e5", // prediction band (blue)
  obs: "#d95926", // observation band (orange)
  post: "#199e70", // posterior line (aqua)
  zeta: "#3987e5",
  gain: "#199e70",
  guide: "var(--color-surface-700)",
  guide2: "#f43f5e", // ±2 ζ guide (evidence rose)
  ink: "fill-slate-500 text-[9px]",
} as const;
const Q_COLORS: Record<(typeof Q_KEYS)[number], string> = {
  clock: "#3987e5",
  spot: "#d95926",
  event: "#199e70",
  source: "#c98500",
  model: "#008300",
  adaptive: "#d55181", // the surprise component, top of the stack
};
const MARKER_COLORS: Record<StepMarker["kind"], string> = {
  seed: "#3987e5",
  reset: "#f43f5e",
  contaminated: "#fbbf24",
};

const ML = 46; // left margin (y labels)
const MR = 6;

const selectCls =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** Per-step hover summary (native <title> tooltip). */
function stepTitle(s: FilterStepWire, h: number, multiDay: boolean): string {
  const f = (a: number[], d = 4) => (Number.isFinite(a?.[h]) ? a[h].toFixed(d) : "—");
  const flags = [s.resetReason ? `reset: ${s.resetReason}` : null, s.contaminated ? "contaminated" : null]
    .filter(Boolean)
    .join(" · ");
  return (
    `${stepLabel(s.ts, multiDay)} · dt ${s.dtDays.toFixed(4)}d · ${s.provenance}` +
    `\nm⁻ ${f(s.prediction)} ± ${f(s.predictionStd)} · z ${f(s.observation)} ± ${f(s.observationStd)}` +
    `\nm⁺ ${f(s.posterior)} ± ${f(s.posteriorStd)} · ζ ${s.zeta ? f(s.zeta, 2) : "—"} · K ${f(s.gain, 2)}` +
    (flags ? `\n${flags}` : "")
  );
}

/** The stacked evidence charts for one handle. Pure render — no fetching. */
export function FilterTimeline({ steps, handle }: { steps: FilterStepWire[]; handle: number }) {
  const { ref, size } = useElementSize();
  const innerW = Math.max(0, size.width - ML - MR);
  const n = steps.length;
  const multiDay = spansDays(steps);
  const xScale = linearScale([0, Math.max(n - 1, 1)], [0, innerW]);
  const xs = steps.map((_, i) => xScale.map(i));
  const slotW = n > 1 ? innerW / (n - 1) : innerW;

  // --- three-band chart -----------------------------------------------------
  const hs = handleSeries(steps, handle);
  const bandH = 108;
  const [bLo, bHi] = yDomain([...hs.predLo, ...hs.predHi, ...hs.obsLo, ...hs.obsHi, ...hs.post]);
  const bY = linearScale([bLo, bHi], [bandH, 0]);
  const bTicks = niceTicks(bLo, bHi, 3);
  const fmtY = (v: number) => (handle === 0 ? formatPct(v, 1) : v.toFixed(2));
  const bPix = (a: number[]) => a.map((v) => (Number.isFinite(v) ? bY.map(v) : NaN));
  const markers = stepMarkers(steps);

  // --- ζ strip ---------------------------------------------------------------
  const zs = zetaSeries(steps, handle);
  const zMax = Math.max(2.5, ...zs.filter(Number.isFinite).map(Math.abs)) * 1.1;
  const zH = 52;
  const zY = linearScale([-zMax, zMax], [zH, 0]);

  // --- gain sparkline ----------------------------------------------------------
  const gs = gainSeries(steps, handle);
  const gH = 36;
  const gY = linearScale([0, 1.05], [gH, 0]);

  // --- Q-breakdown stack -------------------------------------------------------
  const layers = qStack(steps, handle);
  const qMax = Math.max(...layers[layers.length - 1].hi.filter(Number.isFinite), 1e-12);
  const qH = 56;
  const qY = linearScale([0, qMax * 1.05], [qH, 0]);
  const activeKeys = new Set(
    layers.filter((l) => l.hi.some((v, i) => v - l.lo[i] > 0)).map((l) => l.key),
  );

  const xTicks = tickIndices(n);

  if (size.width === 0) return <div ref={ref} className="h-2 w-full" />;
  return (
    <div ref={ref} className="w-full">
      <svg width={size.width} height={bandH + zH + gH + qH + 58} className="block select-none">
        {/* ---- bands: prediction / observation / posterior ---- */}
        <g transform={`translate(${ML},4)`}>
          {bTicks.map((t) => (
            <g key={`b${t}`}>
              <line x1={0} x2={innerW} y1={bY.map(t)} y2={bY.map(t)} stroke={C.guide} strokeWidth={1} />
              <text x={-6} y={bY.map(t)} dy="0.32em" textAnchor="end" className={C.ink}>
                {fmtY(t)}
              </text>
            </g>
          ))}
          <path d={bandPath(xs, bPix(hs.predLo), bPix(hs.predHi))} fill={C.pred} opacity={0.18} />
          <path d={bandPath(xs, bPix(hs.obsLo), bPix(hs.obsHi))} fill={C.obs} opacity={0.16} />
          <path d={linePath(xs, bPix(hs.obs))} fill="none" stroke={C.obs} strokeWidth={1} strokeDasharray="3 3" opacity={0.8} />
          <path d={linePath(xs, bPix(hs.post))} fill="none" stroke={C.post} strokeWidth={2} />
          {steps.map((_, i) =>
            Number.isFinite(hs.post[i]) ? (
              <circle key={`p${i}`} cx={xs[i]} cy={bY.map(hs.post[i])} r={2} fill={C.post} />
            ) : null,
          )}
          {/* reset / seed / contamination ticks with hover titles */}
          {markers.map((m, j) => (
            <line
              key={`m${j}`}
              x1={xs[m.index]}
              x2={xs[m.index]}
              y1={0}
              y2={bandH}
              stroke={MARKER_COLORS[m.kind]}
              strokeWidth={1.5}
              strokeDasharray={m.kind === "seed" ? "3 3" : m.kind === "contaminated" ? "1.5 2.5" : undefined}
              opacity={0.85}
            >
              <title>{m.label}</title>
            </line>
          ))}
          {/* per-step hover hit columns (native tooltip, hit area > mark) */}
          {steps.map((s, i) => (
            <rect
              key={`h${i}`}
              x={xs[i] - slotW / 2}
              y={0}
              width={slotW}
              height={bandH}
              fill="transparent"
            >
              <title>{stepTitle(s, handle, multiDay)}</title>
            </rect>
          ))}
        </g>

        {/* ---- ζ strip ---- */}
        <g transform={`translate(${ML},${bandH + 16})`}>
          <text x={-6} y={zY.map(0)} dy="0.32em" textAnchor="end" className={C.ink}>ζ</text>
          <line x1={0} x2={innerW} y1={zY.map(0)} y2={zY.map(0)} stroke={C.guide} strokeWidth={1} />
          {[1, -1].map((g) => (
            <line key={`g1${g}`} x1={0} x2={innerW} y1={zY.map(g)} y2={zY.map(g)} stroke="var(--color-slate-600)" strokeWidth={0.75} strokeDasharray="2 3" />
          ))}
          {[2, -2].map((g) => (
            <line key={`g2${g}`} x1={0} x2={innerW} y1={zY.map(g)} y2={zY.map(g)} stroke={C.guide2} strokeWidth={0.75} strokeDasharray="2 3" opacity={0.7} />
          ))}
          <path d={linePath(xs, zs.map((v) => (Number.isFinite(v) ? zY.map(v) : NaN)))} fill="none" stroke={C.zeta} strokeWidth={1.5} />
          {zs.map((v, i) =>
            Number.isFinite(v) ? <circle key={`z${i}`} cx={xs[i]} cy={zY.map(v)} r={1.8} fill={C.zeta} /> : null,
          )}
        </g>

        {/* ---- gain sparkline ---- */}
        <g transform={`translate(${ML},${bandH + zH + 24})`}>
          <text x={-6} y={gY.map(0.5)} dy="0.32em" textAnchor="end" className={C.ink}>K</text>
          {[0, 1].map((g) => (
            <line key={`k${g}`} x1={0} x2={innerW} y1={gY.map(g)} y2={gY.map(g)} stroke={C.guide} strokeWidth={0.75} strokeDasharray={g === 1 ? "2 3" : undefined} />
          ))}
          <path d={linePath(xs, gs.map((v) => (Number.isFinite(v) ? gY.map(v) : NaN)))} fill="none" stroke={C.gain} strokeWidth={1.5} />
        </g>

        {/* ---- Q-breakdown stack ---- */}
        <g transform={`translate(${ML},${bandH + zH + gH + 32})`}>
          <text x={-6} y={qY.map(qMax * 0.5)} dy="0.32em" textAnchor="end" className={C.ink}>Q</text>
          <line x1={0} x2={innerW} y1={qY.map(0)} y2={qY.map(0)} stroke={C.guide} strokeWidth={1} />
          {layers.map((l) => {
            const d = bandPath(xs, l.lo.map((v) => qY.map(v)), l.hi.map((v) => qY.map(v)));
            return d !== "" ? (
              <path key={l.key} d={d} fill={Q_COLORS[l.key]} opacity={0.75} stroke="var(--color-surface-800)" strokeWidth={1}>
                <title>{`Q ${l.key} (variance share)`}</title>
              </path>
            ) : null;
          })}
        </g>

        {/* ---- shared x axis ---- */}
        <g transform={`translate(${ML},${bandH + zH + gH + qH + 34})`}>
          {xTicks.map((i) => (
            <text key={`x${i}`} x={xs[i]} y={14} textAnchor="middle" className={C.ink}>
              {steps[i] ? stepLabel(steps[i].ts, multiDay) : ""}
            </text>
          ))}
        </g>
      </svg>

      {/* Legends: series identity is never color-alone (labels + swatches). */}
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[9px] text-slate-400">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px]" style={{ background: C.pred, opacity: 0.6 }} />m⁻ ± σ</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px]" style={{ background: C.obs, opacity: 0.6 }} />z ± σR</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px]" style={{ background: C.post }} />m⁺</span>
        <span className="text-slate-600">|</span>
        {Q_KEYS.filter((k) => activeKeys.has(k)).map((k) => (
          <span key={k}><span className="mr-1 inline-block h-2 w-2 rounded-[2px]" style={{ background: Q_COLORS[k] }} />{k}</span>
        ))}
        <span className="text-slate-600">|</span>
        <span style={{ color: MARKER_COLORS.reset }}>│ reset</span>
        <span style={{ color: MARKER_COLORS.seed }}>┆ seed</span>
        <span style={{ color: MARKER_COLORS.contaminated }}>┊ cont.</span>
      </div>
    </div>
  );
}

/** Self-contained panel section: expiry + handle selectors around the charts.
 *  Mounted by ObservationFilterPanel behind its "Timeline" toggle; serves the
 *  mock ring when the backend is unreachable (`live` false). */
export default function FilterTimelineSection({
  ticker, live, fitMode, refreshKey,
}: { ticker: string; live: boolean; fitMode: FitMode; refreshKey: unknown }) {
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [handle, setHandle] = useState(0);

  useEffect(() => {
    if (!live || !ticker) { setExpiries([]); setExpiry(""); return; }
    let cancelled = false;
    api
      .get<{ entries: { expiry: string }[] }>(`/forwards/${ticker}`)
      .then((f) => {
        if (cancelled) return;
        const exps = (f.entries ?? []).map((e) => e.expiry);
        setExpiries(exps);
        setExpiry((cur) => (cur !== "" && exps.includes(cur) ? cur : exps[0] ?? ""));
      })
      .catch(() => !cancelled && setExpiries([]));
    return () => { cancelled = true; };
  }, [live, ticker]);

  const { steps, source } = useFilterHistory(live, ticker, expiry, fitMode, refreshKey);

  return (
    <div className="mt-2 rounded-md border border-slate-800 bg-surface-800/40 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Filter timeline
          {source === "mock" && (
            <span className="ml-2 rounded bg-amber-500/15 px-1 py-px text-[9px] font-medium normal-case tracking-normal text-amber-400">
              MOCK
            </span>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          <select
            value={handle}
            onChange={(e) => setHandle(Number(e.target.value))}
            className={`${selectCls} w-20`}
            title="Which filtered handle to chart"
          >
            {HANDLES.map((h, i) => (
              <option key={h} value={i}>{h}</option>
            ))}
          </select>
          {live && (
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className={`${selectCls} w-28`}
              title="Node expiry"
            >
              {expiries.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          )}
        </span>
      </div>
      {steps.length === 0 ? (
        <p className="text-[10px] text-slate-600">
          No committed filter steps yet — calibrate with the filter on; the ring
          keeps the last 64 committed updates per node.
        </p>
      ) : (
        <FilterTimeline steps={steps} handle={handle} />
      )}
    </div>
  );
}
