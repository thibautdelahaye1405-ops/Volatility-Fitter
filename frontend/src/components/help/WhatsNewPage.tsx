// Help ▸ What's new (HELP CENTER ARC, H4): release notes in user language
// (lib/help/whatsNew), newest first; a deep link `whatsnew:<date>` highlights
// that entry.
import { WHATS_NEW } from "../../lib/help/whatsNew";
import { Markdown } from "../../lib/help/markdown";
import { useHelpLinks } from "./useHelpLinks";
import type { HelpPageProps } from "./HelpCenter";

export default function WhatsNewPage({ anchor }: HelpPageProps) {
  const links = useHelpLinks();
  return (
    <ol className="relative mx-auto flex max-w-3xl flex-col gap-4 border-l border-slate-800 pl-5">
      {WHATS_NEW.map((w, i) => {
        const hit = anchor === w.date;
        return (
          <li key={`${w.date}-${w.title}`} id={`help-new-${w.date}`} className="relative">
            <span className={["absolute -left-[1.55rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface-900", i === 0 || hit ? "bg-accent-400" : "bg-slate-600"].join(" ")} />
            <div className={["rounded-lg border p-3", hit ? "border-accent-500/60 bg-accent-500/5" : "border-slate-800 bg-surface-800/40"].join(" ")}>
              <div className="flex flex-wrap items-baseline gap-2">
                <h3 className="text-[13px] font-semibold text-slate-100">{w.title}</h3>
                <span className="font-mono text-[10px] text-slate-500">{w.date}</span>
                {i === 0 && <span className="rounded border border-accent-500/40 bg-accent-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-accent-300">latest</span>}
              </div>
              <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-slate-300">
                {w.items.map((it, j) => <li key={j}><Markdown source={it} handlers={links} className="inline [&_p]:mt-0 [&_p]:inline" /></li>)}
              </ul>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
