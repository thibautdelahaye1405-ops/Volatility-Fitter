// Help ▸ Ask @Vol-Fitter (HELP CENTER ARC, H4): a question box with two
// tiers. Tier 0 — LOCAL: the help corpus ranked by lib/help/search, answered
// instantly and offline as cards with actions (open the entry, run the
// command). Tier 1 — CLAUDE: when the server reports `tier: "claude"`
// (GET /help/ask/status — an Anthropic key configured on the backend), the
// same top cards ground a streamed answer from POST /help/ask (SSE deltas);
// the panel says which tier answered. Conversation history stays in this
// panel (not persisted). Ctrl+Shift+/ opens it.
import { useEffect, useMemo, useRef, useState } from "react";
import { Send, Sparkles } from "lucide-react";
import { API_BASE_URL, api } from "../../state/api";
import { useWorkflowContext } from "../../state/workflowContext";
import { useWorkbench } from "../../state/workbench";
import { useHelp } from "../../state/help";
import { searchHelp } from "../../lib/help/search";
import type { SearchHit } from "../../lib/help/search";
import { parseHelpLink } from "../../lib/help/pages";
import { Markdown } from "../../lib/help/markdown";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, GHOST_BTN, KindChip } from "./HelpCards";

interface AskStatus { tier: "claude" | "local"; configured: boolean; sdkInstalled: boolean; model: string | null }
interface Turn { role: "user" | "assistant"; text: string; hits?: SearchHit[]; tier?: "local" | "claude"; model?: string | null; error?: string }

const SUGGESTIONS = [
  "How do I calibrate only the local-vol surface?",
  "What does the haircut fit target do?",
  "Why is a node marked stale?",
  "How do I light a dark node?",
  "What is the difference between precision messages and smooth field?",
  "How do I save the workspace to a file?",
];

