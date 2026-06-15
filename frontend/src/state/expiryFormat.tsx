// Global expiry-format preference, shared across every workspace (ROADMAP
// Phase 10 follow-up). A pure display setting, so it lives in its own
// lightweight localStorage-backed context rather than the backend settings.
//
// Like viewSettings, persistence is EXPLICIT ([REQ 2026-06-15]): setFormat /
// cycle change the live format instantly but only saveDefault() (the View tab's
// "Save as default" button) writes it to localStorage. `dirty` reports an
// unsaved change so the View tab's Save/Reset bar covers the format too.
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
  /** Persist the current format as this device's default (the Save button). */
  saveDefault: () => void;
  /** Live format differs from the saved default. */
  dirty: boolean;
}

const Ctx = createContext<ExpiryFormatCtx | null>(null);

export function ExpiryFormatProvider({ children }: { children: ReactNode }) {
  const [format, setFormatState] = useState<ExpiryFormat>(loadInitial);
  //: The persisted default — what a reload restores; only saveDefault() moves it.
  const [saved, setSaved] = useState<ExpiryFormat>(loadInitial);

  // Changes apply live but are not persisted until saveDefault().
  const setFormat = useCallback((f: ExpiryFormat) => setFormatState(f), []);

  const cycle = useCallback(() => {
    setFormatState((prev) => IDS[(IDS.indexOf(prev) + 1) % IDS.length]);
  }, []);

  const saveDefault = useCallback(() => {
    persist(format);
    setSaved(format);
  }, [format]);

  return (
    <Ctx.Provider value={{ format, setFormat, cycle, saveDefault, dirty: format !== saved }}>
      {children}
    </Ctx.Provider>
  );
}

export function useExpiryFormat(): ExpiryFormatCtx {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useExpiryFormat must be used within ExpiryFormatProvider");
  return ctx;
}
