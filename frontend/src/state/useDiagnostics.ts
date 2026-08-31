// Diagnostics snapshot hook (HELP CENTER ARC, H4): gathers the live shell
// state — backend, data source, as-of, lens, node, tabs, workflow, last
// action / error, look — into the PURE DiagnosticsSnapshot that
// lib/help/diagnostics formats for "Copy diagnostics" (About dialog, palette).
import { useCallback } from "react";
import { API_BASE_URL } from "./api";
import { useWorkflowContext } from "./workflowContext";
import { useWorkbench } from "./workbench";
import { useSmileSession } from "./smileSession";
import { useViewSettings } from "./viewSettings";
import { APP_VERSION, BUILD_MODE } from "../lib/appInfo";
import type { DiagnosticsSnapshot } from "../lib/help/diagnostics";

/** Readable as-of line from the loosely-typed as-of state. */
function asOfLabel(asof: unknown): string | null {
  if (!asof || typeof asof !== "object") return null;
  const a = asof as Record<string, unknown>;
  const parts = ["mode", "on", "moment", "effective", "label"]
    .map((k) => a[k])
    .filter((v): v is string => typeof v === "string" && v !== "");
  return parts.length ? parts.join(" · ") : null;
}

export function useDiagnosticsSnapshot(): () => DiagnosticsSnapshot {
  const { live, workflow, dataSources, asof } = useWorkflowContext();
  const wb = useWorkbench();
  const { fitMode } = useSmileSession();
  const view = useViewSettings();
  return useCallback((): DiagnosticsSnapshot => {
    const source = dataSources.sources.find((s) => s.id === dataSources.active);
    const tab = wb.activeTab;
    const la = workflow.lastAction as { label?: string; at?: number | string } | null;
    const calibError = (workflow as { calib?: { error?: string | null } | null }).calib?.error ?? null;
    return {
      appVersion: APP_VERSION,
      buildMode: BUILD_MODE,
      backendUrl: API_BASE_URL,
      connected: live,
      dataSource: source ? `${source.label} · ${source.status}` : null,
      asOf: asOfLabel(asof.asof),
      lens: wb.activity,
      node: tab ? `${tab.ticker} ${tab.expiry}` : null,
      tabs: wb.tabs.length,
      groups: wb.groups.length,
      workflowBusy: workflow.busy,
      lastAction: la?.label ? `${la.label}${la.at ? ` @ ${new Date(la.at).toISOString()}` : ""}` : null,
      lastError: calibError || null,
      fitMode: fitMode ?? null,
      colorScheme: view.scheme,
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "—",
      viewport: typeof window !== "undefined" ? `${window.innerWidth}×${window.innerHeight}` : "—",
      now: new Date().toISOString(),
    };
  }, [live, workflow, dataSources, asof, wb, fitMode, view.scheme]);
}
