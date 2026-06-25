// Prior-persistence controls + diagnostics (roadmap Phase 7; design note §10/§9.4).
//
// The single mode selector picks how a fetched prior is persisted into the
// calibration; the knobs shown are grouped by the active mode. The diagnostics
// table below makes the prior auditable (which operators/factors are persisted,
// their activation gap and final weight) — "the prior is not a hidden stabilizer".
//
// Lives outside OptionsViewer (file-size policy); driven by the same Options draft.
import { useEffect, useRef, useState } from "react";

import { NumberRow, Toggle } from "./OptionsControls";
import { api } from "../state/api";
import type { OptionsSettings, PriorPersistenceMode } from "../state/useOptions";
import type { FitMode } from "../state/useSmile";

const MODES: { id: PriorPersistenceMode; label: string; hint: string }[] = [
  { id: "off", label: "Off", hint: "No prior overlay or calibration penalty — pure current market." },
  { id: "overlay", label: "Overlay only", hint: "Draw the transported prior, no calibration penalty." },
  { id: "strike_gap", label: "Strike gaps", hint: "Legacy data-gap synthetic anchors — preserve unquoted wings." },
  { id: "quote_operator", label: "Quote operators", hint: "Persist ATM / RR / BF / var-swap only where under-observed." },
  { id: "smile_factor", label: "Smile factors", hint: "Persist ATM-local level / skew / curvature distance to the prior." },
  { id: "hybrid", label: "Hybrid", hint: "Operators + a residual deep-tail strike anchor (the recommended default)." },
  { id: "graph_only", label: "Graph only", hint: "Lit calibration stays market-pure; the graph carries the prior for dark nodes." },
];

const OPERATOR_OPTS = ["ATM", "RR25", "BF25", "RR10", "BF10", "VarSwap"];
const FACTOR_OPTS = ["ATM", "skew", "curvature", "leftWing", "rightWing", "VarSwap"];

interface PriorOperatorDiag {
  operator: string;
  priorValue: number;
  obsPrecision: number;
  requiredPrecision: number;
  gap: number;
  activeLambda: number;
}
interface PriorDiagnostics {
  mode: string;
  active: boolean;
  operators: PriorOperatorDiag[];
  varSwapPriorVol: number | null;
  varSwapWeight: number | null;
  strikeAnchorCount: number | null;
}

