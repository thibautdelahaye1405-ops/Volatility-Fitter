// Help Center (HELP CENTER ARC, H4): ONE dialog, ten pages — a nav rail in
// the Options-dialog grammar (search box on top, page list, footer with the
// build + Walkthrough), a content column with back / forward, the page title
// and the page itself. A non-empty search query replaces the page with ranked
// results over the whole help corpus (lib/help/search). Pages are deep-linked
// through state/help (`link.page` + `link.anchor`); every page receives the
// anchor and the shared link handler (useHelpLinks).
import type { ComponentType } from "react";
import {
  ArrowLeft, ArrowRight, BookA, BookOpen, Compass, Keyboard, Library, Lightbulb, Megaphone,
  MessageCircleQuestion, Search, SlidersHorizontal, Sparkles, Terminal, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Dialog from "../shell/Dialog";
import { useHelp } from "../../state/help";
import { HELP_PAGES, helpPageDef } from "../../lib/help/pages";
import type { HelpPageId } from "../../lib/help/types";
import { APP_VERSION } from "../../lib/appInfo";
import { useHelpLinks } from "./useHelpLinks";
import { SearchResults } from "./HelpCards";
import WelcomePage from "./WelcomePage";
import GuidePage from "./GuidePage";
import CommandReference from "./CommandReference";
import SettingsReference from "./SettingsReference";
import ShortcutsPage from "./ShortcutsPage";
import GlossaryPage from "./GlossaryPage";
import TipsPage from "./TipsPage";
import DocsBrowser from "./DocsBrowser";
import AskPanel from "./AskPanel";
import WhatsNewPage from "./WhatsNewPage";

const ICONS: Record<string, LucideIcon> = {
  Sparkles, BookOpen, Terminal, SlidersHorizontal, Keyboard, BookA, Lightbulb, Library, MessageCircleQuestion, Megaphone,
};

export interface HelpPageProps {
  anchor?: string;
}

const PAGES: Record<HelpPageId, ComponentType<HelpPageProps>> = {
  welcome: WelcomePage,
  guides: GuidePage,
  commands: CommandReference,
  settings: SettingsReference,
  shortcuts: ShortcutsPage,
  glossary: GlossaryPage,
  tips: TipsPage,
  docs: DocsBrowser,
  ask: AskPanel,
  whatsnew: WhatsNewPage,
};

export default function HelpCenter({ open, onClose }: { open: boolean; onClose: () => void }) {
  const help = useHelp();
  const links = useHelpLinks();
  const page = helpPageDef(help.link.page);
  const Page = PAGES[help.link.page];
  const searching = help.query.trim().length > 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Help Center"
      subtitle={page.blurb}
      width="w-[min(97vw,84rem)]"
      height="h-[min(92vh,58rem)]"
    >
      <div className="flex h-full min-h-0">
        {/* Nav rail */}
        <nav aria-label="Help pages" className="flex w-60 shrink-0 flex-col border-r border-slate-800">
          <div className="p-2 pt-3">
            <label className="flex items-center gap-2 rounded-md border border-slate-700 bg-surface-950 px-2 py-1.5 focus-within:border-accent-600/60">
              <Search size={13} className="shrink-0 text-slate-500" />
              <input
                value={help.query}
                onChange={(e) => help.setQuery(e.target.value)}
                placeholder="Search help…"
                aria-label="Search help"
                className="min-w-0 flex-1 bg-transparent text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none"
              />
              {searching && (
                <button onClick={() => help.setQuery("")} title="Clear" className="text-slate-500 hover:text-slate-200">
                  <X size={12} />
                </button>
              )}
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {HELP_PAGES.map((p) => {
              const Icon = ICONS[p.icon] ?? BookOpen;
              const on = !searching && p.id === help.link.page;
              return (
                <div key={p.id}>
                  {p.groupStart && <div className="my-1.5 border-t border-slate-800/70" />}
                  <button
                    onClick={() => { help.setQuery(""); help.navigate({ page: p.id }); }}
                    aria-current={on ? "page" : undefined}
                    data-help-nav={p.id}
                    className={[
                      "flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-xs font-medium transition-colors",
                      on ? "bg-accent-500/10 text-accent-300" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
                    ].join(" ")}
                  >
                    <Icon size={14} strokeWidth={1.75} className="shrink-0 opacity-80" />
                    <span className="truncate">{p.label}</span>
                  </button>
                </div>
              );
            })}
          </div>
          <div className="border-t border-slate-800 p-2">
            <button
              onClick={() => help.startTour()}
              className="flex w-full items-center gap-2 rounded-md border border-accent-600/40 bg-accent-600/10 px-2.5 py-1.5 text-xs font-medium text-accent-300 hover:bg-accent-600/20"
            >
              <Compass size={13} /> {help.tour.done ? "Replay the Walkthrough" : help.tour.step > 0 ? "Resume the Walkthrough" : "Start the Walkthrough"}
            </button>
            <div className="mt-2 flex items-center justify-between px-1 font-mono text-[10px] text-slate-600">
              <span>VolFit v{APP_VERSION}</span>
              <button onClick={() => links.run("help.copyDiagnostics")} className="hover:text-slate-300" title="Copy a diagnostics bundle for a support request">
                copy diagnostics
              </button>
            </div>
          </div>
        </nav>

        {/* Content */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-2 border-b border-slate-800/70 px-4 py-2">
            <button onClick={help.back} disabled={!help.canBack} title="Back" aria-label="Back"
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40">
              <ArrowLeft size={14} />
            </button>
            <button onClick={help.forward} disabled={!help.canForward} title="Forward" aria-label="Forward"
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40">
              <ArrowRight size={14} />
            </button>
            <h3 className="ml-1 text-sm font-semibold text-slate-100">
              {searching ? `Results for “${help.query.trim()}”` : page.label}
            </h3>
            {!searching && help.link.anchor && (
              <span className="truncate font-mono text-[11px] text-slate-500">› {help.link.anchor}</span>
            )}
            <span className="ml-auto text-[10px] text-slate-600">F1 · help for this view &nbsp;·&nbsp; Ctrl+Shift+/ · ask</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5" data-help-page={searching ? "search" : help.link.page}>
            {searching ? (
              <SearchResults query={help.query} onOpen={(link) => { help.setQuery(""); help.navigate(link); }} />
            ) : (
              <Page anchor={help.link.anchor} />
            )}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
