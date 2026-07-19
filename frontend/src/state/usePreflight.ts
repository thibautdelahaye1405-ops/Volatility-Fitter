// Pre-run diagnostics state (P5b U5): POST /graph/preflight with the SAME
// body Run would ship, auto-refreshed (debounced) whenever that body changes
// — the TopBar chip is always current and Run gating never races a stale
// report. The endpoint is a dry run (nothing fitted/solved/recorded), so
// refreshing on every knob edit is cheap by contract.
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { ExtrapolateBody } from "./useGraphExtrapolation";

export type PreflightSeverity = "blocker" | "warning" | "info";

export interface PreflightIssue {
  severity: PreflightSeverity;
  code: string;
  message: string;
  count: number;
}

export interface PreflightReport {
  universeNodes: number;
  litCount: number;
  darkCount: number;
  observationCount: number;
  propagationMode: string;
  ok: boolean;
  issues: PreflightIssue[];
}

const DEBOUNCE_MS = 500;

export interface UsePreflightResult {
  report: PreflightReport | null;
  loading: boolean;
  /** Fetch failure (offline/older backend) — the chip degrades to counts-only
   *  display and Run is NOT gated (fail-open: preflight is advisory infra). */
  error: string | null;
}

export function usePreflight(body: ExtrapolateBody): UsePreflightResult {
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stable key so an unchanged body doesn't refetch every render; the ref
  // carries the live value into the debounced effect.
  const bodyKey = JSON.stringify(body);
  const bodyRef = useRef(body);
  bodyRef.current = body;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .post<PreflightReport>("/graph/preflight", {
          body: bodyRef.current,
          signal: controller.signal,
        })
        .then((r) => {
          setReport(r);
          setError(null);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [bodyKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return { report, loading, error };
}
