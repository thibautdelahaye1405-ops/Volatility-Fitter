// Top navigation bar: product branding plus workspace tabs.
import type { TabDef, TabId } from "../App";

interface TopBarProps {
  tabs: TabDef[];
  activeTab: TabId;
  onSelect: (tab: TabId) => void;
}

export default function TopBar({ tabs, activeTab, onSelect }: TopBarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-8 border-b border-slate-800 bg-surface-900 px-6">
      {/* Brand mark */}
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent-600/20 font-mono text-sm font-bold text-accent-400">
          σ
        </span>
        <h1 className="text-sm font-semibold tracking-wide text-slate-100">
          Vol Fitter
        </h1>
      </div>

      {/* Workspace tabs */}
      <nav className="flex h-full items-stretch gap-1" aria-label="Workspaces">
        {tabs.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => onSelect(tab.id)}
              aria-current={active ? "page" : undefined}
              className={[
                "relative px-4 text-sm font-medium transition-colors",
                active
                  ? "text-accent-400"
                  : "text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {tab.label}
              {/* Active-tab underline indicator */}
              {active && (
                <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent-500" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Right-side status placeholder (backend connectivity, user, etc.) */}
      <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-600" />
        Backend offline
      </div>
    </header>
  );
}
