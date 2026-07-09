// Options ▸ Local-Vol surface: the master calibration switch, the vertex grid,
// wing/front regularizers and solver features. Feature-dependent knobs render
// ONLY while their feature toggle is on (convex-wing weight, front-tie weight,
// the left-wing slope used by the convex wing). Turning the master switch off
// collapses the whole section to just the switch.
import { api } from "../../state/api";
import { NumberRow, PenaltyTable, Toggle } from "../OptionsControls";
import type { OptionsSettings } from "../../state/useOptions";
import { numInput, rowLabel, sectionTitle, subTitle } from "./shared";

/** The resolved local-vol vertex grid for the active ticker (GET grid-info). */
export interface GridInfo {
  nTNodes: number;
  nXNodes: number;
  nVertices: number;
  convexWingNodes: number;
  strikeMode: string;
  nExpiries: number;
  capVol: number;
  floorVol: number;
}

export default function LocalVolSection({
  draft,
  patch,
  live,
  ticker,
  gridInfo,
  anyDirty,
}: {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
  ticker: string;
  gridInfo: GridInfo | null;
  anyDirty: boolean;
}) {
  return (
    <>
      <h3 className={sectionTitle}>Local-Vol surface</h3>
      <Toggle
        label="Local-Vol calibration"
        hint="On: Calibrate also fits each ticker's Local-Vol surface (slow); the Local Vol workspace is available. Off: skip LV for fast test cycles and grey out the workspace."
        checked={draft.localVolEnabled} disabled={!live}
        onChange={(v) => patch({ localVolEnabled: v })}
      />
      {!draft.localVolEnabled ? (
        <p className="mt-1 text-[10px] text-slate-500">
          Enable to configure the vertex grid, wing regularizers and solver.
        </p>
      ) : (
        <>
          <h4 className={subTitle}>Vertex grid</h4>
          <Toggle
            label="Delta strike axis"
            hint="Place strike vertices on the symmetric {1,2,5,10,25,40,50}Δ axis (dense near ATM, clipped to the traded range) — resolves the put wing. Off = legacy uniform-in-x spacing."
            checked={draft.gridStrikeMode === "delta"} disabled={!live}
            onChange={(v) => patch({ gridStrikeMode: v ? "delta" : "linear" })}
          />
          <div className="mt-2 space-y-2">
            <NumberRow
              label={draft.gridStrikeMode === "delta" ? "Strike nodes (floor)" : "Strike nodes"}
              value={draft.gridXNodes} step={1} disabled={!live}
              onChange={(v) => patch({ gridXNodes: v })} />
            <NumberRow label="Time nodes (floor; 0 = per expiry)" value={draft.gridTNodes} step={1} disabled={!live}
              onChange={(v) => patch({ gridTNodes: v })} />
            <NumberRow label="Roughness λ" value={draft.gridRegLambda} step={0.001} disabled={!live}
              onChange={(v) => patch({ gridRegLambda: v })} />
            <NumberRow label="Roughness ρ (t vs x)" value={draft.gridRegRho} step={0.1} disabled={!live}
              onChange={(v) => patch({ gridRegRho: v })} />
          </div>
          {gridInfo && (
            <p className="mt-2 rounded-md border border-slate-800 bg-surface-800/50 px-2 py-1 text-[10px] text-slate-400">
              {anyDirty ? <span className="text-amber-400">Apply to refresh — </span> : null}
              Resolved grid for {ticker}: <span className="font-mono text-slate-200">
                {gridInfo.nTNodes}×{gridInfo.nXNodes} = {gridInfo.nVertices}
              </span> vertices ({gridInfo.strikeMode}
              {gridInfo.convexWingNodes > 0 ? `, ${gridInfo.convexWingNodes} convex-wing` : ""})
              · {gridInfo.nExpiries} expiries · LV bounds{" "}
              <span className="font-mono text-slate-200">
                {(gridInfo.floorVol * 100).toFixed(0)}%–{(gridInfo.capVol * 100).toFixed(0)}%
              </span>
            </p>
          )}
          <button
            type="button"
            disabled={!live || ticker === ""}
            title={`Size the grid to ${ticker || "the ticker"}'s observed quotes`}
            onClick={() => {
              api
                .get<{ gridXNodes: number; gridTNodes: number }>(
                  `/fit/affine/${ticker}/optimal-size`,
                )
                .then((o) => patch({ gridXNodes: o.gridXNodes, gridTNodes: o.gridTNodes }))
                .catch(() => {});
            }}
            className="mt-2 w-full rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1 text-[11px] font-semibold text-accent-300 transition hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Optimal size (≈ # quotes)
          </button>
          <p className="mt-1 text-[10px] text-slate-500">
            Time vertices default to the observed expiries; the lowest strike vertex
            sits just above the lowest observed strike.
          </p>

          <h4 className={subTitle}>Wing &amp; front regularizers</h4>
          <Toggle
            label="Convex wing (< 5Δ)"
            hint="Soft-penalize concavity of local vol σ(x,t) in x below the 5Δ-put strike, so the sparse left wing doesn't fit too concave"
            checked={draft.convexWing} disabled={!live}
            onChange={(v) => patch({ convexWing: v })}
          />
          {draft.convexWing && (
            <div className="mt-1 space-y-2">
              <NumberRow label="Convex-wing weight" value={draft.convexWingWeight} step={100}
                disabled={!live}
                onChange={(v) => patch({ convexWingWeight: v })} />
              <div>
                <NumberRow label="Left-wing slope ×" value={draft.leftWingSlopeMult} step={0.1}
                  disabled={!live}
                  onChange={(v) => patch({ leftWingSlopeMult: v })} />
                <p className="mt-1 text-[10px] text-slate-500">
                  Below the lowest strike the local variance continues linearly toward
                  x=0 at this × the first-cell slope (with a var-swap quote the slope is
                  fitted to the quote, this is its start).
                </p>
              </div>
            </div>
          )}
          <Toggle
            label="Front tie (t=0 → first row)"
            hint="Pull the unconstrained t=0 local-vol row toward the first calibrated row (soft one-sided difference), so the free front stops leaking into the shortest, most-curved smile — improves short-dated fits"
            checked={draft.frontTie} disabled={!live}
            onChange={(v) => patch({ frontTie: v })}
          />
          {draft.frontTie && (
            <div className="mt-1">
              <NumberRow label="Front-tie weight" value={draft.frontTieWeight} step={0.005}
                disabled={!live}
                onChange={(v) => patch({ frontTieWeight: v })} />
            </div>
          )}
          <div className="mt-2">
            <NumberRow label="LV cap × (× max IV)" value={draft.lvVolCapMult} step={0.5}
              disabled={!live}
              onChange={(v) => patch({ lvVolCapMult: v })} />
            <p className="mt-1 text-[10px] text-slate-500">
              Local vol capped at max(60%, this × the highest observed IV) — scales the
              cap to high-vol names so deep-put local vol isn't clamped.
            </p>
          </div>

          <h4 className={subTitle}>Solver</h4>
          <div className="flex items-center justify-between">
            <span
              className={rowLabel}
              title="LV calibration solver. TRF = scipy trust-region (default). Gauss-Newton = matrix-free GN that avoids trf's dense SVD (~52% of an eval) — ~1.3-1.65x faster with the fast compiled march + early-stop. Trade-off: GN converges to a slightly different local optimum on stiff data, so the surface can differ by up to ~0.25 vol-bp (sometimes better). Needs the fast kernel + early-stop; var-swap fits always use TRF."
            >
              LV solver
            </span>
            <select
              value={draft.lvSolver}
              disabled={!live}
              onChange={(e) => patch({ lvSolver: e.target.value as "trf" | "gn" })}
              className={numInput}
            >
              <option value="gn">Gauss-Newton (default, faster)</option>
              <option value="trf">TRF (legacy)</option>
            </select>
          </div>
          <div className="mt-2">
            <Toggle
              label="Fast compiled march (Numba)"
              hint="Run the LV Dupire calibration march on the compiled Numba vectorized-Thomas kernel (~6x the scipy/LAPACK banded march) — the bulk of the per-eval cost. Output matches the banded march to ~1e-15; automatic fallback if Numba is missing. Off = always use the banded march."
              checked={draft.lvFastKernel} disabled={!live}
              onChange={(v) => patch({ lvFastKernel: v })}
            />
            <Toggle
              label="Early-stop cold fit (faster)"
              hint="Stop the cold LV calibration once the quote-fit improvement stalls, instead of always running to the 200-evaluation cap (~1.45-3.3x, +0.10-0.25 vol-bp). Warm recalibrations converge before the stall window, so they are unaffected. Off = full 200-eval fit."
              checked={draft.lvEarlyStop} disabled={!live}
              onChange={(v) => patch({ lvEarlyStop: v })}
            />
            <Toggle
              label="2nd-order time stepping (experimental)"
              hint="Rannacher (Crank-Nicolson after implicit-Euler start-up) reaches the same accuracy at ~3x larger time steps but benchmarked at only ~1.1x net and is not monotone (an arb violation appeared on a coarse-x grid) — OFF by default. Off = 1st-order implicit Euler. Var-swap fits always use implicit."
              checked={draft.timeScheme === "rannacher"} disabled={!live}
              onChange={(v) => patch({ timeScheme: v ? "rannacher" : "implicit" })}
            />
          </div>

          <h4 className={subTitle}>Penalties</h4>
          <PenaltyTable group="lv" />
        </>
      )}
    </>
  );
}
