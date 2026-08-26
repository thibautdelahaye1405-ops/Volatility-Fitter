// Modal dialog primitive of the workbench (UI SHELL v2, S2): a dimmed
// backdrop (click closes), Esc closes, a title bar with a × button, and a
// body that fills the remaining height — the children own their scrolling
// (the Settings dialog scrolls its section column, the Universe dialog its
// node matrix). Rendered inline by the shell (no portal needed: the shell is
// the last child of #root, so z-50 sits above every pane).
import { useEffect } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Muted line under the title. */
  subtitle?: string;
  /** Tailwind width classes for the panel (default: a wide workspace dialog). */
  width?: string;
  /** Tailwind height classes (default: 84vh, capped). */
  height?: string;
  children: ReactNode;
}

export default function Dialog({
  open,
  onClose,
  title,
  subtitle,
  width = "w-[min(96vw,72rem)]",
  height = "h-[min(88vh,52rem)]",
  children,
}: DialogProps) {
  // Esc closes (only while open; the shell's shortcut hook defers to us).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <button
        className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-[2px]"
        aria-label="Close dialog"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={[
          "relative flex flex-col overflow-hidden rounded-xl border border-slate-700",
          "bg-surface-900 shadow-2xl shadow-black/60",
          width,
          height,
        ].join(" ")}
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-slate-800 px-4 py-2.5">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
            {subtitle && <p className="truncate text-[11px] text-slate-500">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            title="Close (Esc)"
            className="ml-auto rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200"
          >
            <X size={15} strokeWidth={1.75} />
          </button>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
