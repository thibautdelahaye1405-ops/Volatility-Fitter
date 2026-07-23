// Dynamics policy card (P6 V3): the layered-mode dials that version WITH the
// relation config — clamp freshness window, residual half-life, per-class
// semantics defaults. Shown in the Relationships pane in Layered mode only.
//
// Save stages the policy on the DRAFT config (PUT /graph/config/messages/
// policy) — production keeps the active policy until Activate (config chip),
// exactly like relation rows. The solve resolves request dials it wasn't
// sent from the ACTIVE policy, so activating here changes the next Run.
import { useEffect, useState } from "react";
import {
  DEFAULT_POLICY,
  putMessagePolicy,
  type DynamicPolicy,
  type MessageConfigPair,
} from "../../state/useMessageConfig";
import {
  CLASS_DEFAULT_SEMANTICS,
  RELATION_CLASSES,
  type RelationClass,
  type RelationSemantics,
} from "../../state/useMessageEdges";
import { semanticsLabel } from "../MessageEdgeEditor.helpers";

const numCls =
  "w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right " +
  "font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500";
const selCls =
  "rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono " +
  "text-[10px] text-slate-100 outline-none focus:border-accent-500";

/** The staged-or-active policy the card edits from (null ⇒ schema defaults). */
function seedPolicy(config: MessageConfigPair | null): DynamicPolicy {
  const slot = config?.draft?.policy ?? config?.active?.policy ?? null;
  return {
    ...DEFAULT_POLICY,
    ...(slot ?? {}),
    semanticsDefaults: { ...(slot?.semanticsDefaults ?? {}) },
  };
}

export default function DynamicsPolicyCard({
  config,
  onSaved,
}: {
  config: MessageConfigPair | null;
  onSaved?: () => void;
}) {
  const [policy, setPolicy] = useState<DynamicPolicy>(() => seedPolicy(config));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Re-seed when the lifecycle pair lands/refreshes (fetch is async).
  const seedKey = JSON.stringify(config?.draft?.policy ?? config?.active?.policy ?? null);
  useEffect(() => {
    setPolicy(seedPolicy(config));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seedKey digest
  }, [seedKey]);

  const save = () => {
    setBusy(true);
    setError(null);
    putMessagePolicy(policy)
      .then(() => onSaved?.())
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <div data-testid="dynamics-policy">
      <label
        className="flex items-center justify-between gap-2 text-xs text-slate-400"
        title="Clamp freshness window (§4.2): a lit calibration older than this many days loses hard-boundary status and enters as a soft aged anchor"
      >
        <span>Clamp max age (d)</span>
        <input
          type="number"
          step={0.5}
          min={0.5}
          value={policy.clampMaxAgeDays}
          onChange={(e) => {
            const v = e.target.valueAsNumber;
            if (Number.isFinite(v) && v > 0)
              setPolicy((p) => ({ ...p, clampMaxAgeDays: v }));
          }}
          className={numCls}
        />
      </label>
      <label
        className="mt-1 flex items-center justify-between gap-2 text-xs text-slate-400"
        title="Residual half-life in days (D2): how fast a node's own dislocation memory decays. Empty = never (random walk) — it persists until the next calibration"
      >
        <span>Residual half-life (d)</span>
        <input
          type="number"
          step={1}
          min={0}
          placeholder="never"
          value={policy.residualHalfLifeDays ?? ""}
          onChange={(e) => {
            const v = e.target.valueAsNumber;
            setPolicy((p) => ({
              ...p,
              residualHalfLifeDays: Number.isFinite(v) && v > 0 ? v : null,
            }));
          }}
          className={numCls}
        />
      </label>

      {/* Per-class semantics defaults — rows set to "auto" resolve here. */}
      <details className="mt-1.5">
        <summary
          className="cursor-pointer text-[11px] text-slate-500 transition-colors hover:text-slate-300"
          title="Per-class semantics defaults: relation rows left on 'auto' resolve to these. Unset classes keep the §9.2 defaults (calendar/peer/custom reciprocal; index/ETF directed)"
        >
          Semantics defaults{" "}
          <span className="text-slate-600">
            · {Object.keys(policy.semanticsDefaults).length || "§9.2"}
          </span>
        </summary>
        <div className="mt-1 space-y-1">
          {RELATION_CLASSES.map((cls: RelationClass) => {
            const override = policy.semanticsDefaults[cls];
            return (
              <label
                key={cls}
                className="flex items-center justify-between gap-2 text-[11px] text-slate-400"
              >
                <span>{cls.replace("_", " ")}</span>
                <select
                  className={selCls}
                  value={override ?? "auto"}
                  title={`Default semantics for ${cls} rows on auto; §9.2 default = ${semanticsLabel(CLASS_DEFAULT_SEMANTICS[cls])}`}
                  onChange={(e) =>
                    setPolicy((p) => {
                      const next = { ...p.semanticsDefaults };
                      if (e.target.value === "auto") delete next[cls];
                      else next[cls] = e.target.value as RelationSemantics;
                      return { ...p, semanticsDefaults: next };
                    })
                  }
                >
                  <option value="auto">
                    §9.2 · {semanticsLabel(CLASS_DEFAULT_SEMANTICS[cls])}
                  </option>
                  <option value="reciprocal_harmonic">recip ⇄</option>
                  <option value="directed_state">direct →</option>
                </select>
              </label>
            );
          })}
        </div>
      </details>

      {error !== null && (
        <p className="mt-1 truncate text-[10px] text-amber-400/80" title={error}>
          {error}
        </p>
      )}
      <button
        disabled={busy}
        onClick={save}
        title="Stage these dials on the DRAFT config — production keeps the active policy until you Activate (config chip)"
        className="mt-1.5 w-full rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Staging…" : "Save draft policy"}
      </button>
    </div>
  );
}
