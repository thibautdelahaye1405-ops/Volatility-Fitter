// Menubar face button (UI SHELL v2): the flat "Universe ▾ / Options / Help ▾"
// triggers of the top bar — VS Code menubar look, lit while its menu is open
// or its dialog is active.
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

export default function MenuButton({
  label,
  active = false,
  chevron = false,
  title,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  /** Show a ▾ (the button opens a dropdown). */
  chevron?: boolean;
  title?: string;
  onClick: () => void;
  /** Optional leading icon. */
  children?: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-haspopup={chevron ? "menu" : undefined}
      aria-expanded={chevron ? active : undefined}
      className={[
        "flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors",
        active ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/70 hover:text-slate-100",
      ].join(" ")}
    >
      {children}
      <span>{label}</span>
      {chevron && <ChevronDown size={11} className="text-slate-500" />}
    </button>
  );
}
