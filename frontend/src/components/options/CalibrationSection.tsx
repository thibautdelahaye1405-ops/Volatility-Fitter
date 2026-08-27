// Options ▸ Calibration: what all fits target and how residuals are weighted —
// fit target, haircut, quote weighting, band mid anchor, calendar-arbitrage
// enforcement, the extrapolation guard, and the variance-swap feature (its
// knobs render only while the feature is on).
import HyperparamPanel from "../HyperparamPanel";
import type { FitSettings } from "../HyperparamPanel";
import { PenaltyTable, Segmented, Toggle } from "../OptionsControls";
import type { OptionsSettings } from "../../state/useOptions";
import type { FitMode } from "../../state/useSmile";
import { numInput, rowLabel, sectionTitle, subTitle } from "./shared";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

export default function CalibrationSection({
  fitDraft,
  fitPatch,
  draft,
  patch,
  live,
  fitMode,
  setFitMode,
}: {
  fitDraft: FitSettings;
  fitPatch: (p: Partial<FitSettings>) => void;
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
  fitMode: FitMode;
  setFitMode: (m: FitMode) => void;
}) {
  return (
    <>
      <h3 className={sectionTitle}>Calibration</h3>

      <span className={`${rowLabel} mb-1 block`}>Fit target</span>
      <Segmented
        options={FIT_MODES}
        value={fitMode}
        onChange={(v) => { setFitMode(v); patch({ fitMode: v }); }}
        disabled={!live}
      />
      <p className="mt-1 text-[10px] text-slate-600">
        Mid · Bid-Ask band · Haircut band (shrink set by Haircut below).
        Persisted via Save as default.
      </p>

      {/* Haircut, quote weighting, band mid anchor (FitSettings). */}
      <div className="mt-4">
        <HyperparamPanel group="calibration" draft={fitDraft} patch={fitPatch} disabled={!live} />
      </div>

      <h4 className={subTitle}>Arbitrage enforcement</h4>
      <Toggle
        label="Arbitrage fix"
        hint="Calendar-couple the Calibrate job: fit each ticker's expiries in order, enforcing the convex-order (no-calendar-arbitrage) floor"
        checked={draft.enforceCalendar} disabled={!live}
        onChange={(v) => patch({ enforceCalendar: v })}
      />
      <div className="mt-1 flex items-center justify-between">
        <span
          className={rowLabel}
          title="Symmetric (default): fit every expiry independently, screen adjacent pairs for an identified violation on their common quote support, then jointly repair only the violating runs - no front-to-back bias, corrections shared by quote precision. Sequential: the historical nearest-to-farthest pass where each slice inherits the previous one as a hard floor."
        >
          Surface solver
        </span>
        <select
          value={draft.surfaceSolver}
          disabled={!live || !draft.enforceCalendar}
          onChange={(e) => patch({ surfaceSolver: e.target.value as "symmetric" | "sequential" })}
          className={numInput}
        >
          <option value="symmetric">Symmetric (screen + joint repair)</option>
          <option value="sequential">Sequential (front-to-back floor)</option>
        </select>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span className={rowLabel} title="Quadratic calendar-slack penalty weight (surface fits)">
          Calendar weight
        </span>
        <input
          type="number" step={1e5} min={0} value={draft.calendarWeight} disabled={!live}
          onChange={(e) => patch({ calendarWeight: Number(e.target.value) })}
          className={numInput}
        />
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span
          className={rowLabel}
          title="Winged calendar floors: build BOTH overlay families' (SVI and MCS) calendar floor and ceiling grids this many sigma*sqrt(T) beyond the common quote support, so displayed smiles keep calendar order out into the wing where the stacked-IV crossings live. Empty = the historical per-family scopes (SVI confined to common support; MCS winged at 2 sigma)."
        >
          Winged floors (σ pad)
        </span>
        <input
          type="number" step={0.5} min={0} max={8}
          value={draft.calendarFloorPadZ ?? ""}
          placeholder="off"
          disabled={!live || !draft.enforceCalendar}
          onChange={(e) => {
            const v = Number(e.target.value);
            patch({ calendarFloorPadZ: e.target.value === "" || !(v > 0) ? null : Math.min(v, 8) });
          }}
          className={numInput}
        />
      </div>
      <Toggle
        label="Calendar on refit"
        hint="Single-node refits (quote edit, auto-calibrate tick, lone Calibrate) keep the surface pass's calendar coupling: the adjacent committed slices supply a confined floor (previous expiry) and ceiling (next expiry) instead of silently dropping cross-expiry context. A neighbour's changed fit marks this node stale for free."
        checked={draft.calendarOnRefit} disabled={!live || !draft.enforceCalendar}
        onChange={(v) => patch({ calendarOnRefit: v })}
      />
      <Toggle
        label="Extrapolation guard"
        hint="Tapered no-arb enforcement beyond the quoted strikes (SVI/MCS): butterfly + calendar hinges over the time-value envelope, weighted like a handful of extra quotes - leans, never outvotes the data. The Quality tab measures this region either way."
        checked={draft.extrapEnforce} disabled={!live}
        onChange={(v) => patch({ extrapEnforce: v })}
      />
      <Toggle
        label="Tail-order gate"
        hint="Promote the full-line certificate's TAIL-ORDER clause (the limiting tail order of adjacent slices) from advisory to a gate: the active-set exchange treats a tail-order failure like a ledger-gap failure (the λ± seam rows at common α are its repair path — unequal α is irreducible by construction), the Quality readiness issue list names it and the publish export blocks on it. Off = byte-identical (the Phase-0 advisory policy); affects the surface repair."
        checked={draft.ledgerTailOrderGate} disabled={!live}
        onChange={(v) => patch({ ledgerTailOrderGate: v })}
      />
      <Toggle
        label="Band relaxation diagnostic"
        hint="After the surface pass, for every adjacent pair the exchange could NOT certify, bisect the smallest symmetric quote-band widening (vol) under which the pair certifies and report it on the Quality node and in export notes — the book's 'smallest quote-band relaxation needed for feasibility'. Advisory: the accepted surface is untouched; only runs in band fit modes (Bid-Ask / Haircut) on uncertified pairs."
        checked={draft.bandRelaxationDiagnostic} disabled={!live}
        onChange={(v) => patch({ bandRelaxationDiagnostic: v })}
      />

      <h4 className={subTitle}>Variance swaps</h4>
      <Toggle
        label="Variance-swaps"
        hint="Add var-swap quotes (Smile/Term/Table) with a calibration penalty pulling the model var-swap to the quote"
        checked={draft.varSwapEnabled} disabled={!live}
        onChange={(v) => patch({ varSwapEnabled: v })}
      />
      {draft.varSwapEnabled && (
        <>
          <div className="mt-1 flex items-center justify-between">
            <span
              className={rowLabel}
              title="Var-swap penalty weight as a % of the summed option-quote weights of the same (asset, expiry) node — at 100% the var-swap weighs as much as all option quotes combined"
            >
              Var-swap weight (%)
            </span>
            <input
              type="number" step={1} min={0} value={draft.varSwapWeightPct} disabled={!live}
              onChange={(e) => patch({ varSwapWeightPct: Number(e.target.value) })}
              className={numInput}
            />
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span
              className={rowLabel}
              title="How the Local-Vol fit prices the model variance swap: static log-contract strike replication (k^-2 weighted, grid-sensitive in the wings), or the backward source PDE g(0,1) — a local quantity robust to a coarse/truncated strike grid"
            >
              Var-swap pricing
            </span>
            <select
              value={draft.varSwapMethod}
              disabled={!live}
              onChange={(e) => patch({ varSwapMethod: e.target.value as "static" | "source_pde" })}
              className={numInput}
            >
              <option value="static">Static (replication)</option>
              <option value="source_pde">Source PDE</option>
            </select>
          </div>
        </>
      )}

      <h4 className={subTitle}>Calibration penalties</h4>
      <PenaltyTable group="calibration" />
    </>
  );
}