const rowLabel = "text-xs text-slate-400";
const numInput =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** A canonical-order multi-select of operator / factor names. */
function ChipSet({
  all, value, onChange, disabled,
}: { all: string[]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  const toggle = (name: string) => {
    const set = new Set(value);
    set.has(name) ? set.delete(name) : set.add(name);
    onChange(all.filter((a) => set.has(a))); // keep canonical order
  };
  return (
    <div className="flex flex-wrap gap-1">
      {all.map((name) => {
        const on = value.includes(name);
        return (
          <button
            key={name}
            type="button"
            disabled={disabled}
            onClick={() => toggle(name)}
            className={[
              "rounded px-1.5 py-0.5 font-mono text-[10px] border transition-colors",
              on
                ? "border-accent-500/60 bg-accent-500/15 text-accent-300"
                : "border-slate-700 bg-surface-800 text-slate-400 hover:border-slate-600",
              disabled ? "cursor-not-allowed opacity-50" : "",
            ].join(" ")}
          >
            {name}
          </button>
        );
      })}
    </div>
  );
}

export default function PriorPersistencePanel({
  draft, patch, live, ticker, fitMode, refreshKey,
}: {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
  ticker: string;
  fitMode: FitMode;
  refreshKey: unknown; // bump to refetch diagnostics (e.g. after Apply)
}) {
  const mode = draft.priorPersistenceMode;
  const disabled = !live;
  const showStrike = mode === "strike_gap" || mode === "hybrid";
  const showOperators = mode === "quote_operator" || mode === "hybrid";
  const showFactors = mode === "smile_factor";
  const sharedGate = showOperators || showFactors;

  // Comma-separated %-per-side delta editor (commits on blur), shared by the
  // strike-gap anchor and the hybrid deep-tail anchor.
  const fmtDeltas = (ds: number[]) => ds.map((d) => +(d * 100).toFixed(2)).join(", ");
  const [deltaText, setDeltaText] = useState(() => fmtDeltas(draft.priorAnchorDeltas));
  const deltaRef = useRef(draft.priorAnchorDeltas);
  useEffect(() => {
    if (draft.priorAnchorDeltas !== deltaRef.current) {
      deltaRef.current = draft.priorAnchorDeltas;
      setDeltaText(fmtDeltas(draft.priorAnchorDeltas));
    }
  }, [draft.priorAnchorDeltas]);
  const commitDeltas = () => {
    const parsed = deltaText.split(/[,\s]+/).map(Number).filter((x) => Number.isFinite(x) && x > 0 && x < 50);
    const ds = Array.from(new Set(parsed.map((x) => +(x / 100).toFixed(4)))).sort((a, b) => a - b);
    const next = ds.length ? ds : draft.priorAnchorDeltas;
    deltaRef.current = next;
    setDeltaText(fmtDeltas(next));
    patch({ priorAnchorDeltas: next });
  };

  return (
    <div className="mt-4 border-t border-slate-800 pt-3">
      <div className="mb-2 flex items-center justify-between">
        <span className={rowLabel} title="How a fetched prior is persisted into the calibration (design note §10)">
          Prior persistence
        </span>
        <select
          value={mode}
          disabled={disabled}
          onChange={(e) => patch({ priorPersistenceMode: e.target.value as PriorPersistenceMode })}
          className={`${numInput} w-40`}
        >
          {MODES.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      </div>
      <p className="mb-2 text-[10px] text-slate-500">
        {MODES.find((m) => m.id === mode)?.hint} Applies once a prior has been fetched
        (Save / Fetch priors); pick <span className="text-slate-300">Off</span> to disable.
      </p>

      {/* strike-gap anchor knobs (also the hybrid deep-tail anchor placements) */}
      {showStrike && (
        <div className="space-y-1">
          {mode === "strike_gap" && (
            <NumberRow label="Anchor weight (%)" value={draft.priorAnchorWeightPct} step={5}
              disabled={disabled} onChange={(v) => patch({ priorAnchorWeightPct: v })} />
          )}
          {mode === "hybrid" && (
            <NumberRow label="Tail-anchor weight (%)" value={draft.priorTailAnchorStrengthPct} step={5}
              disabled={disabled} onChange={(v) => patch({ priorTailAnchorStrengthPct: v })} />
          )}
          <div className="flex items-center justify-between">
            <span className={rowLabel} title="Per-side delta-locations (%, comma-separated). Hybrid uses the deltas below the shallowest wing operator as the deep-tail anchor.">
              {mode === "hybrid" ? "Tail Δ (%, per side)" : "Anchor Δ (%, per side)"}
            </span>
            <input
              type="text" value={deltaText} disabled={disabled}
              onChange={(e) => setDeltaText(e.target.value)} onBlur={commitDeltas}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
              className={`${numInput} w-32`}
            />
          </div>
        </div>
      )}

      {/* quote-operator knobs */}
      {showOperators && (
        <div className="mt-2 space-y-2">
          <NumberRow label="Operator strength (%)" value={draft.priorOperatorStrengthPct} step={5}
            disabled={disabled} onChange={(v) => patch({ priorOperatorStrengthPct: v })} />
          <div>
            <span className={`${rowLabel} mb-1 block`}>Operators</span>
            <ChipSet all={OPERATOR_OPTS} value={draft.priorOperatorSet} disabled={disabled}
              onChange={(v) => patch({ priorOperatorSet: v })} />
          </div>
          <div className="flex items-center justify-between">
            <span className={rowLabel} title="Risk-reversal sign: call-minus-put or put-minus-call">Collar sign</span>
            <select value={draft.collarSign} disabled={disabled}
              onChange={(e) => patch({ collarSign: e.target.value as "call_put" | "put_call" })}
              className={`${numInput} w-32`}>
              <option value="call_put">Call − Put</option>
              <option value="put_call">Put − Call</option>
            </select>
          </div>
        </div>
      )}

      {/* smile-factor knobs */}
      {showFactors && (
        <div className="mt-2 space-y-2">
          <NumberRow label="Factor strength (%)" value={draft.priorFactorStrengthPct} step={5}
            disabled={disabled} onChange={(v) => patch({ priorFactorStrengthPct: v })} />
          <div>
            <span className={`${rowLabel} mb-1 block`}>Factors</span>
            <ChipSet all={FACTOR_OPTS} value={draft.priorFactorSet} disabled={disabled}
              onChange={(v) => patch({ priorFactorSet: v })} />
          </div>
        </div>
      )}

      {/* shared activation-gate knobs (operators + factors) */}
      {sharedGate && (
        <div className="mt-2 space-y-1">
          <NumberRow label="Required precision" value={draft.priorOperatorRequiredPrecision} step={0.5}
            disabled={disabled} onChange={(v) => patch({ priorOperatorRequiredPrecision: v })} />
          <NumberRow label="Gap exponent γ" value={draft.priorOperatorGapExponent} step={0.5}
            disabled={disabled} onChange={(v) => patch({ priorOperatorGapExponent: v })} />
          <NumberRow label="Support bandwidth / step" value={draft.priorOperatorBandwidth} step={0.01}
            disabled={disabled} onChange={(v) => patch({ priorOperatorBandwidth: v })} />
          <Toggle label="Two-pass (don't damp signal)"
            hint="Fit data-only first, then refit anchoring only the under-observed factors — so a well-observed move (e.g. a tight ATM) is never pulled back. Slower (~2x per node)."
            checked={draft.priorDataOnlyPrepass} disabled={disabled}
            onChange={(v) => patch({ priorDataOnlyPrepass: v })} />
        </div>
      )}

      {(mode === "off" || mode === "overlay" || mode === "graph_only") && (
        <p className="text-[10px] text-slate-600">
          No calibration penalty in this mode{mode === "overlay" ? " (the dotted prior is still drawn)" : ""}.
        </p>
      )}

      <PriorDiagnosticsTable ticker={ticker} live={live} fitMode={fitMode} refreshKey={refreshKey} />
    </div>
  );
}

/** The §9.4 audit table: per-expiry active operators with their gap + weight. */
function PriorDiagnosticsTable({
  ticker, live, fitMode, refreshKey,
}: { ticker: string; live: boolean; fitMode: FitMode; refreshKey: unknown }) {
  const [rows, setRows] = useState<{ expiry: string; diag: PriorDiagnostics }[]>([]);
  useEffect(() => {
    if (!live || !ticker) { setRows([]); return; }
    let cancelled = false;
    api
      .get<{ entries: { expiry: string }[] }>(`/forwards/${ticker}`)
      .then(async (f) => {
        const exps = (f.entries ?? []).map((e) => e.expiry).slice(0, 8);
        const diags = await Promise.all(
          exps.map((e) =>
            api
              .get<PriorDiagnostics>(`/smiles/${ticker}/${e}/prior-diagnostics?fit_mode=${fitMode}`)
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        setRows(
          exps
            .map((e, i) => ({ expiry: e, diag: diags[i] }))
            .filter((r): r is { expiry: string; diag: PriorDiagnostics } => !!r.diag && r.diag.active),
        );
      })
      .catch(() => !cancelled && setRows([]));
    return () => { cancelled = true; };
  }, [live, ticker, fitMode, refreshKey]);

  return (
    <div className="mt-3 rounded-md border border-slate-800 bg-surface-800/40 p-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Prior diagnostics{ticker ? ` · ${ticker}` : ""}
      </div>
      {rows.length === 0 ? (
        <p className="text-[10px] text-slate-600">
          No active prior (enable Auto-load prior, pick a mode, and fetch a prior).
        </p>
      ) : (
        <table className="w-full text-[10px] text-slate-300">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-medium">Expiry</th>
              <th className="text-left font-medium">Factor</th>
              <th className="text-right font-medium" title="Activation gap (1 = fully persisted, 0 = data wins)">gap</th>
              <th className="text-right font-medium" title="Final calibration weight λ">λ</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {rows.flatMap((r) =>
              r.diag.operators.length
                ? r.diag.operators.map((op, j) => (
                    <tr key={`${r.expiry}-${op.operator}`}>
                      <td className="text-slate-500">{j === 0 ? r.expiry : ""}</td>
                      <td>{op.operator}</td>
                      <td className="text-right">{op.gap.toFixed(2)}</td>
                      <td className="text-right">{op.activeLambda.toFixed(2)}</td>
                    </tr>
                  ))
                : [
                    <tr key={r.expiry}>
                      <td className="text-slate-500">{r.expiry}</td>
                      <td colSpan={3} className="text-slate-500">
                        {r.diag.strikeAnchorCount
                          ? `${r.diag.strikeAnchorCount} strike anchors`
                          : r.diag.varSwapPriorVol != null
                            ? `var-swap ${(r.diag.varSwapPriorVol * 100).toFixed(1)}%`
                            : "active"}
                      </td>
                    </tr>,
                  ],
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
