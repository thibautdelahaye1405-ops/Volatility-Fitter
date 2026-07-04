// Observation Kalman filter controls + diagnostics (Note 15 Phase 4).
//
// The single mode selector picks how the filtered handle state (ATM, skew,
// curvature) is used: off / drawn as an overlay only / entering the fit as a
// one-stage MAP prior. The knobs shown are the process-noise and safety
// parameters of the filter. The diagnostics table below makes the filter
// auditable per expiry — gains, innovation, covariance route, resets.
//
// Lives outside OptionsViewer (file-size policy); driven by the same Options draft.
import { useEffect, useState } from "react";

import { NumberRow, Toggle } from "./OptionsControls";
import { api } from "../state/api";
import type { OptionsSettings } from "../state/useOptions";
import type { FilterDiagnostics } from "../state/useObservationFilter";
import type { FitMode } from "../state/useSmile";

type FilterMode = OptionsSettings["observationFilterMode"];

const MODES: { id: FilterMode; label: string; hint: string }[] = [
  { id: "off", label: "Off", hint: "No filtering — every calibration is a fresh market snapshot." },
  { id: "overlay", label: "Overlay only", hint: "Draw the filtered handles + band on the smile; the calibration is untouched." },
  { id: "active", label: "active (one-stage MAP — pending validation)", hint: "The filtered state enters the calibration as a MAP prior — pending validation." },
];

const rowLabel = "text-xs text-slate-400";
const numInput =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

export default function ObservationFilterPanel({
  draft, patch, live, ticker, fitMode, refreshKey,
}: {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
  ticker: string;
  fitMode: FitMode;
  refreshKey: unknown; // bump to refetch diagnostics (e.g. after Apply)
}) {
  const mode = draft.observationFilterMode;
  const disabled = !live;

  return (
    <div className="mt-4 border-t border-slate-800 pt-3">
      <div className="mb-2 flex items-center justify-between">
        <span className={rowLabel} title="Time-series Kalman filter on the fitted smile handles (Note 15)">
          Observation filter
        </span>
        <select
          value={mode}
          disabled={disabled}
          onChange={(e) => patch({ observationFilterMode: e.target.value as FilterMode })}
          className={`${numInput} w-40`}
        >
          {MODES.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      </div>
      <p className="mb-2 text-[10px] text-slate-500">
        {MODES.find((m) => m.id === mode)?.hint} Handles are (ATM, skew, curvature)
        per node; the state predicts across fetches and resets after long gaps.
      </p>

      {mode !== "off" && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span
              className={rowLabel}
              title="Measurement covariance R: Jacobian-propagated from the fit (default) or the cheap precision-factor fallback (A/B diagnostic)"
            >
              Covariance route
            </span>
            <select
              value={draft.filterCovarianceMode}
              disabled={disabled}
              onChange={(e) => patch({ filterCovarianceMode: e.target.value as "jacobian" | "factors" })}
              className={`${numInput} w-32`}
            >
              <option value="jacobian">Jacobian</option>
              <option value="factors">Factors</option>
            </select>
          </div>
          <NumberRow label="ATM noise (bp/√day)" value={draft.filterProcessVolBpSqrtDay} step={1}
            disabled={disabled} onChange={(v) => patch({ filterProcessVolBpSqrtDay: v })} />
          <NumberRow label="Skew noise (/√day)" value={draft.filterProcessSkewSqrtDay} step={0.005}
            disabled={disabled} onChange={(v) => patch({ filterProcessSkewSqrtDay: v })} />
          <NumberRow label="Curvature noise (/√day)" value={draft.filterProcessCurvSqrtDay} step={0.01}
            disabled={disabled} onChange={(v) => patch({ filterProcessCurvSqrtDay: v })} />
          <NumberRow label="Transport noise ×" value={draft.filterTransportNoiseScale} step={0.05}
            disabled={disabled} onChange={(v) => patch({ filterTransportNoiseScale: v })} />
          <NumberRow label="Max gain (1 = free)" value={draft.filterMaxGain} step={0.05}
            disabled={disabled} onChange={(v) => patch({ filterMaxGain: v })} />
          <NumberRow label="Reset after (hours)" value={draft.filterResetHours} step={12}
            disabled={disabled} onChange={(v) => patch({ filterResetHours: v })} />
          <Toggle label="Residual inflation"
            hint="Inflate R by the realized fit inconsistency χ²/(m−d) (clipped), so an internally inconsistent fit is trusted less."
            checked={draft.filterResidualInflation} disabled={disabled}
            onChange={(v) => patch({ filterResidualInflation: v })} />
          <Toggle label="Data-only prepass"
            hint="Fit data-only first so the measurement fed to the filter is a clean market observation, not one already pulled by a prior. Slower (~2x per node)."
            checked={draft.filterDataOnlyPrepass} disabled={disabled}
            onChange={(v) => patch({ filterDataOnlyPrepass: v })} />
        </div>
      )}

      {mode === "off" && (
        <p className="text-[10px] text-slate-600">
          Filter disabled — no handle state is carried between fetches.
        </p>
      )}

      {mode !== "off" && (
        <FilterDiagnosticsTable ticker={ticker} live={live} fitMode={fitMode} refreshKey={refreshKey} />
      )}
    </div>
  );
}

