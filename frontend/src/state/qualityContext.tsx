// Shared quality report (UI SHELL v2, S2): ONE GET /quality read (per view
// epoch) feeding both the nodes pane's status glyphs and the Quality lens.
// Wraps useQuality so its fetch contract (and the QualityViewer test's mock)
// stay untouched; consumers read the context, falling back to a fresh hook
// call is deliberately NOT offered — mount the provider.
import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { useQuality } from "./useQuality";
import type { QualityNode, UseQualityResult } from "./useQuality";

export interface QualityContextValue extends UseQualityResult {
  /** "T|expiry" -> node row (fast lookup for the tree / node card). */
  nodeOf: (ticker: string, expiry: string) => QualityNode | undefined;
}

const Ctx = createContext<QualityContextValue | null>(null);

export function QualityProvider({ children }: { children: ReactNode }) {
  const q = useQuality();
  const index = useMemo(() => {
    const m = new Map<string, QualityNode>();
    for (const n of q.report?.nodes ?? []) m.set(`${n.ticker}|${n.expiry}`, n);
    return m;
  }, [q.report]);
  const value = useMemo<QualityContextValue>(
    () => ({ ...q, nodeOf: (t, e) => index.get(`${t}|${e}`) }),
    [q, index],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useQualityReport(): QualityContextValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useQualityReport must be used within QualityProvider");
  return ctx;
}
