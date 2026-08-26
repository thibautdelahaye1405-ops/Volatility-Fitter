// Shared Tailwind class strings for the workbench chrome + lenses (UI SHELL
// v2). One place for the control grammar so every workspace reads the same:
// selects, bordered buttons, cards, toolbar chips.

/** Header/toolbar <select>. */
export const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** Bordered secondary button. */
export const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** Primary (accent) button. */
export const primaryButtonClass =
  "rounded-md bg-accent-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors " +
  "enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40";

/** Elevated card (chart cards, asides). */
export const cardClass =
  "rounded-xl border border-slate-800 bg-surface-900 shadow-xl shadow-black/30";

/** Toolbar toggle chip; pass `on` for the lit state and an optional tone. */
export function chipClass(on: boolean, tone: "accent" | "red" | "slate" | "violet" = "accent"): string {
  const lit: Record<typeof tone, string> = {
    accent: "border-accent-500/50 bg-accent-500/10 text-accent-300",
    red: "border-red-500/50 bg-red-500/10 text-red-300",
    slate: "border-slate-400/60 bg-slate-500/15 text-slate-200",
    violet: "border-violet-500/50 bg-violet-500/10 text-violet-300",
  };
  return [
    "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
    on ? lit[tone] : "border-slate-700 text-slate-400 hover:text-slate-200",
  ].join(" ");
}

/** Small status badge (LIVE / MOCK / STALE / UPDATED). */
export function badgeClass(tone: "accent" | "amber" | "emerald" | "rose"): string {
  const t: Record<typeof tone, string> = {
    accent: "border-accent-500/40 bg-accent-500/10 text-accent-400",
    amber: "border-amber-500/40 bg-amber-500/10 text-amber-400",
    emerald: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
    rose: "border-rose-500/40 bg-rose-500/10 text-rose-400",
  };
  return `rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider ${t[tone]}`;
}

/** Centered placeholder for a chart-card body state. */
export const chartMessageClass =
  "flex h-full items-center justify-center text-xs text-slate-500";