/** Format a per-handle number, or a dash when the array is short. */
const fmt = (x: number | undefined, digits: number, scale = 1) =>
  x === undefined ? "—" : (x * scale).toFixed(digits);

/** The per-expiry audit table: gains, ATM innovation, route, resets. */
function FilterDiagnosticsTable({
  ticker, live, fitMode, refreshKey,
}: { ticker: string; live: boolean; fitMode: FitMode; refreshKey: unknown }) {
  const [rows, setRows] = useState<{ expiry: string; diag: FilterDiagnostics | null }[]>([]);
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
              .get<FilterDiagnostics>(`/smiles/${ticker}/${e}/filter?fit_mode=${fitMode}`)
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        setRows(exps.map((e, i) => ({ expiry: e, diag: diags[i] ?? null })));
      })
      .catch(() => !cancelled && setRows([]));
    return () => { cancelled = true; };
  }, [live, ticker, fitMode, refreshKey]);

  return (
    <div className="mt-3 rounded-md border border-slate-800 bg-surface-800/40 p-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Filter diagnostics{ticker ? ` · ${ticker}` : ""}
      </div>
      {rows.length === 0 ? (
        <p className="text-[10px] text-slate-600">
          No expiries loaded (fetch quotes first).
        </p>
      ) : (
        <table className="w-full text-[10px] text-slate-300">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-medium">Expiry</th>
              <th className="text-right font-medium" title="Kalman gain on the ATM handle (1 = trust the fit fully)">K(ATM)</th>
              <th className="text-right font-medium" title="Kalman gain on the skew handle">K(skew)</th>
              <th className="text-right font-medium" title="Kalman gain on the curvature handle">K(curv)</th>
              <th className="text-right font-medium" title="ATM innovation (measurement − prediction), vol bp">innov bp</th>
              <th className="text-right font-medium" title="Measurement-noise correlation ρ">ρ</th>
              <th className="text-left font-medium" title="Measurement covariance route actually used">route</th>
              <th className="text-left font-medium" title="Reset reason / state provenance">reset</th>
              <th className="text-left font-medium" title="Measurement flagged contaminated">⚠</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {rows.map((r) => {
              const d = r.diag;
              if (d === null || !d.active) {
                return (
                  <tr key={r.expiry}>
                    <td className="text-slate-500">{r.expiry}</td>
                    <td colSpan={8} className="text-slate-600">—</td>
                  </tr>
                );
              }
              // Open Record — either key may be absent from the breakdown.
              const rho: number | undefined = d.measurementBreakdown["rho"];
              const route: number | undefined = d.measurementBreakdown["route"];
              return (
                <tr key={r.expiry}>
                  <td className="text-slate-500">{r.expiry}</td>
                  <td className="text-right">{fmt(d.gain[0], 2)}</td>
                  <td className="text-right">{fmt(d.gain[1], 2)}</td>
                  <td className="text-right">{fmt(d.gain[2], 2)}</td>
                  <td className="text-right">{fmt(d.innovation[0], 1, 1e4)}</td>
                  <td className="text-right">{fmt(rho, 2)}</td>
                  <td>{route === undefined ? "—" : route >= 0.5 ? "jacobian" : "factors"}</td>
                  <td className="text-slate-500">{d.resetReason ?? d.provenance ?? ""}</td>
                  <td className={d.contaminated ? "text-amber-400" : "text-slate-600"}>
                    {d.contaminated ? "cont." : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
