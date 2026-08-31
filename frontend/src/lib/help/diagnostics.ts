// Diagnostics bundle (HELP CENTER ARC, H4): the plain-text block "Copy
// diagnostics" (About dialog, palette `help.copyDiagnostics`) puts on the
// clipboard for a support request — app + build, backend URL and state, data
// source, as-of, lens + node, workflow, browser. PURE: the caller gathers the
// snapshot from the live contexts; this module formats it and copies it.

export interface DiagnosticsSnapshot {
  appVersion: string;
  buildMode: string;
  backendUrl: string;
  connected: boolean;
  dataSource: string | null;
  asOf: string | null;
  lens: string;
  node: string | null;
  tabs: number;
  groups: number;
  workflowBusy: boolean;
  lastAction: string | null;
  lastError: string | null;
  fitMode: string | null;
  colorScheme: string | null;
  userAgent: string;
  viewport: string;
  now: string;
}

/** Render the snapshot as an aligned key: value block (stable key order). */
export function formatDiagnostics(s: DiagnosticsSnapshot): string {
  const rows: [string, string][] = [
    ["VolFit", `v${s.appVersion} (${s.buildMode})`],
    ["Time", s.now],
    ["Backend", `${s.backendUrl} · ${s.connected ? "connected" : "offline (mock data)"}`],
    ["Data source", s.dataSource ?? "—"],
    ["As-of", s.asOf ?? "—"],
    ["Fit target", s.fitMode ?? "—"],
    ["Lens", s.lens],
    ["Active node", s.node ?? "—"],
    ["Tabs / groups", `${s.tabs} / ${s.groups}`],
    ["Workflow", s.workflowBusy ? "busy" : "idle"],
    ["Last action", s.lastAction ?? "—"],
    ["Last error", s.lastError ?? "—"],
    ["Colour scheme", s.colorScheme ?? "—"],
    ["Browser", s.userAgent],
    ["Viewport", s.viewport],
  ];
  const w = Math.max(...rows.map(([k]) => k.length));
  return ["VolFit diagnostics", "=".repeat(18), ...rows.map(([k, v]) => `${k.padEnd(w)}  ${v}`)].join("\n");
}

/** Clipboard write with a textarea fallback; resolves true on success. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the legacy path */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
