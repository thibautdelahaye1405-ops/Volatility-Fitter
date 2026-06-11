// Shared smile session: a single useSmile() instance lifted into React
// context so the data (and the backend fit session it mirrors) survives
// workspace tab switches, and so the TopBar can show real connectivity.
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { useSmile } from "./useSmile";
import type { UseSmileResult } from "./useSmile";

const SmileSessionContext = createContext<UseSmileResult | null>(null);

/** Mount once near the app root; provides the shared smile session. */
export function SmileSessionProvider({ children }: { children: ReactNode }) {
  const session = useSmile();
  return (
    <SmileSessionContext.Provider value={session}>
      {children}
    </SmileSessionContext.Provider>
  );
}

/** Consume the shared session; throws outside a SmileSessionProvider. */
export function useSmileSession(): UseSmileResult {
  const ctx = useContext(SmileSessionContext);
  if (ctx === null) {
    throw new Error("useSmileSession must be used within SmileSessionProvider");
  }
  return ctx;
}
