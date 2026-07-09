// Shared dropdown primitives for the top bar: an anchored panel with a
// click-away backdrop, plus consistently styled rows (item / section label /
// divider). Every top-bar menu (brand, workspace groups, fetch, priors,
// market context) composes these so the chrome stays uniform.
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/** Anchored dropdown panel. Render inside a `relative` wrapper, right after
 *  the trigger button; `open` gates everything (backdrop included). */
export function MenuPanel({
  open,
  onClose,
  align = "left",
  width = "w-60",
  children,
}: {
  open: boolean;
  onClose: () => void;
  align?: "left" | "right";
  width?: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <>
      {/* Click-away backdrop */}
      <button className="fixed inset-0 z-10 cursor-default" aria-hidden onClick={onClose} />
      <div
        className={[
          "absolute z-20 mt-1 max-h-[70vh] overflow-auto rounded-lg border border-slate-700",
          "bg-surface-800 py-1 shadow-xl shadow-black/40",
          align === "right" ? "right-0" : "left-0",
          width,
        ].join(" ")}
      >
        {children}
      </div>
    </>
  );
}

/** One menu row. The label lives in its own <span> (stable hook for UI
 *  automation); `detail` is a muted right-aligned annotation. */
export function MenuItem({
  icon: Icon,
  label,
  detail,
  active = false,
  disabled = false,
  title,
  onClick,
}: {
  icon?: LucideIcon;
  label: string;
  detail?: string;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      disabled={disabled}
      title={title}
      onClick={onClick}
      className={[
        "flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors",
        disabled
          ? "cursor-not-allowed text-slate-600"
          : active
            ? "bg-accent-500/10 text-accent-300"
            : "text-slate-300 hover:bg-slate-700/40 hover:text-slate-100",
      ].join(" ")}
    >
      {Icon && <Icon size={14} strokeWidth={1.75} className="shrink-0 opacity-80" />}
      <span className="flex-1 font-medium">{label}</span>
      {detail && <span className="truncate text-[10px] text-slate-500">{detail}</span>}
      {active && <span className="text-accent-400">✓</span>}
    </button>
  );
}

/** Small uppercase section label between item groups. */
export function MenuSection({ label }: { label: string }) {
  return (
    <div className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-slate-600">
      {label}
    </div>
  );
}

export function MenuDivider() {
  return <div className="my-1 border-t border-slate-700/60" />;
}
