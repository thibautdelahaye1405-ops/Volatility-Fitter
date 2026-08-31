// Help Center state (HELP CENTER ARC, H1): which page / entry the center
// shows, its back/forward history and search query, the Walkthrough tour
// (active flag + step), the first-run Welcome flag and the tip-of-the-day
// index — persisted in localStorage ("volfit.help.v1"). The provider mounts
// inside WorkbenchProvider because opening a page opens the shell's "help"
// dialog; the registry commands (state/commands.tsx) call openHelp / startTour.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useWorkbench } from "./workbench";
import { parseHelpLink } from "../lib/help/pages";
import type { HelpLink } from "../lib/help/types";
import { TOUR_STEPS } from "../lib/help/walkthrough";
import { guideForLens } from "../lib/help/guides";

const STORAGE_KEY = "volfit.help.v1";
const HOME: HelpLink = { page: "welcome" };

interface Persisted {
  seenWelcome: boolean;
  tourDone: boolean;
  /** Last tour step reached (resume point). */
  tourStep: number;
  lastLink: string;
}

const DEFAULT_PERSISTED: Persisted = { seenWelcome: false, tourDone: false, tourStep: 0, lastLink: "welcome" };

function load(): Persisted {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (!raw) return DEFAULT_PERSISTED;
    const p = JSON.parse(raw) as Partial<Persisted>;
    return {
      seenWelcome: p.seenWelcome === true,
      tourDone: p.tourDone === true,
      tourStep: Number.isInteger(p.tourStep) ? Math.max(0, Math.min(TOUR_STEPS.length - 1, Number(p.tourStep))) : 0,
      lastLink: typeof p.lastLink === "string" ? p.lastLink : "welcome",
    };
  } catch {
    return DEFAULT_PERSISTED;
  }
}

function save(p: Persisted): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* private mode / quota — the flags simply do not persist */
  }
}

export interface HelpValue {
  /** The page + optional entry anchor the center shows. */
  link: HelpLink;
  /** Open the center on a page / entry ("settings:gridXNodes" or a HelpLink). */
  openHelp: (to?: HelpLink | string) => void;
  /** Navigate inside the open center (pushes history). */
  navigate: (to: HelpLink | string) => void;
  back: () => void;
  forward: () => void;
  canBack: boolean;
  canForward: boolean;
  /** Help ▸ Help for this view (F1): the guide of the active lens / dialog. */
  openContextHelp: () => void;
  /** Search box of the center (shared by every page). */
  query: string;
  setQuery: (q: string) => void;
  /** Walkthrough. */
  tour: { active: boolean; step: number; done: boolean };
  startTour: (fromStart?: boolean) => void;
  endTour: (completed?: boolean) => void;
  tourNext: () => void;
  tourPrev: () => void;
  tourGo: (step: number) => void;
  /** First-run Welcome. */
  seenWelcome: boolean;
  markWelcomeSeen: () => void;
  /** Tip of the day (rotates daily; Next picks another). */
  tipIndex: number;
  nextTip: () => void;
}

const Ctx = createContext<HelpValue | null>(null);

function dayIndex(): number {
  return Math.floor(Date.now() / 86_400_000);
}

