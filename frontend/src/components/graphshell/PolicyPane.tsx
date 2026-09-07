// Graph shell LEFT pane (GRAPH ERGONOMICS ARC, E4) — the Relationships pane
// rebuilt around THREE disclosure levels, never one flat list:
//
//   Level 0  what a trader touches every day: the amplitude preset (Desk |
//            Learned), the calendar switch + its confidence slider, the
//            cross-asset confidence slider (both σ in vol points on the same
//            anchors the canvas arrows use), the live +1 pt example, and the
//            Relations shortcut into the drawer.
//   Level 1  Fine-tune — shape / family dials (αT, ρ per class, decay, ε,
//            cross-expiry tolerance), the per-ticker calendar overrides + the
//            ladder view, the receiver × informer matrix, and the Dynamics
//            policy (Layered only).
//   Level 2  Advanced — the units lens (raw precision) and the door to the
//            legacy Smooth-field operator (η/κ/λ/ν, autotune, the weight
//            matrix), which takes over the pane while it is selected.
//
// The relation editors are fed by the SELECTED universe (GET /universe — what
// the production solve propagates over); the sandbox lattice is only a
// fallback (regression 2026-07-09).
import { useEffect, useMemo, useState } from "react";
import { Grid3x3, ListTree } from "lucide-react";
import CalendarPolicyCard, { calendarLiveExample } from "./CalendarPolicyCard";
import CrossMatrixCard from "./CrossMatrixCard";
import DynamicsPolicyCard from "./DynamicsPolicyCard";
import SigmaSlider from "./SigmaSlider";
import EdgeMatrixEditor from "../EdgeMatrixEditor";
import SegmentedControl from "../SegmentedControl";
import Slider from "../Slider";
import SolverPanel, { DEFAULT_CALENDAR_WEIGHT, DEFAULT_CROSS_WEIGHT, EdgeWeightInput } from "../SolverPanel";
import { AMPLITUDE_PRESETS } from "../../lib/messagePreview";
import { api } from "../../state/api";
import type { CalendarDecay, PropagationMode, UseGraphResult } from "../../state/useGraph";
import type { MessageConfigPair } from "../../state/useMessageConfig";
import type { MessageEdgeRow } from "../../state/useMessageEdges";
import type { UniverseResponse } from "../../state/useSmile";

interface PolicyPaneProps {
  graph: UseGraphResult;
  mode: PropagationMode;
  setMode: (m: PropagationMode) => void;
  /** The U6 lifecycle pair — seeds the Dynamics policy card. */
  config: MessageConfigPair | null;
  /** Fired after a policy / legacy-matrix save (parent refreshes + re-runs). */
  onSaved: () => void;
  /** Smooth-field cross-ticker β (rides both sources since U3). */
  crossBeta: number;
  setCrossBeta: (v: number) => void;
  /** Effective relation rows (the matrix cells). */
  rows: MessageEdgeRow[];
  /** Open the drawer's Relations tab. */
  onOpenRelations: () => void;
  /** Units lens (σ pts default / raw precision) — shared with the inspector. */
  raw: boolean;
  setRaw: (v: boolean) => void;
}

type PresetKey = "desk" | "learned" | "custom";
function presetOf(p: { ampCal: number; ampCross: number }): PresetKey {
  for (const [key, v] of Object.entries(AMPLITUDE_PRESETS))
    if (p.ampCal === v.ampCal && p.ampCross === v.ampCross) return key as PresetKey;
  return "custom";
}

const numCls =
  "w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500";
const selCls =
  "rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500";
const btn =
  "flex w-full items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      {children}
    </section>
  );
}

