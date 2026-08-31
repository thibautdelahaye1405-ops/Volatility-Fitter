// Help ▸ Welcome (HELP CENTER ARC, H4): the landing page — the product in one
// paragraph, the four-step workflow (Universe → Fetch → Calibrate → Read),
// the tip of the day, the page directory and the two ways to get help fast.
// First run opens it once (state/help); Help ▾ Welcome brings it back.
import { ArrowRight, Compass, Keyboard, MessageCircleQuestion, Terminal } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHelp } from "../../state/help";
import { useWorkflowContext } from "../../state/workflowContext";
import { HELP_PAGES } from "../../lib/help/pages";
import { TIPS } from "../../lib/help/tips";
import { Markdown } from "../../lib/help/markdown";
import { APP_VERSION } from "../../lib/appInfo";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, GHOST_BTN } from "./HelpCards";

const STEPS: { n: string; title: string; body: string; link: string }[] = [
  { n: "1", title: "Pick a universe", body: "Universe ▾ Manage universe… (Ctrl+Shift+U): add tickers, choose expiries, light the nodes you have quotes for, pick the data source. Save it under a name.", link: "help:guides:universe" },
  { n: "2", title: "Fetch a snapshot", body: "Fetch ▾ Snapshot pulls quotes + spot for every ticker at the chosen as-of (live, previous close, or a past moment).", link: "help:guides:workflow" },
  { n: "3", title: "Calibrate", body: "Calibrate ▾ fits every lit node — parametric smiles, the local-vol surface, or both — in the background; the status bar narrates progress.", link: "help:guides:workflow" },
  { n: "4", title: "Read the surfaces", body: "Open nodes from the Nodes pane into tabs; switch lenses with Alt+1…5 — Graph, Forwards, Parametric, Local Vol, Quality — and publish from Quality.", link: "help:guides:workbench" },
];

const FAST: { icon: LucideIcon; title: string; body: string; command: string; label: string }[] = [
  { icon: Terminal, title: "Every command", body: "Ctrl+K opens the palette: type what you want to do.", command: "help.palette", label: "Open the palette" },
  { icon: Keyboard, title: "Help for this view", body: "F1 opens the guide of the lens or dialog in front of you.", command: "help.context", label: "Help for this view" },
  { icon: MessageCircleQuestion, title: "Ask @Vol-Fitter", body: "Ctrl+Shift+/ — ask a question in your own words.", command: "help.ask", label: "Ask a question" },
  { icon: Compass, title: "Walkthrough", body: "A 12-step tour of the shell over the live application.", command: "help.walkthrough", label: "Start the tour" },
];

export default function WelcomePage() {
  const help = useHelp();
  const links = useHelpLinks();
  const { live } = useWorkflowContext();
  const tip = TIPS.length ? TIPS[((help.tipIndex % TIPS.length) + TIPS.length) % TIPS.length] : null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <section className="flex items-start gap-4">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent-600/20 font-mono text-2xl font-bold text-accent-400">σ</span>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Welcome to VolFit <span className="font-mono text-xs text-slate-500">v{APP_VERSION}</span></h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-400">
            VolFit fits implied-volatility smiles under explicit no-arbitrage control — LQD, SVI-JW and Multi-Core
            Sigmoid slices plus a jointly calibrated local-volatility surface — and extrapolates sparse observations to the
            whole universe of smiles by propagating signal through a graph whose nodes are (underlying, expiry). Every
            control has a reference entry, every command an explanation, and F1 is never far.
          </p>
          {!live && (
            <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
              The backend is offline: the shell runs on mock data. Start it with <code className="font-mono">.\restart.ps1</code>; the guides and references work either way.
            </p>
          )}
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">The four-step workflow</h3>
        <ol className="grid gap-2 md:grid-cols-2">
          {STEPS.map((s) => (
            <li key={s.n} className="flex gap-3 rounded-lg border border-slate-800 bg-surface-800/40 p-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-600/20 font-mono text-xs font-bold text-accent-300">{s.n}</span>
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-slate-100">{s.title}</div>
                <p className="mt-0.5 text-xs text-slate-400">{s.body}</p>
                <button onClick={() => links.open(s.link)} className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-accent-400 hover:text-accent-300">
                  Guide <ArrowRight size={11} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Help, fast</h3>
        <div className="grid gap-2 md:grid-cols-4">
          {FAST.map((f) => (
            <div key={f.title} className="flex flex-col gap-1.5 rounded-lg border border-slate-800 bg-surface-800/40 p-3">
              <f.icon size={16} className="text-accent-400" />
              <div className="text-[13px] font-semibold text-slate-100">{f.title}</div>
              <p className="flex-1 text-xs text-slate-400">{f.body}</p>
              <button onClick={() => links.run(f.command)} className={`${ACTION_BTN} self-start`}>▶ {f.label}</button>
            </div>
          ))}
        </div>
      </section>

      {tip && (
        <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
          <div className="flex items-center gap-2">
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Tip of the day</h3>
            <span className="text-[13px] font-semibold text-slate-100">{tip.title}</span>
            <button onClick={help.nextTip} className={`${GHOST_BTN} ml-auto`}>Another tip</button>
          </div>
          <Markdown source={tip.body} handlers={links} className="mt-1" />
          {tip.action && <button onClick={() => links.run(tip.action!.command, tip.action!.arg)} className={`${ACTION_BTN} mt-2`}>▶ {tip.action.label}</button>}
        </section>
      )}

      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">In this Help Center</h3>
        <div className="grid gap-1.5 md:grid-cols-2">
          {HELP_PAGES.filter((p) => p.id !== "welcome").map((p) => (
            <button key={p.id} onClick={() => help.navigate({ page: p.id })}
              className="flex items-baseline gap-2 rounded-md px-2 py-1.5 text-left hover:bg-slate-800/60">
              <span className="text-xs font-semibold text-slate-200">{p.label}</span>
              <span className="truncate text-[11px] text-slate-500">{p.blurb}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