async function streamAsk(body: unknown, onDelta: (t: string) => void): Promise<{ tier: "claude"; model: string | null; error?: string }> {
  const res = await fetch(`${API_BASE_URL}/help/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let model: string | null = null;
  let error: string | undefined;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        const ev = JSON.parse(line.slice(5).trim()) as { type: string; text?: string; model?: string; message?: string };
        if (ev.type === "delta" && ev.text) onDelta(ev.text);
        else if (ev.type === "done") model = ev.model ?? null;
        else if (ev.type === "error") error = ev.message ?? "assistant error";
      } catch { /* a partial frame — wait for more */ }
    }
  }
  return { tier: "claude", model, error };
}

export default function AskPanel() {
  const { live } = useWorkflowContext();
  const wb = useWorkbench();
  const help = useHelp();
  const links = useHelpLinks();
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!live) { setStatus(null); return; }
    let cancelled = false;
    api.get<AskStatus>("/help/ask/status").then((s) => { if (!cancelled) setStatus(s); }).catch(() => { if (!cancelled) setStatus(null); });
    return () => { cancelled = true; };
  }, [live]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [turns]);

  const claude = live && status?.tier === "claude";
  const tierLabel = useMemo(() => claude ? `Claude (${status?.model ?? "configured"}) grounded on the help corpus` : "local retrieval over the help corpus", [claude, status]);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setQ("");
    const hits = searchHelp(text, { limit: 6 });
    const local: Turn = { role: "assistant", text: "", hits, tier: "local" };
    setTurns((t) => [...t, { role: "user", text }, local]);
    if (!claude) return;
    setBusy(true);
    const idx = turns.length + 1;
    const body = {
      question: text,
      cards: hits.map((h) => ({ id: h.card.id, kind: h.card.kind, title: h.card.title, text: h.card.text.slice(0, 4000), link: h.card.link })),
      context: { lens: wb.activity, ticker: wb.activeTab?.ticker, expiry: wb.activeTab?.expiry, page: help.link.page },
      history: turns.filter((t) => t.role === "user" || t.text).slice(-8).map((t) => ({ role: t.role, text: t.text })),
    };
    try {
      const r = await streamAsk(body, (delta) => setTurns((all) => all.map((t, i) => (i === idx ? { ...t, text: t.text + delta, tier: "claude" } : t))));
      setTurns((all) => all.map((t, i) => (i === idx ? { ...t, tier: "claude", model: r.model, error: r.error } : t)));
    } catch (e: unknown) {
      setTurns((all) => all.map((t, i) => (i === idx ? { ...t, tier: "local", error: `Claude tier unavailable (${e instanceof Error ? e.message : String(e)}) — showing the local answer` } : t)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col gap-3">
      <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-surface-800/40 px-3 py-2 text-[11px] text-slate-400">
        <Sparkles size={13} className={claude ? "text-accent-400" : "text-slate-500"} />
        <span>Answers come from <span className="text-slate-200">{tierLabel}</span>.</span>
        {!claude && <span className="text-slate-500">— set <code className="font-mono">VOLFIT_ANTHROPIC_KEY</code> on the server to enable the Claude tier (the browser never sees the key).</span>}
      </div>

      <div className="flex min-h-[14rem] flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {turns.length === 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-slate-500">Ask in your own words. Try:</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => void ask(s)} className={GHOST_BTN}>{s}</button>)}
            </div>
          </div>
        )}
        {turns.map((t, i) => t.role === "user" ? (
          <div key={i} className="self-end rounded-lg border border-accent-600/40 bg-accent-600/10 px-3 py-2 text-xs text-slate-100">{t.text}</div>
        ) : (
          <div key={i} className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-surface-800/40 p-3">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
              <span>{t.tier === "claude" ? `Claude${t.model ? ` · ${t.model}` : ""}` : "local"}</span>
              {busy && i === turns.length - 1 && t.tier === "claude" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-400" />}
              {t.error && <span className="normal-case tracking-normal text-amber-400">{t.error}</span>}
            </div>
            {t.text && <Markdown source={t.text} handlers={links} />}
            {t.hits && t.hits.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                {!t.text && <p className="text-xs text-slate-400">The closest entries in the help corpus:</p>}
                {t.hits.map((h) => {
                  const link = parseHelpLink(h.card.link);
                  return (
                    <div key={h.card.id} data-ask-hit className="flex items-start gap-2 rounded-md border border-slate-800/80 bg-surface-950/60 p-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2"><span className="text-xs font-semibold text-slate-100">{h.card.title}</span><KindChip kind={h.card.kind} /></div>
                        <p className="mt-0.5 text-[11px] text-slate-400">{h.snippet}</p>
                      </div>
                      <div className="flex shrink-0 flex-col gap-1">
                        {link && <button onClick={() => help.navigate(link)} className={GHOST_BTN}>Open</button>}
                        {h.card.command && <button onClick={() => links.run(h.card.command!, h.card.commandArg)} className={ACTION_BTN}>▶ Run</button>}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              !t.text && <p className="text-xs text-slate-400">Nothing in the help corpus matches that wording. Try the <button onClick={() => help.navigate({ page: "commands" })} className="text-accent-400 underline">Command reference</button>, the <button onClick={() => help.navigate({ page: "settings" })} className="text-accent-400 underline">Settings reference</button> or <button onClick={() => help.navigate({ page: "docs" })} className="text-accent-400 underline">Documentation</button>.</p>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); void ask(q); }} className="flex items-center gap-2 rounded-lg border border-slate-700 bg-surface-950 px-3 py-2 focus-within:border-accent-600/60">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask @Vol-Fitter — e.g. “how do I exclude a quote from the fit?”" aria-label="Ask a question" autoFocus
          className="min-w-0 flex-1 bg-transparent text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none" />
        <button type="submit" disabled={!q.trim() || busy} className="rounded-md border border-accent-600/60 bg-accent-600/20 p-1.5 text-accent-300 hover:bg-accent-600/30 disabled:cursor-not-allowed disabled:opacity-40" aria-label="Ask">
          <Send size={13} />
        </button>
        {turns.length > 0 && <button type="button" onClick={() => setTurns([])} className={GHOST_BTN}>Clear</button>}
      </form>
    </div>
  );
}
