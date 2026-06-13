// "Hyperparameters" panel for the Smile Viewer diagnostics aside.
//
// Edits the backend's global fit settings (GET/PUT /settings/fit): vol-surface
// model, LQD Legendre order N and the high-order damping lambda * n^{2r}.
// Settings are app-global on the server — a changed PUT bumps the fit-cache
// version so every view refits — and the panel triggers a refetch of the
// current smile via the session's reload() once the PUT lands.
import { useEffect, useState } from "react";
import { api } from "../state/api";

/** The smile families calibratable through PUT /settings/fit. */
export type FitModel = "lqd" | "svi" | "sigmoid";

/** Mirror of the backend FitSettings schema (volfit/api/schemas.py). */
export interface FitSettings {
  model: FitModel;
  nOrder: number;
  regLambda: number;
  regPower: number;
}

const DEFAULTS: FitSettings = {
  model: "lqd",
  nOrder: 6,
  regLambda: 1e-6,
  regPower: 1.0,
};

/** Model choices. LQD is the arbitrage-free default and the analytic backbone
 *  (density/term/graph/local-vol stay LQD-based); SVI and sigmoid fit the
 *  displayed smile as overlays. The local-vol grid is viewed via the LV-grid
 *  scenario; a direct slice fit through the API is still TODO. */
const MODELS: { id: string; label: string; title: string; enabled: boolean }[] = [
  { id: "lqd", label: "LQD", title: "Logistic-quantile density slices (arbitrage-free)", enabled: true },
  { id: "svi", label: "SVI", title: "Raw SVI own calibration (Gatheral)", enabled: true },
  { id: "sigmoid", label: "Sig", title: "Four-parameter sigmoid marking curve", enabled: true },
  { id: "lv", label: "LV", title: "Local-vol grid — view via the LV-grid scenario; direct fit TODO", enabled: false },
];

/** Damping presets: log-spaced lambda values, Off = exact interpolation. */
const LAMBDAS = [0, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3];
const POWERS = [0.5, 1.0, 1.5, 2.0];

function lambdaLabel(value: number): string {
  return value === 0 ? "Off" : `1e${Math.round(Math.log10(value))}`;
}

interface HyperparamPanelProps {
  /** Greyed out in mock mode (settings live on the backend). */
  disabled: boolean;
  /** Refetch the current smile after settings were applied server-side. */
  onApplied: () => void;
}

export default function HyperparamPanel({ disabled, onApplied }: HyperparamPanelProps) {
  // `saved` mirrors the backend; `draft` is the panel state being edited.
  const [saved, setSaved] = useState<FitSettings>(DEFAULTS);
  const [draft, setDraft] = useState<FitSettings>(DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);

  // Load the server's current settings once the backend is reachable.
  useEffect(() => {
    if (disabled) return;
    const controller = new AbortController();
    api
      .get<FitSettings>("/settings/fit", { signal: controller.signal })
      .then((s) => {
        setSaved(s);
        setDraft(s);
      })
      .catch(() => {
        /* keep defaults; the Apply PUT will surface real failures */
      });
    return () => controller.abort();
  }, [disabled]);

  const dirty =
    draft.model !== saved.model ||
    draft.nOrder !== saved.nOrder ||
    draft.regLambda !== saved.regLambda ||
    draft.regPower !== saved.regPower;

  // The Legendre order and high-order damping are LQD-only knobs; the SVI and
  // sigmoid overlays ignore them, so the controls are disabled off-LQD.
  const lqdOnly = disabled || draft.model !== "lqd";

  const apply = () => {
    if (!dirty || busy) return;
    setBusy(true);
    api
      .put<FitSettings>("/settings/fit", { body: draft })
      .then((s) => {
        setSaved(s);
        setDraft(s);
        setFlash(true);
        setTimeout(() => setFlash(false), 1200);
        onApplied();
      })
      .catch(() => {
        /* leave the draft dirty so the user can retry */
      })
      .finally(() => setBusy(false));
  };

  const rowLabel = "text-xs text-slate-400";
  const selectClass =
    "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono " +
    "text-[11px] text-slate-200 outline-none hover:border-slate-600 " +
    "focus:border-accent-500 disabled:cursor-not-allowed";

  return (
    <section
      className={disabled ? "opacity-40" : ""}
      title={disabled ? "requires live backend" : undefined}
    >
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Hyperparameters</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        Global fit settings · every view refits
      </p>

      {/* Model segmented control (only LQD is calibratable today) */}
      <div className="mb-3 flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {MODELS.map((m) => (
          <button
            key={m.id}
            title={m.title}
            disabled={disabled || !m.enabled}
            onClick={() => setDraft({ ...draft, model: m.id as FitModel })}
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
          onChange={(e) => setDraft({ ...draft, nOrder: Number(e.target.value) })}
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
              onChange={(e) => setDraft({ ...draft, regLambda: Number(e.target.value) })}
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
              onChange={(e) => setDraft({ ...draft, regPower: Number(e.target.value) })}
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

      <button
        onClick={apply}
        disabled={disabled || !dirty || busy}
        className={[
          "w-full rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors",
          flash
            ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
            : dirty && !disabled
              ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
              : "cursor-not-allowed border-slate-700 text-slate-600",
        ].join(" ")}
      >
        {flash ? "Applied ✓" : busy ? "Refitting…" : "Apply & refit"}
      </button>
    </section>
  );
}