export default function PolicyPane({
  graph,
  mode,
  setMode,
  config,
  onSaved,
  crossBeta,
  setCrossBeta,
  rows,
  onOpenRelations,
  raw,
  setRaw,
}: PolicyPaneProps) {
  const { params, setParam } = graph;
  const messages = mode !== "smooth_field";
  const layered = mode === "layered_dynamic_harmonic";
  const [editingLegacy, setEditingLegacy] = useState(false);

  // The selected universe (ladders + tickers) for the cards and editors.
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .get<UniverseResponse>("/universe")
      .then((u) => {
        if (alive) setUniverse(u);
      })
      .catch(() => {
        /* the cards degrade to knob-only rendering */
      });
    return () => {
      alive = false;
    };
  }, [messages, editingLegacy]);
  const editorNodes = useMemo(
    () =>
      universe !== null && universe.tickers.length > 0
        ? universe.tickers.flatMap((t) => (universe.expiries[t] ?? []).map((e) => ({ ticker: t, expiry: e.expiry })))
        : (graph.nodes ?? []).map((n) => ({ ticker: n.ticker, expiry: n.expiry })),
    [universe, graph.nodes],
  );
  const tickers = useMemo(() => [...new Set(editorNodes.map((n) => n.ticker))], [editorNodes]);
  const preset = presetOf(params);

  /* ------------------------------ legacy ------------------------------ */
  if (!messages) {
    return (
      <aside className="flex w-72 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30" data-testid="policy-pane">
        <div className="mb-1 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Legacy smooth field</h3>
        </div>
        <p className="mb-3 text-[11px] text-slate-500">
          Graph coupling of the smooth field: calendar and cross-ticker edge weights, the η/κ/λ/ν dials.
        </p>
        <div className="flex flex-col gap-3">
          <Section title="Weights">
            <EdgeWeightInput label="Calendar (same ticker)" title="Weight of within-ticker calendar edges." value={params.calendarWeight} fallback={DEFAULT_CALENDAR_WEIGHT} onChange={(v) => setParam("calendarWeight", v)} />
            <EdgeWeightInput label="Cross-ticker" title="Weight of equal-expiry edges between tickers." value={params.crossWeight} fallback={DEFAULT_CROSS_WEIGHT} onChange={(v) => setParam("crossWeight", v)} />
            <label className="flex items-center justify-between gap-2 text-xs text-slate-400" title="Level-transfer slope applied on cross-ticker edges (smooth field).">
              <span>Cross-ticker β</span>
              <input type="number" step={0.1} value={crossBeta} onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v)) setCrossBeta(v); }} className={numCls} />
            </label>
            <label className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-400" title="Cross-venue asynchronous expiries: pair a rung with the other ticker's NEAREST expiry up to this many days apart. 0 = exact-date matching only.">
              <span>Cross-expiry tol (d)</span>
              <input type="number" step={1} min={0} value={params.crossExpiryToleranceDays} onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v) && v >= 0) setParam("crossExpiryToleranceDays", v); }} className={numCls} />
            </label>
            <button className={btn + " mt-2"} onClick={() => setEditingLegacy((v) => !v)} title="Edit the per-edge graph weights + beta">
              <Grid3x3 size={12} strokeWidth={1.75} className="opacity-80" />
              {editingLegacy ? "Done" : "Edges"}
            </button>
          </Section>
          <SolverPanel params={params} setParam={setParam} resetParams={graph.resetParams} litCount={Object.keys(graph.lit).length} autotune={() => void graph.autotune()} autotuning={graph.autotuning} autotuneResult={graph.autotuneResult} autotuneError={graph.autotuneError} />
          <button className={btn} onClick={() => setMode("layered_dynamic_harmonic")} title="Back to the Layered operator (the default)">
            ← Back to Layered
          </button>
        </div>
        {editingLegacy && (
          <EdgeMatrixEditor tickers={tickers} nodes={editorNodes} onSaved={onSaved} onClose={() => setEditingLegacy(false)} />
        )}
      </aside>
    );
  }

  /* ------------------------ message family (L0-L2) ------------------------ */
  return (
    <aside className="flex w-72 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30" data-testid="policy-pane">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-100">Coupling</h3>
        <SegmentedControl
          options={
            preset === "custom"
              ? ([{ id: "desk", label: "Desk" }, { id: "learned", label: "Learned" }, { id: "custom", label: "Custom" }] as const)
              : ([{ id: "desk", label: "Desk" }, { id: "learned", label: "Learned" }] as const)
          }
          value={preset}
          onChange={(key) => {
            if (key === "custom") return;
            setParam("ampCal", AMPLITUDE_PRESETS[key].ampCal);
            setParam("ampCross", AMPLITUDE_PRESETS[key].ampCross);
          }}
          size="xs"
        />
      </div>
      <p className="mb-3 text-[11px] text-slate-500" title="Amplitude preset: Desk = full configured force (ρ = 1); Learned = the day-horizon single-source targets (calendar 0.23, cross 0.39)">
        How each smile informs its neighbors — {layered ? "directed parents, remembered dislocations, harmonic completion." : "calendar and cross-asset messages."}
      </p>

      <div className="flex flex-col gap-3">
        <Section title="Confidence">
          <label className="mb-1 flex items-center gap-2 text-xs text-slate-300" title="Calendar policy switch — off suppresses every calendar factor (auto ladders and persisted calendar rows); cross-asset relations keep flowing">
            <input type="checkbox" checked={params.calendarEnabled} onChange={(e) => setParam("calendarEnabled", e.target.checked)} className="accent-accent-500" />
            Calendar relations
          </label>
          <SigmaSlider
            label="Calendar @ ref distance"
            title="Calendar relationship uncertainty at the reference maturity distance (ε + √gap = 1) — the §9.2 family widens it with the gap. Right = more confident."
            precision={params.calPrecision}
            raw={raw}
            onChange={(p) => setParam("calPrecision", Math.max(p, 1))}
            disabled={!params.calendarEnabled}
            muted={!params.calendarEnabled}
            testId="slider-cal"
          />
          <div className="mt-2">
            <SigmaSlider
              label="Cross-asset"
              title="Cross-asset relationship uncertainty (one factor, receiver units). Right = more confident."
              precision={params.crossPrecision}
              raw={raw}
              onChange={(p) => setParam("crossPrecision", Math.max(p, 1))}
              testId="slider-cross"
            />
          </div>
          {params.calendarEnabled && (
            <p className="mt-2 rounded-md border border-slate-800 bg-surface-800/60 px-2 py-1 font-mono text-[10px] text-slate-400" data-testid="cal-live-example" title="Live example on the canonical 3M/6M pair — exactly the solver's §8.2 shape and §9.2 precision family under the current dials">
              {calendarLiveExample(params)}
            </p>
          )}
        </Section>

        <button className={btn} onClick={onOpenRelations} title="Open the Relations tab — every arrow of the canvas as a row (search, filter, templates, undo)" data-testid="open-relations">
          <ListTree size={12} strokeWidth={1.75} className="opacity-80" />
          Relations · {rows.length}
        </button>

        {/* Level 1 */}
        <details data-testid="fine-tune">
          <summary className="cursor-pointer text-[11px] text-slate-400 transition-colors hover:text-slate-200">
            Fine-tune <span className="text-slate-600">· shape · family · overrides{layered ? " · dynamics" : ""}</span>
          </summary>
          <div className="mt-2 flex flex-col gap-3">
            <Section title="Shape & family">
              <Slider label="Calendar shape αT" title="Maturity-shape exponent: β = (T_informer/T_receiver)^αT. 1.0 = constant total-variance injection (locked default)." value={params.alphaT} min={0} max={2} step={0.05} mark={1} format={(v) => v.toFixed(2)} onChange={(v) => setParam("alphaT", v)} onReset={() => setParam("alphaT", 1)} resetTitle="Back to αT = 1" />
              <Slider className="mt-2" label="ρ calendar" title="Calendar amplitude level (1 = full force; learned day-horizon ≈ 0.23)." value={params.ampCal} min={0.05} max={1} step={0.01} format={(v) => v.toFixed(2)} onChange={(v) => setParam("ampCal", v)} />
              <Slider className="mt-2" label="ρ cross-asset" title="Cross-class amplitude level (1 = full force; learned single-source ≈ 0.39)." value={params.ampCross} min={0.05} max={1} step={0.01} format={(v) => v.toFixed(2)} onChange={(v) => setParam("ampCross", v)} />
              <div className="mt-2 flex items-center justify-between" title="Calendar relation-precision family: p = scale / (ε + √|ΔT|) by default.">
                <span className="text-xs text-slate-400">Calendar decay</span>
                <select className={selCls} value={params.calDecay} onChange={(e) => setParam("calDecay", e.target.value as CalendarDecay)}>
                  <option value="inverse_sqrt_gap">inverse √gap</option>
                  <option value="constant">constant</option>
                  <option value="log_distance">log distance</option>
                </select>
              </div>
              <label className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-400" title="Caps the precision of near-identical expiries (Phase-0 seed 0.97).">
                <span>Calendar ε (√years)</span>
                <input type="number" step={0.05} value={params.calEpsilon} onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v)) setParam("calEpsilon", Math.max(v, 0.01)); }} className={numCls} />
              </label>
              <label className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-400" title="Cross-venue asynchronous expiries: pair a rung with the other ticker's NEAREST expiry up to this many days apart (precision decays with the gap; the maturity-shape β applies). 0 = exact-date matching only.">
                <span>Cross-expiry tol (d)</span>
                <input type="number" step={1} min={0} value={params.crossExpiryToleranceDays} onChange={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v) && v >= 0) setParam("crossExpiryToleranceDays", v); }} className={numCls} />
              </label>
            </Section>
            <Section title="Calendar overrides">
              <CalendarPolicyCard params={params} setParam={setParam} raw={raw} tickers={universe?.tickers ?? []} expiries={universe?.expiries ?? {}} dials={false} />
            </Section>
            <Section title="Cross-asset matrix">
              <CrossMatrixCard params={params} setParam={setParam} raw={raw} tickers={universe?.tickers ?? []} rows={rows} onDrillIn={onOpenRelations} dials={false} />
            </Section>
            {layered && (
              <Section title="Dynamics">
                <DynamicsPolicyCard config={config} onSaved={onSaved} />
              </Section>
            )}
          </div>
        </details>

        {/* Level 2 */}
        <details data-testid="advanced">
          <summary className="cursor-pointer text-[11px] text-slate-500 transition-colors hover:text-slate-300">
            Advanced <span className="text-slate-600">· units · legacy operator</span>
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <button className={btn} onClick={() => setRaw(!raw)} title="Confidence units: relationship uncertainty σ = 1/√p in vol points (default) vs the raw conditional precision p (1/vol²)">
              {raw ? "units: raw p" : "units: σ pts"}
            </button>
            <button className={btn} onClick={() => setMode("smooth_field")} title="Switch to the legacy smooth-field operator (η/κ/λ/ν, autotune, the weight matrix) — the explicit rollback">
              Smooth field (legacy)
            </button>
          </div>
        </details>
      </div>
    </aside>
  );
}
