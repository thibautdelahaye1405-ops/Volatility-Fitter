// Controlled, group-aware FitSettings controls for the Options tab.
//
// Edits the backend's global fit settings (GET/PUT /settings/fit): vol-surface
// model, LQD Legendre order N, the high-order damping lambda * n^{2r}, the
// Multi-Core SIV hat count R, the haircut band-shrink, the quote-weighting
// scheme and the per-model penalty coefficients. The draft + Apply live in
// useFitSettings (lifted), so these controls render across two themed Options
// cards sharing one draft: group="model" (model + hyperparameters + model
// penalties) and group="calibration" (haircut, weighting, band mid anchor).
import type { ReactNode } from "react";
import PenaltyCoefficients from "./PenaltyCoefficients";

/** The smile families calibratable through PUT /settings/fit. */
export type FitModel = "lqd" | "svi" | "sigmoid";

/** Per-quote weighting scheme (a third may be added later). */
export type WeightScheme = "equal" | "tv_density";

/** Mirror of the backend FitSettings schema (volfit/api/schemas.py). */
export interface FitSettings {
  model: FitModel;
  nOrder: number;
  regLambda: number;
  regPower: number;
  nCores: number;
  haircut: number;
  weightScheme: WeightScheme;
  // per-model optimization / penalty coefficients (Options exposes them all)
  barrierCenter: number;
  barrierScale: number;
  sviPenaltyWeight: number;
  leeSlopeMax: number;
  sigmoidRidge: number;
  midAnchorWeight: number;
}

export const FIT_DEFAULTS: FitSettings = {
  model: "lqd",
  nOrder: 6,
  regLambda: 1e-6,
  regPower: 1.0,
  nCores: 2,
  haircut: 0.005,
  weightScheme: "equal",
  barrierCenter: 0.9,
  barrierScale: 50.0,
  sviPenaltyWeight: 1e3,
  leeSlopeMax: 2.0,
  sigmoidRidge: 1e-2,
  midAnchorWeight: 0.05,
};

/** Model choices. LQD is the arbitrage-free default and the analytic backbone
 *  (density/term/graph/local-vol stay LQD-based); SVI and sigmoid fit the
 *  displayed smile as overlays. */
const MODELS: { id: string; label: string; title: string; enabled: boolean }[] = [
  { id: "lqd", label: "LQD", title: "Logistic-quantile density slices (arbitrage-free)", enabled: true },
  { id: "svi", label: "SVI", title: "Raw SVI own calibration (Gatheral)", enabled: true },
  { id: "sigmoid", label: "Sig", title: "Four-parameter sigmoid marking curve", enabled: true },
  { id: "lv", label: "LV", title: "Local-vol grid — view via the LV-grid scenario; direct fit TODO", enabled: false },
];

/** Damping presets: log-spaced lambda values, Off = exact interpolation. */
const LAMBDAS = [0, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3];
const POWERS = [0.5, 1.0, 1.5, 2.0];
/** Haircut presets in absolute vol; labelled in vol points (0.5 = 0.005). */
const HAIRCUTS = [0, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02];

/** Per-quote weighting schemes (room for a third later). */
const WEIGHT_SCHEMES: { id: WeightScheme; label: string; title: string }[] = [
  { id: "equal", label: "Equal", title: "Unit weights — every quote's IV residual counts the same" },
  {
    id: "tv_density",
    label: "TV density",
    title: "Time-value density weights: economic time-value shape with strike oversampling divided out",
  },
];

function lambdaLabel(value: number): string {
  return value === 0 ? "Off" : `1e${Math.round(Math.log10(value))}`;
}

interface HyperparamPanelProps {
  /** Which themed group of controls to render. */
  group: "model" | "calibration";
  draft: FitSettings;
  patch: (p: Partial<FitSettings>) => void;
  /** Greyed out in mock mode (settings live on the backend). */
  disabled: boolean;
}

const rowLabel = "text-xs text-slate-400";
const selectClass =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono " +
  "text-[11px] text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500 disabled:cursor-not-allowed";

