// Config chip (P5b U6): the TopBar's live view of the message-relation
// lifecycle. Label = the ACTIVE config's name·version (or "auto" when
// nothing was ever activated) with a draft-dirty marker; the popover shows
// both slots, the draft-vs-active diff, the run-config toggle (Active |
// Draft — a test drive, never an activation) and the Activate / Revert
// lifecycle actions (event-logged backend-side).
import { useState } from "react";
import SegmentedControl from "../SegmentedControl";
import { configDirty, diffRows, type MessageConfigPair } from "../../state/useMessageConfig";

export interface ConfigChipBundle {
  /** The lifecycle pair, or null (older backend / not yet loaded). */
  config: MessageConfigPair | null;
  /** Which slot the next Run solves with. */
  runDraft: boolean;
  setRunDraft: (v: boolean) => void;
  onActivate: (notes: string) => void;
  onRevert: () => void;
  /** An activate/revert round-trip is in flight. */
  busy: boolean;
}

export default function ConfigChip({ bundle }: { bundle: ConfigChipBundle }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const { config, runDraft, setRunDraft, onActivate, onRevert, busy } = bundle;

  const active = config?.active ?? null;
  const draft = config?.draft ?? null;
  const dirty = configDirty(config);
  const diff =
    draft !== null ? diffRows(draft.rows, active?.rows ?? []) : null;

  const label = active !== null ? `${active.name} v${active.version}` : "auto";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Message-relation config lifecycle (draft/active). Click for slots, diff, run-config and Activate/Revert."
        className="flex items-center gap-1.5 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
      >
        config <span className="text-slate-200">{label}</span>
        {dirty && (
          <span className="text-amber-400" title="The draft differs from the active config">
            draft*
          </span>
        )}
        {runDraft && (
          <span className="rounded bg-accent-600/25 px-1 text-[9px] text-accent-300" title="Run solves with the DRAFT rows (test drive)">
            run draft
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-80 rounded-lg border border-slate-700 bg-surface-900 p-2.5 shadow-2xl shadow-black/50">
          {config === null ? (
            <p className="text-[10px] text-slate-500">
              No lifecycle report — older backend or offline. Solves keep
              using whatever is persisted.
            </p>
          ) : (
            <>
              <p className="mb-1 font-mono text-[10px] text-slate-300">
                active:{" "}
                {active === null
                  ? "— (auto relations)"
                  : `${active.name} v${active.version} · ${active.author} · ` +
                    `${active.createdAt.slice(0, 10)} · ${active.rows.length} rows`}
              </p>
              {active !== null && active.notes !== "" && (
                <p className="mb-1 text-[10px] italic text-slate-500">“{active.notes}”</p>
              )}
              <p className="mb-2 font-mono text-[10px] text-slate-400">
                draft:{" "}
                {draft === null
                  ? "— (nothing staged)"
                  : dirty && diff !== null
                    ? `+${diff.added} −${diff.removed} ~${diff.changed} vs ` +
                      `${active === null ? "auto" : `v${active.version}`} · stages v${draft.version}`
                    : "matches active"}
              </p>

              {/* Which slot Run solves with — a test drive, not an activation. */}
              <label className="mb-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
                Run solves with
                <SegmentedControl
                  options={[
                    { id: "active" as const, label: "Active" },
                    { id: "draft" as const, label: "Draft" },
                  ]}
                  value={runDraft ? "draft" : "active"}
                  onChange={(v) => setRunDraft(v === "draft")}
                  size="xs"
                />
              </label>

              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="activation notes…"
                  className="min-w-0 flex-1 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-[10px] text-slate-100 outline-none placeholder:text-slate-600 focus:border-accent-500"
                />
                <button
                  disabled={busy || draft === null || !dirty}
                  onClick={() => {
                    onActivate(notes);
                    setNotes("");
                  }}
                  title="Promote the draft to ACTIVE (event-logged) — the production solve flips to it"
                  className="rounded-md bg-accent-600 px-2 py-1 text-[10px] font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Activate
                </button>
                <button
                  disabled={busy || !dirty}
                  onClick={onRevert}
                  title="Discard the draft — back to a clean copy of the active config"
                  className="rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[10px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Revert
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
