// Walkthrough overlay (HELP CENTER ARC, H5): Help ▸ Walkthrough… draws a
// spotlight over the LIVE shell — the target is found by its `data-tour`
// anchor (lib/help/walkthrough TOUR_STEPS), the rest of the screen dims, a
// card beside the target explains the step with an optional "Try it" action
// (a registry command), and Back / Next / Skip + the arrow keys drive it. The
// spotlight tracks layout changes (resize, panes toggling) while active. A
// hidden anchor (nodes pane / status bar off) shows the card centred with a
// one-click way to show the pane. State lives in state/help (resumable).
import { useEffect, useLayoutEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useHelp } from "../../state/help";
import { useWorkbench } from "../../state/workbench";
import { useOptionalCommands } from "../../state/commands";
import { TOUR_STEPS } from "../../lib/help/walkthrough";
import { Markdown } from "../../lib/help/markdown";
import { useHelpLinks } from "./useHelpLinks";

interface Rect { top: number; left: number; width: number; height: number }

const PAD = 6;
const CARD_W = 340;
const CARD_H_EST = 220;

function measure(anchor: string): Rect | null {
  const el = document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD };
}

/** Card position by preferred placement, clamped to the viewport. */
function place(rect: Rect | null, placement: string | undefined): { top: number; left: number } {
  const vw = window.innerWidth, vh = window.innerHeight;
  if (!rect) return { top: Math.max(16, vh / 2 - CARD_H_EST / 2), left: Math.max(16, vw / 2 - CARD_W / 2) };
  const gap = 12;
  let top: number, left: number;
  switch (placement) {
    case "right": top = rect.top; left = rect.left + rect.width + gap; break;
    case "left": top = rect.top; left = rect.left - CARD_W - gap; break;
    case "top": top = rect.top - CARD_H_EST - gap; left = rect.left; break;
    default: top = rect.top + rect.height + gap; left = rect.left; break;
  }
  left = Math.max(12, Math.min(vw - CARD_W - 12, left));
  top = Math.max(12, Math.min(vh - CARD_H_EST - 12, top));
  return { top, left };
}

export default function Walkthrough() {
  const help = useHelp();
  const wb = useWorkbench();
  const cmds = useOptionalCommands();
  const links = useHelpLinks();
  const { active, step } = help.tour;
  const s = TOUR_STEPS[step];
  const [rect, setRect] = useState<Rect | null>(null);
  const [tick, setTick] = useState(0);

  // Track the target while active: on step change, resize, and a slow poll
  // (panes animate / mount after commands run).
  useLayoutEffect(() => {
    if (!active || !s) return;
    setRect(measure(s.anchor));
  }, [active, s, tick]);
  useEffect(() => {
    if (!active) return;
    const onResize = () => setTick((t) => t + 1);
    window.addEventListener("resize", onResize);
    const id = window.setInterval(onResize, 400);
    return () => { window.removeEventListener("resize", onResize); window.clearInterval(id); };
  }, [active]);
  // Arrow keys / Enter drive the tour (Esc is handled by the shell shortcuts).
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "Enter") { help.tourNext(); e.preventDefault(); }
      else if (e.key === "ArrowLeft") { help.tourPrev(); e.preventDefault(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, help]);

  if (!active || !s) return null;
  const pos = place(rect, s.placement);
  const last = step === TOUR_STEPS.length - 1;
  const hiddenPane = rect === null && (s.anchor === "nodes" || s.anchor === "status" || s.anchor === "tabs");
  const showPane = () => {
    if (s.anchor === "nodes") wb.setLayout({ nodesPane: true });
    if (s.anchor === "status") wb.setLayout({ statusBar: true });
    setTick((t) => t + 1);
  };

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label={`Walkthrough step ${step + 1} of ${TOUR_STEPS.length}: ${s.title}`} data-tour-overlay>
      {/* Dim everything except the spotlight (a huge box-shadow does the cut-out). */}
      {rect ? (
        <div
          className="pointer-events-none absolute rounded-lg ring-2 ring-accent-400/90 transition-all duration-200"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height, boxShadow: "0 0 0 100vmax rgba(3, 7, 18, 0.72)" }}
        />
      ) : (
        <div className="absolute inset-0 bg-slate-950/75" />
      )}
      {/* Click-away skips nothing: the card owns the controls. */}
      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />

      <div
        className="absolute flex flex-col gap-3 rounded-xl border border-slate-700 bg-surface-900 p-4 shadow-2xl shadow-black/60"
        style={{ top: pos.top, left: pos.left, width: CARD_W }}
      >
        <div className="flex items-start gap-2">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-accent-400">Step {step + 1} of {TOUR_STEPS.length}</div>
            <h3 className="text-sm font-semibold text-slate-100">{s.title}</h3>
          </div>
          <button onClick={() => help.endTour(false)} title="Skip the walkthrough (Esc)" aria-label="Skip the walkthrough"
            className="ml-auto rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200">
            <X size={14} />
          </button>
        </div>
        <Markdown source={s.body} handlers={links} />
        {hiddenPane && (
          <button onClick={showPane} className="self-start rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300 hover:bg-amber-500/20">
            This pane is hidden — show it
          </button>
        )}
        {s.action && cmds && (
          <button
            onClick={() => cmds.run(s.action!.command, s.action!.arg)}
            disabled={!(cmds.byId(s.action.command)?.enabled ?? false)}
            className="self-start rounded-md border border-accent-600/50 bg-accent-600/10 px-2.5 py-1 text-[11px] font-medium text-accent-300 hover:bg-accent-600/20 disabled:cursor-not-allowed disabled:opacity-50"
            title={cmds.byId(s.action.command)?.enabled ? undefined : "Not available right now (needs the live backend or an open node)"}
          >
            ▶ {s.action.label}
          </button>
        )}
        <div className="flex items-center gap-2 pt-1">
          <div className="flex items-center gap-1">
            {TOUR_STEPS.map((t, i) => (
              <button key={t.id} onClick={() => help.tourGo(i)} aria-label={`Go to step ${i + 1}`}
                className={["h-1.5 rounded-full transition-all", i === step ? "w-4 bg-accent-400" : "w-1.5 bg-slate-600 hover:bg-slate-400"].join(" ")} />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={help.tourPrev} disabled={step === 0}
              className="flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">
              <ChevronLeft size={12} /> Back
            </button>
            <button onClick={help.tourNext}
              className="flex items-center gap-1 rounded-md border border-accent-600/60 bg-accent-600/20 px-2.5 py-1 text-[11px] font-medium text-accent-300 hover:bg-accent-600/30">
              {last ? "Finish" : "Next"} {!last && <ChevronRight size={12} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
