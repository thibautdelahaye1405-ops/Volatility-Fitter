// Centered placeholder card used by views that are not yet implemented.
import type { ReactNode } from "react";

interface PlaceholderCardProps {
  title: string;
  /** Short description of what will live in this workspace. */
  children: ReactNode;
}

export default function PlaceholderCard({
  title,
  children,
}: PlaceholderCardProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-lg rounded-xl border border-slate-800 bg-surface-900 p-8 shadow-xl shadow-black/30">
        <h2 className="mb-3 text-lg font-semibold text-slate-100">{title}</h2>
        <div className="text-sm leading-relaxed text-slate-400">{children}</div>
        <div className="mt-6 inline-flex items-center gap-2 rounded-md border border-slate-800 bg-surface-800 px-3 py-1.5 text-xs font-medium text-slate-500">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-500" />
          Under construction
        </div>
      </div>
    </div>
  );
}