export default function HyperparamPanel({ group, draft, patch, disabled }: HyperparamPanelProps) {
  // The Legendre order and high-order damping are LQD-only knobs; the SVI and
  // sigmoid overlays ignore them, so the controls are disabled off-LQD.
  const lqdOnly = disabled || draft.model !== "lqd";
  // The Multi-Core SIV hat count only drives the "sigmoid" family.
  const sigmoidOnly = disabled || draft.model !== "sigmoid";

  const wrap = (children: ReactNode) => (
    <section
      className={disabled ? "opacity-40" : ""}
      title={disabled ? "requires live backend" : undefined}
    >
      {children}
    </section>
  );

  if (group === "calibration") {
    return wrap(
      <>
        {/* Haircut: band shrink (in vol points) used by the haircut fit mode. */}
        <div className="mb-3 flex items-center justify-between">
          <span
            className={rowLabel}
            title="Haircut fit mode: shrink each band side toward mid by this many vol points"
          >
            Haircut (vol pts)
          </span>
          <select
            value={draft.haircut}
            disabled={disabled}
            onChange={(e) => patch({ haircut: Number(e.target.value) })}
            className={selectClass}
          >
            {HAIRCUTS.map((v) => (
              <option key={v} value={v}>
                {(v * 100).toFixed(2).replace(/0$/, "")}
              </option>
            ))}
          </select>
        </div>

        {/* Quote weighting scheme (applies to every model and fit mode). */}
        <div className="mb-3">
          <span className={`${rowLabel} mb-1 block`}>Quote weighting</span>
          <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
            {WEIGHT_SCHEMES.map((s) => (
              <button
                key={s.id}
                title={s.title}
                disabled={disabled}
                onClick={() => patch({ weightScheme: s.id })}
                className={[
                  "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
                  s.id === draft.weightScheme
                    ? "bg-accent-600/25 text-accent-400"
                    : "text-slate-400 enabled:hover:text-slate-200",
                ].join(" ")}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Band mid anchor (all models, band fit modes). */}
        <PenaltyCoefficients group="calibration" draft={draft} onChange={patch} disabled={disabled} />
      </>,
    );
  }

  // group === "model"
  return wrap(
    <>
      {/* Model segmented control */}
      <div className="mb-3 flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {MODELS.map((m) => (
          <button
            key={m.id}
            title={m.title}
            disabled={disabled || !m.enabled}
            onClick={() => patch({ model: m.id as FitModel })}
            className={[
              "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
              m.id === draft.model
                ? "bg-accent-600/25 text-accent-400"
                : m.enabled
                  ? "text-slate-400 enabled:hover:text-slate-200"
                  : "text-slate-600",
            ].join(" ")}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* LQD-only knobs: greyed out when an SVI/sigmoid overlay is selected. */}
      <div className={lqdOnly && !disabled ? "opacity-40" : ""}>
        {/* Legendre order N */}
        <div className="mb-1 flex items-center justify-between">
          <span className={rowLabel}>Legendre order N</span>
          <span className="font-mono text-xs font-medium text-slate-100">{draft.nOrder}</span>
        </div>
        <input
          type="range"
          min={4}
          max={12}
          step={1}
          value={draft.nOrder}
          disabled={lqdOnly}
          onChange={(e) => patch({ nOrder: Number(e.target.value) })}
          className="mb-3 w-full cursor-pointer disabled:cursor-not-allowed"
          style={{ accentColor: "var(--color-accent-500)" }}
        />

        {/* Damping lambda + power r */}
        <div className="mb-3 flex items-center justify-between">
          <span className={rowLabel} title="High-order damping lambda * n^(2r) * a_n^2">
            Damping λ · power r
          </span>
          <span className="flex gap-1.5">
            <select
              value={draft.regLambda}
              disabled={lqdOnly}
              onChange={(e) => patch({ regLambda: Number(e.target.value) })}
              className={selectClass}
            >
              {LAMBDAS.map((v) => (
                <option key={v} value={v}>
                  {lambdaLabel(v)}
                </option>
              ))}
            </select>
            <select
              value={draft.regPower}
              disabled={lqdOnly}
              onChange={(e) => patch({ regPower: Number(e.target.value) })}
              className={selectClass}
            >
              {POWERS.map((v) => (
                <option key={v} value={v}>
                  {v.toFixed(1)}
                </option>
              ))}
            </select>
          </span>
        </div>
      </div>

      {/* Multi-Core SIV hat count R: active only for the sigmoid family. */}
      <div className={sigmoidOnly && !disabled ? "opacity-40" : ""}>
        <div className="mb-1 flex items-center justify-between">
          <span className={rowLabel} title="Zero-wing hat kernels added to the SIV base (eq param-count)">
            SIV cores R
          </span>
          <span className="font-mono text-xs font-medium text-slate-100">{draft.nCores}</span>
        </div>
        <input
          type="range"
          min={0}
          max={6}
          step={1}
          value={draft.nCores}
          disabled={sigmoidOnly}
          onChange={(e) => patch({ nCores: Number(e.target.value) })}
          className="mb-3 w-full cursor-pointer disabled:cursor-not-allowed"
          style={{ accentColor: "var(--color-accent-500)" }}
        />
      </div>

      {/* Per-model optimization / penalty coefficients. */}
      <PenaltyCoefficients group="model" draft={draft} onChange={patch} disabled={disabled} />
    </>,
  );
}
