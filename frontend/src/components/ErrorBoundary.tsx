// Catches render-time crashes in a workspace view so one bad render never
// white-screens the whole app. Shows the error (so it can be reported) with a
// "Try again" (re-render) and "Reload" escape hatch; the TopBar and the other
// tabs stay usable. Wrap each view, keyed by tab, so switching tabs clears it.
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Shown in the fallback header (e.g. the workspace name). */
  label?: string;
}

interface State {
  error: Error | null;
  stack: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, stack: "" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the full error + component stack on the console for reporting.
    // eslint-disable-next-line no-console
    console.error("View crashed:", error, info.componentStack);
    this.setState({ stack: info.componentStack ?? "" });
  }

  private reset = (): void => this.setState({ error: null, stack: "" });

  render(): ReactNode {
    const { error, stack } = this.state;
    if (!error) return this.props.children;

    const firstFrame = stack.trim().split("\n")[0]?.trim() ?? "";
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="max-w-lg rounded-xl border border-rose-500/40 bg-rose-500/5 p-5 shadow-xl shadow-black/30">
          <h3 className="text-sm font-semibold text-rose-300">
            {this.props.label ? `${this.props.label} hit an error` : "This view hit an error"}
          </h3>
          <p className="mt-2 break-words font-mono text-[11px] text-slate-300">
            {error.message || String(error)}
          </p>
          {firstFrame && (
            <p className="mt-1 truncate font-mono text-[10px] text-slate-500">{firstFrame}</p>
          )}
          <p className="mt-3 text-[11px] text-slate-500">
            The rest of the app is fine — other tabs still work. Full details are in the
            browser console.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={this.reset}
              className="rounded-md border border-accent-600/60 bg-accent-600/15 px-3 py-1.5 text-[11px] font-medium text-accent-300 transition-colors hover:bg-accent-600/25"
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded-md border border-slate-700 bg-surface-800 px-3 py-1.5 text-[11px] font-medium text-slate-300 transition-colors hover:border-slate-600"
            >
              Reload app
            </button>
          </div>
        </div>
      </div>
    );
  }
}
