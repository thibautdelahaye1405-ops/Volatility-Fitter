// Config pill (P5b U6 → GRAPH ERGONOMICS ARC): the TopBar's live view of the
// relation-config lifecycle, simplified to the "what you see is what runs"
// ruling. Label = the ACTIVE config's name·version (or "auto" when nothing was
// ever activated) plus the number of staged edits; while the draft differs
// from the active config Run solves the DRAFT (the shell derives
// useDraftConfig from the diff — there is no manual run-draft toggle any
// more). The popover shows both slots, the diff, **Apply** (activates,
// event-logged backend-side) and **Discard** (reverts).
import { useState } from "react";
import {
  configDirty,
  diffRows,
  policyDirty,
  type MessageConfigPair,
} from "../../state/useMessageConfig";

export interface ConfigChipBundle {
  /** The lifecycle pair, or null (older backend / not yet loaded). */
  config: MessageConfigPair | null;
  /** A PUT of the draft is pending / in flight (the draft hook). */
  saving?: boolean;
  onActivate: (notes: string) => void;
  onRevert: () => void;
  /** An activate/revert round-trip is in flight. */
  busy: boolean;
}

/** Number of staged row edits + 1 when the policy is staged. */
export function editCount(config: MessageConfigPair | null): number {
  if (config === null || config.draft === null) return 0;
  const d = diffRows(config.draft.rows, config.active?.rows ?? []);
  return d.added + d.removed + d.changed + (policyDirty(config) ? 1 : 0);
}

export default function ConfigChip({ bundle }: { bundle: ConfigChipBundle }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const { config, saving = false, onActivate, onRevert, busy } = bundle;

  const active = config?.active ?? null;
  const draft = config?.draft ?? null;
  const dirty = configDirty(config);
  const diff = draft !== null ? diffRows(draft.rows, active?.rows ?? []) : null;
  const edits = editCount(config);
  const label = active !== null ? `${active.name} v${active.version}` : "auto";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Relation config: the active version, the staged edits Run is solving with, Apply / Discard."
        data-testid="config-chip"
        className="flex items-center gap-1.5 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
      >
        config <span className="text-slate-200">{label}</span>
        {saving && <span className="text-slate-500" title="Staging the edit on the draft…">…</span>}
        {dirty && (
          <span className="rounded bg-amber-500/15 px-1 text-[9px] text-amber-300" title="Staged edits — Run solves the draft until you Apply or Discard">
            {active === null ? "new draft" : edits > 0 ? `${edits} edit${edits > 1 ? "s" : ""}` : "draft*"}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-72 rounded-md border border-slate-700 bg-surface-800 p-2.5 text-[11px] text-slate-300 shadow-xl shadow-black/40">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Relation config</p>
          <div className="space-y-0.5 font-mono text-[10px]">
            <p>
              <span className="text-slate-500">active</span>{" "}
              {active !== null ? (
                <>
                  {active.name} v{active.version} · {active.rows.length} rows
                  {active.policy ? " · policy" : ""}
                </>
              ) : (
                <span className="text-slate-500">none — the solve builds the auto relations</span>
              )}
            </p>
            <p>
              <span className="text-slate-500">draft</span>{" "}
              {draft !== null ? (
                <>
                  v{draft.version} · {draft.rows.length} rows
                  {diff !== null && (
                    <span className="text-slate-400">
                      {" "}· +{diff.added} −{diff.removed} ~{diff.changed}
                      {policyDirty(config) ? " · policy" : ""}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-slate-500">none staged</span>
              )}
            </p>
            <p className="text-slate-500">
              Run solves: <span className="text-slate-300">{dirty ? "the draft (staged edits)" : "the active config"}</span>
            </p>
          </div>

          {dirty && (
            <div className="mt-2 border-t border-slate-700 pt-2">
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="notes for the event log (optional)"
                className="mb-1.5 w-full rounded border border-slate-700 bg-surface-900 px-1.5 py-1 text-[10px] text-slate-200 outline-none focus:border-accent-500"
              />
              <div className="flex gap-1.5">
                <button
                  disabled={busy || saving}
                  onClick={() => {
                    onActivate(notes);
                    setNotes("");
                    setOpen(false);
                  }}
                  title="Promote the draft to ACTIVE (event-logged); the next Run solves it as production"
                  className="flex-1 rounded-md bg-accent-600 px-2 py-1 text-[11px] font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Apply
                </button>
                <button
                  disabled={busy || saving}
                  onClick={() => {
                    onRevert();
                    setOpen(false);
                  }}
                  title="Discard the staged edits — back to a clean copy of the active config"
                  className="flex-1 rounded-md border border-slate-700 bg-surface-900 px-2 py-1 text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Discard
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
