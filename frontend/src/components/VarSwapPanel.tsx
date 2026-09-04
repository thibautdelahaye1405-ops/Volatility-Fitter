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
//
// V3.6 readouts: "model · quote · basis" line, penalty-weight readout (set in
// Options ▸ Calibration), stale badge, and DATA-DERIVED slider bounds — the
// quote∪model envelope padded by max(2 vol pts, 2·|basis|) (lib/varswap.ts),
// replacing the old ×0.5 / ×1.5 heuristic. 0.05 step / 2-dp display everywhere.
//
// Tail-persistence arc: a "Hard pin" toggle (OptionsSettings.varSwapHardPin).
// SELF-CONTAINED options round-trip: the parents deliberately do not thread the
// Options draft into this panel, so it GETs /settings/options itself and PUTs
// the full object back with the one bit flipped (fetch-then-flip, so no other
// field is clobbered; last-writer-wins vs a concurrently open Options draft —
// the app's standard PUT semantics). The options-version bump marks nodes
// stale; the fit picks the pin up on the next refetch / Calibrate.
//
// Sizes (lib/asideSizes, the column's shared focus): compact = one row with
// the quote (or the model level); standard = the model · quote · basis readout,
// the level editor and the undo / redo / reset row; expanded = everything
// (penalty weight, replication split, hard pin). Outside the column the card
// is expanded.
import { useEffect, useState } from "react";
import { AsideBody, AsideHeader } from "./AsideCard";
import type { AsideSize } from "../lib/asideSizes";
import type { VarSwapInfo } from "../lib/mockData";
import { formatPct } from "../lib/chartScale";
import {
  formatBasisBp,
  formatReplicationSplit,
  varswapBasisBp,
  varswapSliderBounds,
} from "../lib/varswap";
import { api } from "../state/api";

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
  /** Card size in the column (default: expanded, the full card). */
  size?: AsideSize;
  /** Expand / fold the card (the column's shared focus). */
  onToggleSize?: () => void;
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
  size = "L",
  onToggleSize,
}: VarSwapPanelProps) {
  const full = size === "L";
  // Local draft of the level in PERCENT, so the slider/input stay responsive
  // while a refit is in flight; resynced whenever the backend value changes.
  const level = info?.level ?? null;
  const model = info?.modelVol ?? 0;
  const [draftPct, setDraftPct] = useState<string>(pctStr(level ?? model));
  useEffect(() => {
    setDraftPct(pctStr(level ?? model));
  }, [level, model]);

  // Hard-pin state (null = not loaded / mock mode → the row is hidden).
  const [pin, setPin] = useState<boolean | null>(null);
  const [pinBusy, setPinBusy] = useState(false);
  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    api
      .get<{ varSwapHardPin: boolean }>("/settings/options")
      .then((s) => !cancelled && setPin(s.varSwapHardPin))
      .catch(() => {
        /* keep the row hidden — the toggle needs a live backend anyway */
      });
    return () => {
      cancelled = true;
    };
  }, [live]);
  const togglePin = () => {
    if (pinBusy || pin === null) return;
    setPinBusy(true);
    api
      .get<Record<string, unknown>>("/settings/options") // fetch-then-flip
      .then((s) =>
        api.put<{ varSwapHardPin: boolean }>("/settings/options", {
          body: { ...s, varSwapHardPin: !pin },
        }),
      )
      .then((s) => setPin(s.varSwapHardPin))
      .catch(() => {
        /* leave the previous state; the user can retry */
      })
      .finally(() => setPinBusy(false));
  };

  if (!info || !info.enabled) return null;

  const has = level !== null;
  const excluded = info.excluded;
  // Data-derived slider range: quote∪model envelope, basis-proportional pad.
  const bounds = varswapSliderBounds(level, model);
  // Basis in vol bp: prefer the wire value, derive it for older payloads/mock.
  const basisBp = info.basisBp ?? varswapBasisBp(level, model);
  // Strip-vs-tails split of the replication (null ⇒ the line is omitted).
  const split = formatReplicationSplit(info);
  const span =
    info.stripKLo != null && info.stripKHi != null
      ? `[${info.stripKLo.toFixed(2)}, ${info.stripKHi.toFixed(2)}]`
      : "[k_lo, k_hi]";

  /** Commit a percent value (clamped > 0) as a decimal var-swap vol. */
  const commit = (pct: number) => {
    if (Number.isFinite(pct) && pct > 0) onSet(pct / 100);
  };

  const readout = has
    ? `model ${formatPct(model, 2)} · quote ${formatPct(level, 2)} · basis ${formatBasisBp(basisBp)}`
    : `model ${formatPct(model, 2)}`;
  // Compact row: the quote and its basis (or the model level when unquoted).
  const summary = has
    ? `quote ${formatPct(level, 2)} · ${formatBasisBp(basisBp)}${excluded ? " · excluded" : ""}`
    : `model ${formatPct(model, 2)}`;
  const staleBadge = info.stale === true && (
    <span
      className="font-sans text-[10px] font-semibold uppercase text-amber-400"
      title="Inputs drifted since the last calibration — press Calibrate"
    >
      stale
    </span>
  );

  return (
    // Borderless: every caller (the Parametric / Local Vol asides) wraps the
    // panel in its own stacked card since UI SHELL v2 wave 2.
    <div className="flex min-h-0 flex-col">
      <AsideHeader
        title="Variance swap"
        size={size}
        onToggle={onToggleSize}
        badge={staleBadge}
        right={<span className="truncate font-mono text-[10px] text-slate-500">{readout}</span>}
        summary={summary}
        expandTip="penalty weight, replication split, hard pin"
      />
      {size !== "S" && (
        <AsideBody>
          {full && (
            <p className="mb-2 text-[11px] text-slate-500">
              {subtitle ?? "A penalty pulls the fitted var-swap toward the quote."}
            </p>
          )}
          {full && info.weightPct != null && (
            <p
              className="mb-2 font-mono text-[10px] text-slate-500"
              title="Penalty strength: varSwapWeightPct % of the node's summed option-quote weights — set in Options ▸ Calibration"
            >
              penalty {info.weightPct.toFixed(0)}% of quote weight
              {info.weightAbs != null && ` ≈ ${info.weightAbs.toPrecision(3)} abs`}
              {info.rmsShare != null && ` · ${(info.rmsShare * 100).toFixed(0)}% of node RMS²`}
              <span className="font-sans text-slate-600"> · Options ▸ Calibration</span>
            </p>
          )}
          {full && split && (
            <p
              className="mb-2 font-mono text-[10px] text-slate-500"
              title={
                "share of the model's replicated variance from the quoted strike span " +
                `${span} vs the extrapolated wings (log-contract replication truncated at ±6)`
              }
            >
              replication {split}
            </p>
          )}
          {full && pin !== null && (
            <label
              className="mb-2 flex cursor-pointer items-center justify-between"
              title={
                "Stiff-row equality (varSwapHardPin): the MARKET var-swap row's weight " +
                "is escalated to 10⁴× the node's summed quote weights — the calendar-row " +
                "idiom — so the fitted var-swap matches the quote to solver tolerance " +
                "(not a true constraint). Prior var-swap rows stay soft. Applies on the " +
                "next refit — the stale badge shows until then."
              }
            >
              <span className="text-[11px] text-slate-500">
                Hard pin
                {pin && (
                  <span className="ml-1.5 rounded bg-amber-500/15 px-1 py-0.5 font-mono text-[10px] text-amber-300">
                    pinned
                  </span>
                )}
              </span>
              <input
                type="checkbox"
                checked={pin}
                disabled={!live || pinBusy}
                onChange={togglePin}
                className="cursor-pointer accent-amber-400 disabled:cursor-not-allowed"
              />
            </label>
          )}

          {!has ? (
            <button
              className={`${btn} w-full`}
              disabled={!live}
              title={live ? "Add a var-swap quote at the model level" : "requires live backend"}
              onClick={() => commit(model * 100)}
            >
              + Add var-swap @ {formatPct(model, 2)}
            </button>
          ) : (
            <>
              <div className="mb-2 flex items-center gap-2">
                <input
                  type="number"
                  step={0.05}
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
                min={bounds.min}
                max={bounds.max}
                step={bounds.step}
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
        </AsideBody>
      )}
    </div>
  );
}
