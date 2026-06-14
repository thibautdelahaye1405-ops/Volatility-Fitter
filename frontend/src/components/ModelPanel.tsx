// Slim model selector for the Parametric aside (ROADMAP Phase 10).
//
// The full hyperparameter panel (Legendre order, damping, cores, weighting,
// haircut) now lives in the Options workspace; the aside keeps only the live
// per-node control a trader flips often: the smile family. It loads the global
// FitSettings (so a model swap PUTs the *full* object and never resets the
// other fields), changes only `model`, and refits via onApplied.
import { useEffect, useState } from "react";
import { api } from "../state/api";
import type { FitModel, FitSettings } from "./HyperparamPanel";

const MODELS: { id: FitModel; label: string; title: string }[] = [
  { id: "lqd", label: "LQD", title: "Logistic-quantile density slices (arbitrage-free)" },
  { id: "svi", label: "SVI", title: "Raw SVI own calibration (Gatheral)" },
  { id: "sigmoid", label: "Sig", title: "Multi-Core SIV marking curve" },
];

interface ModelPanelProps {
  disabled: boolean;
  onApplied: () => void;
}

export default function ModelPanel({ disabled, onApplied }: ModelPanelProps) {
  const [settings, setSettings] = useState<FitSettings | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (disabled) return;
    const controller = new AbortController();
    api
      .get<FitSettings>("/settings/fit", { signal: controller.signal })
      .then(setSettings)
      .catch(() => {
        /* keep null; controls disable until the backend responds */
      });
    return () => controller.abort();
  }, [disabled]);

  const select = (model: FitModel) => {
    if (settings === null || busy || model === settings.model) return;
    setBusy(true);
    const next = { ...settings, model };
    api
      .put<FitSettings>("/settings/fit", { body: next })
      .then((s) => {
        setSettings(s);
        onApplied();
      })
      .catch(() => {
        /* leave the previous model selected */
      })
      .finally(() => setBusy(false));
  };

  const active = settings?.model ?? "lqd";
  const off = disabled || settings === null;

  return (
    <section className={off ? "opacity-40" : ""} title={off ? "requires live backend" : undefined}>
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Model</h3>
      <p className="mb-2 text-[11px] text-slate-500">
        Smile family · full defaults in the Options tab
      </p>
      <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {MODELS.map((m) => (
          <button
            key={m.id}
            title={m.title}
            disabled={off || busy}
            onClick={() => select(m.id)}
            className={[
              "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
              m.id === active ? "bg-accent-600/25 text-accent-400" : "text-slate-400 enabled:hover:text-slate-200",
            ].join(" ")}
          >
            {m.label}
          </button>
        ))}
      </div>
    </section>
  );
}
