// Reusable variance-swap quote control, shared by the Parametric and Local Vol
// workspaces (Smile / Term / Table sub-tabs). A node has at most ONE var-swap
// quote (the var-swap level is a single scalar per smile), so this edits that
// one value: add it (seeded at the model's own fair var-swap), nudge it with a
// slider or exact entry, exclude it from the fit, remove it, with the usual
// undo / redo / reset. Gated by VarSwapInfo.enabled (OptionsSettings.varSwapEnabled).
//
// Stateless w.r.t. the backend: the parent wires the callbacks to the shared
// /smiles/{ticker}/{expiry}/varswap endpoints (volfit.api.varswap) and refits.
// The slider commits on release (not every drag tick) so a refit fires once.
import { useEffect, useState } from "react";
import type { VarSwapInfo } from "../lib/mockData";
import { formatPct } from "../lib/chartScale";

interface VarSwapPanelProps {
  info: VarSwapInfo | null | undefined;
  /** Live backend? Edits are disabled in mock mode. */
  live: boolean;
  onSet: (level: number) => void;
  onExclude: () => void;
  onInclude: () => void;
  onRemove: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onReset: () => void;
  /** Optional context label, e.g. the expiry being edited in the Term view. */
  subtitle?: string;
}

const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** Round a percent display value to a clean number of decimals. */
const pctStr = (decimal: number) => (decimal * 100).toFixed(2);

export default function VarSwapPanel({
  info,
  live,
  onSet,
  onExclude,
  onInclude,
  onRemove,
  onUndo,
  onRedo,
  onReset,
  subtitle,
}: VarSwapPanelProps) {
  // Local draft of the level in PERCENT, so the slider/input stay responsive
  // while a refit is in flight; resynced whenever the backend value changes.
  const level = info?.level ?? null;
  const model = info?.modelVol ?? 0;
  const [draftPct, setDraftPct] = useState<string>(pctStr(level ?? model));
  useEffect(() => {
    setDraftPct(pctStr(level ?? model));
  }, [level, model]);

  if (!info || !info.enabled) return null;

  const has = level !== null;
  const excluded = info.excluded;
  // Slider range straddles the model var-swap; widened so a far quote still fits.
  const center = (level ?? model) * 100;
  const sliderMin = Math.max(1, Math.min(center, model * 100) * 0.5);
  const sliderMax = Math.max(center, model * 100) * 1.5 + 1;

  /** Commit a percent value (clamped > 0) as a decimal var-swap vol. */
  const commit = (pct: number) => {
    if (Number.isFinite(pct) && pct > 0) onSet(pct / 100);
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-surface-950/40 p-3">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Variance swap</h3>
        <span className="font-mono text-[10px] text-slate-500">
          model {formatPct(model)}
        </span>
      </div>
      <p className="mb-2 text-[11px] text-slate-500">
        {subtitle ?? "A penalty pulls the fitted var-swap toward the quote."}
      </p>

      {!has ? (
        <button
          className={`${btn} w-full`}
          disabled={!live}
          title={live ? "Add a var-swap quote at the model level" : "requires live backend"}
          onClick={() => commit(model * 100)}
        >
          + Add var-swap @ {formatPct(model)}
        </button>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2">
            <input
              type="number"
              step={0.1}
              min={0}
              value={draftPct}
              disabled={!live}
              title="Var-swap vol (%)"
              onChange={(e) => setDraftPct(e.target.value)}
              onBlur={() => commit(Number(draftPct))}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit(Number(draftPct));
              }}
              className="w-20 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
            />
            <span className="font-mono text-[11px] text-slate-500">% vol</span>
            <span
              className={[
                "ml-auto rounded px-1.5 py-0.5 font-mono text-[10px]",
                excluded
                  ? "bg-slate-700/40 text-slate-400"
                  : "bg-teal-600/20 text-teal-300",
              ].join(" ")}
            >
              {excluded ? "excluded" : "active"}
            </span>
          </div>
          <input
            type="range"
            min={sliderMin}
            max={sliderMax}
            step={0.05}
            value={Number(draftPct)}
            disabled={!live}
            onChange={(e) => setDraftPct(e.target.value)}
            onPointerUp={() => commit(Number(draftPct))}
            onKeyUp={() => commit(Number(draftPct))}
            className="mb-2 w-full cursor-pointer"
            style={{ accentColor: "var(--color-teal-400, #2dd4bf)" }}
          />
          <div className="flex gap-1.5">
            <button
              className={`${btn} flex-1`}
              disabled={!live}
              onClick={excluded ? onInclude : onExclude}
              title={excluded ? "Include in the fit" : "Exclude from the fit"}
            >
              {excluded ? "Include" : "Exclude"}
            </button>
            <button
              className={`${btn} flex-1`}
              disabled={!live}
              onClick={onRemove}
              title="Remove the var-swap quote"
            >
              Remove
            </button>
          </div>
        </>
      )}

      <div className="mt-2 flex gap-1.5 border-t border-slate-800 pt-2">
        <button className={`${btn} flex-1`} disabled={!live || !info.canUndo} onClick={onUndo}>
          Undo
        </button>
        <button className={`${btn} flex-1`} disabled={!live || !info.canRedo} onClick={onRedo}>
          Redo
        </button>
        <button
          className={`${btn} flex-1`}
          disabled={!live || (!has && !excluded)}
          onClick={onReset}
          title="Clear the var-swap quote"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
