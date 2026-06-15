// Global display/UX preferences (the View tab): colour scheme, contrast and
// brightness. Pure presentation, so — like expiryFormat — it lives in a
// lightweight localStorage-backed context rather than the backend settings.
//
// The scheme drives `data-theme` on <html> (index.css re-skins the palette);
// contrast/brightness drive the `--ui-contrast` / `--ui-brightness` filter knobs
// on the same element. All three are applied imperatively so a reload restores
// the look before React paints (see applyTheme).
//
// Persistence is EXPLICIT ([REQ 2026-06-15]): a change applies live (instant
// preview) but is NOT written to localStorage until the View tab's "Save as
// default" button calls saveDefault(). On load the saved default is restored;
// unsaved tweaks are lost on reload. `dirty` (live != saved) drives the
// Save/Reset bar, mirroring the Options tab.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

export type ColorScheme = "dark" | "light" | "contrast" | "warm";

export const COLOR_SCHEMES: { id: ColorScheme; label: string; hint: string }[] = [
  { id: "dark", label: "Dark", hint: "Default deep-slate trading look" },
  { id: "light", label: "Light", hint: "Paper canvas with dark ink" },
  { id: "contrast", label: "High contrast", hint: "Near-black, maximally legible" },
  { id: "warm", label: "Warm", hint: "Warm surfaces + amber accent" },
];

/** Slider bounds (multipliers passed straight to the CSS `filter`). */
export const CONTRAST_RANGE = { min: 0.8, max: 1.4, step: 0.02 } as const;
export const BRIGHTNESS_RANGE = { min: 0.7, max: 1.3, step: 0.02 } as const;

interface ViewSettings {
  scheme: ColorScheme;
  contrast: number;
  brightness: number;
}

const DEFAULTS: ViewSettings = { scheme: "dark", contrast: 1, brightness: 1 };
const STORAGE_KEY = "volfit.viewSettings";
const SCHEME_IDS = COLOR_SCHEMES.map((s) => s.id);

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

function loadInitial(): ViewSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw) as Partial<ViewSettings>;
      return {
        scheme: SCHEME_IDS.includes(p.scheme as ColorScheme) ? (p.scheme as ColorScheme) : DEFAULTS.scheme,
        contrast: clamp(Number(p.contrast ?? 1) || 1, CONTRAST_RANGE.min, CONTRAST_RANGE.max),
        brightness: clamp(Number(p.brightness ?? 1) || 1, BRIGHTNESS_RANGE.min, BRIGHTNESS_RANGE.max),
      };
    }
  } catch {
    /* localStorage unavailable / malformed: fall through */
  }
  return DEFAULTS;
}

/** Push the settings onto <html> so index.css + the filter pick them up. */
function applyTheme(s: ViewSettings): void {
  const el = document.documentElement;
  el.dataset.theme = s.scheme;
  el.style.setProperty("--ui-contrast", String(s.contrast));
  el.style.setProperty("--ui-brightness", String(s.brightness));
}

function persist(s: ViewSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* best-effort */
  }
}

interface ViewSettingsCtx extends ViewSettings {
  setScheme: (s: ColorScheme) => void;
  setContrast: (v: number) => void;
  setBrightness: (v: number) => void;
  /** Revert the live look to the built-in defaults (does not persist). */
  reset: () => void;
  /** Persist the current look as this device's default (the Save button). */
  saveDefault: () => void;
  /** Live settings differ from the saved default. */
  dirty: boolean;
}

const Ctx = createContext<ViewSettingsCtx | null>(null);

function eq(a: ViewSettings, b: ViewSettings): boolean {
  return a.scheme === b.scheme && a.contrast === b.contrast && a.brightness === b.brightness;
}

export function ViewSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ViewSettings>(loadInitial);
  //: The persisted default — what a reload restores; only saveDefault() moves it.
  const [saved, setSaved] = useState<ViewSettings>(loadInitial);

  // Apply (live preview) on mount and whenever any knob changes — but do NOT
  // persist here; persistence is explicit (saveDefault).
  useEffect(() => {
    applyTheme(settings);
  }, [settings]);

  const setScheme = useCallback((scheme: ColorScheme) => setSettings((s) => ({ ...s, scheme })), []);
  const setContrast = useCallback(
    (contrast: number) => setSettings((s) => ({ ...s, contrast: clamp(contrast, CONTRAST_RANGE.min, CONTRAST_RANGE.max) })),
    [],
  );
  const setBrightness = useCallback(
    (brightness: number) => setSettings((s) => ({ ...s, brightness: clamp(brightness, BRIGHTNESS_RANGE.min, BRIGHTNESS_RANGE.max) })),
    [],
  );
  const reset = useCallback(() => setSettings(DEFAULTS), []);
  const saveDefault = useCallback(() => {
    persist(settings);
    setSaved(settings);
  }, [settings]);

  return (
    <Ctx.Provider
      value={{ ...settings, setScheme, setContrast, setBrightness, reset, saveDefault, dirty: !eq(settings, saved) }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useViewSettings(): ViewSettingsCtx {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useViewSettings must be used within ViewSettingsProvider");
  return ctx;
}
