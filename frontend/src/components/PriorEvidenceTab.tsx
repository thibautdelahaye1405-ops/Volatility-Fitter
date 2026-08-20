// Prior Evidence tab body (V3.9 item 8) — mounted by PriorPersistencePanel.
//
// Three evidence blocks, all read-only / poll-safe (usePriorEvidence):
//   1. per-ticker card — active prior age + source tier, saved-snapshot count
//      and a compact history list (savedTs → nodeCount);
//   2. innovation chart — |calibrated − transported prior| ATM bp per
//      (day, expiry): the honest "does the prior persist?" tape, straight
//      from the persisted graph innovation store;
//   3. residual decay curve — φ(dt) = 2^(−dt/H) for the ACTIVE layered
//      policy's residualHalfLifeDays, labeled as the GRAPH residual memory.
//
// THE DOCTRINE (backend filter_mode.py §6.3): the Kalman filter (temporal
// prior on the OBSERVED latent state) and the graph residual store (memory of
// the UNOBSERVED functional gap) are different objects — the copy below keeps
// them apart. `residualAgeDays` is marked on the curve only when the parent
// has a layered solve result in context (the Options panel has none, so the
// curve renders unmarked there).
import OverlayCurvesChart, { maturityColor } from "./OverlayCurvesChart";
import type { OverlaySeries } from "./OverlayCurvesChart";
import { usePriorEvidence } from "../state/usePriorEvidence";
import {
  ageDaysFromTs,
  decayAt,
  decayCurve,
  formatAge,
  shapeInnovationSeries,
  sourceLabel,
} from "../lib/priorEvidence";

const label = "text-xs text-slate-400";

/** "2026-06-08T19:46:12" → "2026-06-08 19:46" (compact list rendering). */
const fmtTs = (ts: string | null | undefined) =>
  ts ? ts.replace("T", " ").slice(0, 16) : "—";

/** Active-source tier chip tone: saved is the strong tier, ladder fallbacks
 *  are amber, none is muted. */
function sourceTone(source: string | null | undefined): string {
  if (source === "saved") return "border-emerald-500/50 bg-emerald-500/10 text-emerald-300";
  if (source === "15min" || source === "close")
    return "border-amber-500/50 bg-amber-500/10 text-amber-300";
  return "border-slate-700 bg-surface-800 text-slate-500";
}

/** The hand-rolled residual decay mini-chart (no zoom — a fixed evidence
 *  glyph, not an explorer). Bare SVG in a padded viewBox. */
