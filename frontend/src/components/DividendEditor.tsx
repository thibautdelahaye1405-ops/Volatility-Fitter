// Discrete dividend-schedule editor, embedded in the Forward panel.
//
// Mirrors the backend dividend model (volfit.data.dividends): a mode picker
// (continuous yield / discrete cash / discrete proportional / mixed) plus, for
// the discrete modes, an editable schedule of (ex-date, amount) rows and — for
// "mixed" — the cash→proportional switch horizon. Controlled component: the
// parent ForwardPanel owns the draft and applies it via PUT
// /settings/market/{ticker}, so changing the schedule refits the smile.
import type { DividendItem, DividendMode } from "./ForwardPanel";

interface DividendEditorProps {
  disabled: boolean;
  mode: DividendMode;
  onModeChange: (m: DividendMode) => void;
  dividends: DividendItem[];
  onDividendsChange: (d: DividendItem[]) => void;
  /** Draft string for the mixed-mode switch horizon (years). */
  switchYears: string;
  onSwitchYearsChange: (v: string) => void;
}

const MODES: { id: DividendMode; label: string; title: string }[] = [
  { id: "continuous", label: "Cont", title: "Continuous dividend yield q" },
  { id: "discrete_absolute", label: "Cash", title: "Discrete cash (escrowed) dividends" },
  { id: "discrete_proportional", label: "Prop", title: "Discrete proportional dividends (fraction of spot)" },
  { id: "mixed", label: "Mixed", title: "Cash near-dated, proportional far-dated (switch horizon)" },
];

const inputClass =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono " +
  "text-[11px] text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500 disabled:cursor-not-allowed disabled:opacity-50";

export default function DividendEditor({
  disabled,
  mode,
  onModeChange,
  dividends,
  onDividendsChange,
  switchYears,
  onSwitchYearsChange,
}: DividendEditorProps) {
  const discrete = mode !== "continuous";
  const proportional = mode === "discrete_proportional";

  const updateRow = (i: number, patch: Partial<DividendItem>) =>
    onDividendsChange(dividends.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const removeRow = (i: number) =>
    onDividendsChange(dividends.filter((_, j) => j !== i));
  const addRow = () =>
    onDividendsChange([...dividends, { exDate: "", amount: proportional ? 0.01 : 0.5 }]);

  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-slate-400">Dividend model</span>
      </div>

      {/* Mode segmented control */}
      <div className="mb-2 flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {MODES.map((m) => (
          <button
            key={m.id}
            title={m.title}
            disabled={disabled}
            onClick={() => onModeChange(m.id)}
            className={[
              "flex-1 px-1.5 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
              m.id === mode
                ? "bg-accent-600/25 text-accent-400"
                : "text-slate-400 enabled:hover:text-slate-200",
            ].join(" ")}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Discrete schedule (cash / proportional / mixed) */}
      {discrete && (
        <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-slate-600">
            <span className="flex-1">ex-date</span>
            <span className="w-16 text-right">{proportional ? "fraction" : "amount"}</span>
            <span className="w-4" />
          </div>
          {dividends.length === 0 ? (
            <p className="py-1 text-[11px] text-slate-500">No dividends scheduled.</p>
          ) : (
            <div className="flex max-h-32 flex-col gap-1 overflow-y-auto">
              {dividends.map((d, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <input
                    type="date"
                    value={d.exDate}
                    disabled={disabled}
                    onChange={(e) => updateRow(i, { exDate: e.target.value })}
                    className={`${inputClass} min-w-0 flex-1`}
                  />
                  <input
                    type="number"
                    step={proportional ? 0.001 : 0.05}
                    min={0}
                    value={d.amount}
                    disabled={disabled}
                    onChange={(e) => {
                      const v = e.target.valueAsNumber;
                      updateRow(i, { amount: Number.isFinite(v) ? v : 0 });
                    }}
                    className={`${inputClass} w-16 text-right`}
                  />
                  <button
                    onClick={() => removeRow(i)}
                    disabled={disabled}
                    title="Remove dividend"
                    className="w-4 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200 disabled:opacity-40"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={addRow}
            disabled={disabled}
            className="mt-1.5 w-full rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:opacity-40"
          >
            + Add dividend
          </button>

          {/* Mixed-mode switch horizon: cash before, proportional after */}
          {mode === "mixed" && (
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-slate-400" title="Cash before this horizon, proportional after">
                Switch (yrs)
              </span>
              <input
                type="number"
                step={0.25}
                min={0.01}
                value={switchYears}
                disabled={disabled}
                onChange={(e) => onSwitchYearsChange(e.target.value)}
                className={`${inputClass} w-16 text-right`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
