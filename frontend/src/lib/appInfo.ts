// Build identity shared by the About dialog, the Welcome page and the
// diagnostics bundle (HELP CENTER ARC): one place for the version string and
// the Vite build mode, so the three never disagree.

/** Semantic version shown in About / diagnostics (bumped by hand on releases). */
export const APP_VERSION = "0.2.0";

/** "development" under `npm run dev`, "production" in the built bundle. */
export const BUILD_MODE: string = import.meta.env.MODE;

/** Frontend stack line for About. */
export const STACK = "React 19 · Vite · Tailwind v4";
