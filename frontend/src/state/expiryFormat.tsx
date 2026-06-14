// Global expiry-format preference, shared across every workspace and persisted
// to localStorage (ROADMAP Phase 10 follow-up). A pure display setting, so it
// lives in its own lightweight context rather than the backend settings.
import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { EXPIRY_FORMATS } from "../lib/expiryFormat";
import type { ExpiryFormat } from "../lib/expiryFormat";

const STORAGE_KEY = "volfit.expiryFormat";
const IDS = EXPIRY_FORMATS.map((f) => f.id);

function loadInitial(): ExpiryFormat {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && IDS.includes(v as ExpiryFormat)) return v as ExpiryFormat;
  } catch {
    /* localStorage unavailable (SSR / privacy mode): fall through */
  }
  return "dmy";
}

function persist(f: ExpiryFormat): void {
  try {
    localStorage.setItem(STORAGE_KEY, f);
  } catch {
    /* best-effort */
  }
}

interface ExpiryFormatCtx {
  format: ExpiryFormat;
  setFormat: (f: ExpiryFormat) => void;
  /** Advance to the next format in the cycle (the header ↻ button). */
  cycle: () => void;
}

const Ctx = createContext<ExpiryFormatCtx | null>(null);

export function ExpiryFormatProvider({ children }: { children: ReactNode }) {
  const [format, setFormatState] = useState<ExpiryFormat>(loadInitial);

  const setFormat = useCallback((f: ExpiryFormat) => {
    setFormatState(f);
    persist(f);
  }, []);

  const cycle = useCallback(() => {
    setFormatState((prev) => {
      const next = IDS[(IDS.indexOf(prev) + 1) % IDS.length];
      persist(next);
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ format, setFormat, cycle }}>{children}</Ctx.Provider>;
}

export function useExpiryFormat(): ExpiryFormatCtx {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useExpiryFormat must be used within ExpiryFormatProvider");
  return ctx;
}