export function HelpProvider({ children }: { children: ReactNode }) {
  const wb = useWorkbench();
  const persisted = useRef<Persisted>(load());
  const [history, setHistory] = useState<HelpLink[]>([parseHelpLink(persisted.current.lastLink) ?? HOME]);
  const [cursor, setCursor] = useState(0);
  const [query, setQuery] = useState("");
  const [tour, setTour] = useState({ active: false, step: persisted.current.tourStep, done: persisted.current.tourDone });
  const [seenWelcome, setSeenWelcome] = useState(persisted.current.seenWelcome);
  const [tipIndex, setTipIndex] = useState(dayIndex());

  const persist = useCallback((patch: Partial<Persisted>) => {
    persisted.current = { ...persisted.current, ...patch };
    save(persisted.current);
  }, []);

  const link = history[cursor] ?? HOME;

  const navigate = useCallback((to: HelpLink | string) => {
    const target = typeof to === "string" ? parseHelpLink(to) : to;
    if (!target) return;
    setHistory((h) => {
      const cur = h[cursor];
      if (cur && cur.page === target.page && cur.anchor === target.anchor) return h;
      return [...h.slice(0, cursor + 1), target];
    });
    setCursor((c) => {
      const cur = history[c];
      return cur && cur.page === target.page && cur.anchor === target.anchor ? c : c + 1;
    });
    persist({ lastLink: target.anchor ? `${target.page}:${target.anchor}` : target.page });
  }, [cursor, history, persist]);

  const openHelp = useCallback((to?: HelpLink | string) => {
    if (to !== undefined) navigate(to);
    setQuery("");
    wb.openDialog("help");
  }, [navigate, wb]);

  const back = useCallback(() => setCursor((c) => Math.max(0, c - 1)), []);
  const forward = useCallback(() => setCursor((c) => Math.min(history.length - 1, c + 1)), [history.length]);

  // F1: the guide of the open dialog, else of the active lens.
  const openContextHelp = useCallback(() => {
    const d = wb.dialog;
    const anchor = d === "options" ? "options" : d === "universe" ? "universe" : guideForLens(wb.activity);
    openHelp({ page: "guides", anchor });
  }, [openHelp, wb.activity, wb.dialog]);

  // Walkthrough — the overlay reads `tour`; the dialog closes so the shell is visible.
  const startTour = useCallback((fromStart = false) => {
    const step = fromStart || tour.done ? 0 : tour.step;
    wb.closeDialog();
    setTour({ active: true, step, done: false });
  }, [tour.done, tour.step, wb]);
  const endTour = useCallback((completed = false) => {
    setTour((t) => ({ active: false, step: completed ? 0 : t.step, done: completed || t.done }));
    persist({ tourDone: completed || persisted.current.tourDone, tourStep: completed ? 0 : tour.step });
  }, [persist, tour.step]);
  const tourGo = useCallback((step: number) => {
    const s = Math.max(0, Math.min(TOUR_STEPS.length - 1, step));
    setTour((t) => ({ ...t, step: s }));
    persist({ tourStep: s });
  }, [persist]);
  const tourNext = useCallback(() => {
    if (tour.step >= TOUR_STEPS.length - 1) endTour(true);
    else tourGo(tour.step + 1);
  }, [endTour, tour.step, tourGo]);
  const tourPrev = useCallback(() => tourGo(tour.step - 1), [tour.step, tourGo]);

  const markWelcomeSeen = useCallback(() => {
    setSeenWelcome(true);
    persist({ seenWelcome: true });
  }, [persist]);
  const nextTip = useCallback(() => setTipIndex((i) => i + 1), []);

  // First run: open the Welcome page once (after the shell painted; never
  // over another dialog, never in a test DOM).
  useEffect(() => {
    if (seenWelcome || typeof window === "undefined" || wb.dialog !== null) return;
    if (typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent)) return;
    const t = window.setTimeout(() => {
      navigate(HOME);
      wb.openDialog("help");
      markWelcomeSeen();
    }, 600);
    return () => window.clearTimeout(t);
    // Intentionally only on mount + the seen flag: a later dialog must not re-trigger it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seenWelcome]);

  const value = useMemo<HelpValue>(() => ({
    link, openHelp, navigate, back, forward,
    canBack: cursor > 0, canForward: cursor < history.length - 1,
    openContextHelp, query, setQuery,
    tour, startTour, endTour, tourNext, tourPrev, tourGo,
    seenWelcome, markWelcomeSeen, tipIndex, nextTip,
  }), [link, openHelp, navigate, back, forward, cursor, history.length, openContextHelp, query, tour,
    startTour, endTour, tourNext, tourPrev, tourGo, seenWelcome, markWelcomeSeen, tipIndex, nextTip]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useHelp(): HelpValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useHelp must be used within HelpProvider");
  return ctx;
}

/** Null outside the provider (tests / legacy mounts). */
export function useOptionalHelp(): HelpValue | null {
  return useContext(Ctx);
}