function ResidualDecayCurve({
  halfLifeDays,
  residualAgeDays,
}: {
  halfLifeDays: number | null;
  residualAgeDays?: number | null;
}) {
  const W = 280;
  const H = 88;
  const M = { l: 26, r: 8, t: 8, b: 16 };
  const pts = decayCurve(halfLifeDays);
  const horizon = pts[pts.length - 1].dt;
  const x = (dt: number) => M.l + ((W - M.l - M.r) * dt) / horizon;
  const y = (phi: number) => M.t + (H - M.t - M.b) * (1 - phi);
  const path = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.dt).toFixed(1)},${y(p.phi).toFixed(1)}`)
    .join("");
  const age =
    residualAgeDays != null && Number.isFinite(residualAgeDays)
      ? Math.min(residualAgeDays, horizon)
      : null;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img">
      {[1, 0.5, 0].map((phi) => (
        <g key={phi}>
          <line
            x1={M.l} x2={W - M.r} y1={y(phi)} y2={y(phi)}
            stroke="var(--color-surface-700)" strokeWidth={1}
          />
          <text x={M.l - 4} y={y(phi)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[8px]">
            {phi}
          </text>
        </g>
      ))}
      {[0, horizon / 2, horizon].map((dt) => (
        <text key={dt} x={x(dt)} y={H - 4} textAnchor="middle" className="fill-slate-500 text-[8px]">
          {dt.toFixed(0)}d
        </text>
      ))}
      <path d={path} fill="none" stroke="rgb(56 189 248)" strokeWidth={1.5} />
      {age !== null && (
        <g>
          <circle
            cx={x(age)} cy={y(decayAt(halfLifeDays, age))} r={3.5}
            fill="rgb(56 189 248 / 0.2)" stroke="rgb(56 189 248)" strokeWidth={1.5}
          >
            <title>{`residual age ${age.toFixed(1)}d → φ ${decayAt(halfLifeDays, age).toFixed(2)}`}</title>
          </circle>
        </g>
      )}
    </svg>
  );
}

export default function PriorEvidenceTab({
  live,
  ticker,
  refreshKey,
  residualAgeDays,
}: {
  live: boolean;
  ticker: string;
  refreshKey: unknown;
  /** A layered solve result's residual age, when the parent has one in
   *  context; undefined leaves the decay curve unmarked. */
  residualAgeDays?: number | null;
}) {
  const { data, loading } = usePriorEvidence(live, ticker, refreshKey);
  if (data === null) {
    return <p className="mt-2 text-[10px] text-slate-600">Loading prior evidence…</p>;
  }
  const { status, history, innovations, residualHalfLifeDays, mock } = data;
  const shaped = shapeInnovationSeries(innovations);
  const chartSeries: OverlaySeries[] = shaped.series.map((s, i) => ({
    label: s.expiry,
    xs: shaped.days.map((_, j) => j),
    ys: s.values.map((v) => (v === null ? NaN : v)),
    color: maturityColor(shaped.series.length > 1 ? i / (shaped.series.length - 1) : 0),
  }));
  const activeAge =
    ageDaysFromTs(status?.activeDataTs, Date.now()) ?? status?.activeAgeDays ?? null;
  const savedAge = ageDaysFromTs(status?.dataTs, Date.now()) ?? status?.ageDays ?? null;

  return (
    <div className="mt-2 space-y-3">
      {mock && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300">
          Mock evidence — start the backend for live prior data.
        </p>
      )}

      {/* 1 — per-ticker prior age / source tier / snapshot history */}
      <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Prior status{ticker ? ` · ${ticker}` : ""}
          </span>
          <span
            className={`rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${sourceTone(status?.activeSource)}`}
            title="Which freshness-ladder branch the ACTIVE prior came from (saved | 15min | close | none)"
          >
            {sourceLabel(status?.activeSource)}
          </span>
          {loading && <span className="text-[9px] text-slate-600">refreshing…</span>}
        </div>
        {status === null ? (
          <p className="text-[10px] text-slate-600">No prior status for this ticker.</p>
        ) : (
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
            <span className={label}>Active prior age</span>
            <span className="text-right font-mono text-slate-200">{formatAge(activeAge)}</span>
            <span className={label}>Latest saved (age)</span>
            <span className="text-right font-mono text-slate-200">
              {fmtTs(status.dataTs)} ({formatAge(savedAge)})
            </span>
            <span className={label}>Nodes · LV</span>
            <span className="text-right font-mono text-slate-200">
              {status.nodeCount} · {status.hasLvSurface ? "yes" : "no"}
            </span>
            <span className={label}>Saved snapshots</span>
            <span className="text-right font-mono text-slate-200">{history.length}</span>
          </div>
        )}
        {history.length > 0 && (
          <div className="mt-1 border-t border-slate-800 pt-1">
            {history.slice(0, 6).map((h) => (
              <div key={h.savedTs + h.dataTs} className="flex justify-between font-mono text-[9px] text-slate-500">
                <span>{fmtTs(h.savedTs)}</span>
                <span>{h.asOfLabel}</span>
                <span>{h.nodeCount} nodes</span>
              </div>
            ))}
            {history.length > 6 && (
              <p className="text-[9px] text-slate-600">+{history.length - 6} older saves</p>
            )}
          </div>
        )}
      </div>

      {/* 2 — the persisted innovation tape: prior vs market distance over time */}
      <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2">
        <div
          className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500"
          title="|calibrated − transported prior| ATM vol per (day, expiry), straight from the persisted graph innovation store — recorded whenever a lit node calibrates under a graph solve"
        >
          Prior vs market over time
        </div>
        {shaped.days.length === 0 ? (
          <p className="text-[10px] text-slate-600">
            No recorded innovations yet — they are recorded per (day, expiry)
            whenever a graph solve sees a lit, calibrated node.
          </p>
        ) : (
          <div className="h-44">
            <OverlayCurvesChart
              series={chartSeries}
              xLabel="as-of day"
              yLabel="|innovation| (bp)"
              zeroBaseline
              formatX={(v) => shaped.days[Math.round(v)]?.slice(5) ?? ""}
            />
          </div>
        )}
      </div>

      {/* 3 — GRAPH residual memory (kept explicitly distinct from the Kalman filter) */}
      <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Graph residual memory
        </div>
        <p className="mb-1 text-[9px] text-slate-500">
          φ(dt) = 2^(−dt/H),{" "}
          {residualHalfLifeDays !== null
            ? `H = ${residualHalfLifeDays}d (active layered policy)`
            : "no half-life — fully persistent (random walk)"}
          . This is the decay of the <span className="text-slate-300">graph residual store</span>{" "}
          (the node's unobserved functional gap carried between solves) — a
          distinct object from the <span className="text-slate-300">Kalman observation filter</span>{" "}
          (a temporal prior on the observed latent state).
        </p>
        <ResidualDecayCurve
          halfLifeDays={residualHalfLifeDays}
          residualAgeDays={residualAgeDays}
        />
      </div>
    </div>
  );
}
