// Preflight chip (P5b U5): the TopBar's live pre-run report. Colour tells
// the state at a glance (rose = blocker gates Run; amber = warnings; emerald
// = clean; slate = no report — older backend or offline, fail-open), the
// popover lists every finding. Counts fall back to the shell's own numbers
// until a report lands.
import { useState } from "react";
import type { UsePreflightResult } from "../../state/usePreflight";

interface PreflightChipProps {
  preflight: UsePreflightResult;
  /** Shell-side fallback counts (pre-report display). */
  litCount: number;
  darkCount: number;
}

const SEVERITY_STYLE: Record<string, { dot: string; label: string }> = {
  blocker: { dot: "bg-rose-400", label: "text-rose-300" },
  warning: { dot: "bg-amber-400", label: "text-amber-300" },
  info: { dot: "bg-slate-500", label: "text-slate-400" },
};

export default function PreflightChip({ preflight, litCount, darkCount }: PreflightChipProps) {
  const [open, setOpen] = useState(false);
  const { report, loading } = preflight;

  const blockers = report?.issues.filter((i) => i.severity === "blocker").length ?? 0;
  const warnings = report?.issues.filter((i) => i.severity === "warning").length ?? 0;

  const dot =
    report === null
      ? "bg-slate-600"
      : blockers > 0
        ? "bg-rose-400"
        : warnings > 0
          ? "bg-amber-400"
          : "bg-emerald-400";
  const status =
    report === null
      ? `${litCount} lit · ${darkCount} dark`
      : blockers > 0
        ? `${blockers} blocker${blockers > 1 ? "s" : ""}`
        : warnings > 0
          ? `${warnings} warning${warnings > 1 ? "s" : ""}`
          : "preflight ok";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title={
          report === null
            ? "Universe composition (no preflight report — older backend or offline; Run is not gated). Click for details."
            : "Pre-run diagnostics — a dry run of exactly what Run would ship (nothing fitted or recorded). Click for the findings."
        }
        className="flex items-center gap-1.5 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${dot} ${loading ? "animate-pulse" : ""}`}
        />
        {status}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-80 rounded-lg border border-slate-700 bg-surface-900 p-2.5 shadow-2xl shadow-black/50">
          <p className="mb-1.5 font-mono text-[10px] text-slate-400">
            {report === null
              ? `${litCount} lit · ${darkCount} dark — no preflight report`
              : `${report.universeNodes} nodes · ${report.litCount} lit · ` +
                `${report.darkCount} dark · ${report.observationCount} observation` +
                `${report.observationCount === 1 ? "" : "s"}`}
          </p>
          {report === null ? (
            <p className="text-[10px] text-slate-500">
              Preflight needs the current backend; Run stays available
              (fail-open).
            </p>
          ) : report.issues.length === 0 ? (
            <p className="text-[10px] text-emerald-400">
              Clean — no findings for this configuration.
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {report.issues.map((issue, i) => {
                const style = SEVERITY_STYLE[issue.severity] ?? SEVERITY_STYLE.info!;
                return (
                  <div key={`${issue.code}-${i}`} className="flex items-start gap-1.5">
                    <span
                      className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${style!.dot}`}
                    />
                    <p className={`text-[10px] leading-snug ${style!.label}`}>
                      {issue.message}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
