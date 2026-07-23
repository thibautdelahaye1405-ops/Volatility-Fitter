// Timeline preview (P6 V3): the framework §5 asynchronous A/B example as an
// interactive fixture — how the layered operator behaves through TIME, which
// a single-snapshot preview cannot show. A prints every day; B prints at
// t=0 and t=3.5 (a −3pt dislocation). Between prints B rides its directed
// parent (systematic β·m) plus its OWN remembered dislocation u, decaying by
// the half-life. Drag the scrubber; tune β / half-life; read the exact
// three-part decomposition at the scrubbed snapshot (lib/dynamicTimeline —
// vitest-locked to the SAME goldens the production state layer reproduces).
import { useMemo, useState } from "react";
import { AB_FIXTURE, replayAB } from "../../lib/dynamicTimeline";

const W = 460;
const H = 120;
const PAD = 14;

/** Map (t, v) to SVG coordinates over the fixture's value range. */
function scales(points: { t: number; a: number; b: number }[]) {
  const ts = points.map((p) => p.t);
  const vs = points.flatMap((p) => [p.a, p.b]);
  const t0 = Math.min(...ts);
  const t1 = Math.max(...ts);
  const v0 = Math.min(...vs) - 1;
  const v1 = Math.max(...vs) + 1;
  return {
    x: (t: number) => PAD + ((t - t0) / (t1 - t0)) * (W - 2 * PAD),
    y: (v: number) => H - PAD - ((v - v0) / (v1 - v0)) * (H - 2 * PAD),
  };
}

const fmt = (v: number) => (v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2));

export default function TimelinePreview() {
  const [beta, setBeta] = useState(1);
  const [halfLife, setHalfLife] = useState<number | null>(null);
  const [step, setStep] = useState(AB_FIXTURE.snapshots.length - 1);

  const points = useMemo(
    () =>
      replayAB(
        AB_FIXTURE.snapshots, AB_FIXTURE.obsA, AB_FIXTURE.obsB, beta, halfLife,
      ),
    [beta, halfLife],
  );
  const { x, y } = useMemo(() => scales(points), [points]);
  const at = points[Math.min(step, points.length - 1)];

  const path = (key: "a" | "b") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t)},${y(p[key])}`).join(" ");

  return (
    <div data-testid="timeline-preview" className="mt-3 rounded-md border border-slate-800 bg-surface-800/50 p-2">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span
          className="text-[10px] font-semibold uppercase tracking-wide text-slate-500"
          title="The framework §5 asynchronous A/B fixture: A prints daily; B prints at t=0 and t=3.5 (−3pt dislocation). Between prints B = β·A + its own remembered residual."
        >
          Timeline · §5 A/B fixture
        </span>
        <label className="ml-auto flex items-center gap-1 text-[10px] text-slate-500" title="Directed transfer slope: B's systematic prediction is β × A's last print">
          β
          <input
            type="number"
            step={0.5}
            value={beta}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) setBeta(v);
            }}
            className="w-14 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500"
          />
        </label>
        <label className="flex items-center gap-1 text-[10px] text-slate-500" title="Residual half-life (days): how fast B's remembered −3pt dislocation decays. Empty = never (random walk)">
          half-life
          <input
            type="number"
            step={0.5}
            min={0}
            placeholder="∞"
            value={halfLife ?? ""}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              setHalfLife(Number.isFinite(v) && v > 0 ? v : null);
            }}
            className="w-14 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500"
          />
        </label>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {/* A: the directed parent (step-ish path through its prints). */}
        <path d={path("a")} fill="none" stroke="#64748b" strokeWidth={1.2} />
        {/* B: prediction riding A with residual memory. */}
        <path d={path("b")} fill="none" stroke="#38bdf8" strokeWidth={1.5} />
        {points.map((p) => (
          <g key={p.t}>
            {p.aObserved && (
              <circle cx={x(p.t)} cy={y(p.a)} r={2.2} fill="#64748b" />
            )}
            {p.bObserved && (
              <circle cx={x(p.t)} cy={y(p.b)} r={3} fill="#f59e0b" />
            )}
          </g>
        ))}
        {/* Scrub cursor. */}
        <line
          x1={x(at.t)} x2={x(at.t)} y1={PAD / 2} y2={H - PAD / 2}
          stroke="#e2e8f0" strokeOpacity={0.35} strokeDasharray="3 2"
        />
        <circle cx={x(at.t)} cy={y(at.b)} r={3.2} fill="none" stroke="#38bdf8" strokeWidth={1.4} />
      </svg>

      <input
        type="range"
        min={0}
        max={AB_FIXTURE.snapshots.length - 1}
        step={1}
        value={step}
        onChange={(e) => setStep(Number(e.target.value))}
        className="w-full accent-accent-500"
        title="Scrub through the snapshots"
      />
      <p className="font-mono text-[10px] text-slate-300" data-testid="timeline-readout">
        t {at.t.toFixed(1)} · A {at.a.toFixed(1)}
        {" · B "}
        <span className="text-accent-300">{at.b.toFixed(2)}</span>
        <span className="text-slate-500">
          {" = systematic "}
          {at.systematic.toFixed(2)}
          {" + residual "}
          {fmt(at.u)}
        </span>
        {at.bObserved && (
          <span className="ml-1 rounded bg-amber-500/15 px-1 text-[9px] uppercase tracking-wide text-amber-300">
            B prints
          </span>
        )}
      </p>
      <p className="mt-0.5 text-[9px] text-slate-600">
        Zero reverse influence: B's −3pt print never moves A. The residual is
        B's OWN memory — it survives B going dark and decays by the half-life.
      </p>
    </div>
  );
}
