// Help ▸ Settings reference (HELP CENTER ARC, H4): EVERY field of the three
// settings models, grouped by the Options-dialog section it lives in. Machine
// facts (type · default · range · choices) come from the generated schema
// (settingsSchema.json, refreshed live from GET /help/settings-schema so a
// persisted desk default shows as the running default); prose from
// lib/help/settingsDocs (summary · details · example · activation · cache
// effect). "Open in Options" jumps to the section; a deep link
// `settings:<key>` scrolls to and flashes the field. Locked complete by
// settingsDocs.test.ts + the backend drift lock.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../state/api";
import { useWorkflowContext } from "../../state/workflowContext";
import { useWorkbench } from "../../state/workbench";
import {
  SETTINGS_SCHEMA, SETTINGS_SECTIONS, SETTING_DOCS, docsBySection, formatDefault, formatRange, schemaField,
} from "../../lib/help/settingsDocs";
import type { CacheEffect, SchemaField, SettingDoc, SettingsSchema } from "../../lib/help/types";
import { Markdown } from "../../lib/help/markdown";
import { useHelpLinks } from "./useHelpLinks";
import { ACTION_BTN, EntryCard, GHOST_BTN, useAnchorFlash } from "./HelpCards";
import type { HelpPageProps } from "./HelpCenter";

const domId = (key: string) => `help-set-${key}`;

const CACHE_LABEL: Record<CacheEffect, { label: string; tone: string; hint: string }> = {
  "fit-version": { label: "refits everything", tone: "text-rose-300 border-rose-500/40 bg-rose-500/10", hint: "Folded into every fit-cache key: all views refit." },
  "options-version": { label: "refits parametric", tone: "text-orange-300 border-orange-500/40 bg-orange-500/10", hint: "Calibration-affecting: parametric fits refit on the next calibrate." },
  "lv-affine-key": { label: "LV only", tone: "text-violet-300 border-violet-500/40 bg-violet-500/10", hint: "Folds into the local-vol key only — parametric fits stay warm." },
  "filter-version": { label: "filter only", tone: "text-teal-300 border-teal-500/40 bg-teal-500/10", hint: "Bumps the lightweight observation-filter version." },
  "per-ticker-version": { label: "that ticker", tone: "text-amber-300 border-amber-500/40 bg-amber-500/10", hint: "Bumps this ticker's version only — never the universe." },
  "workflow-gate": { label: "workflow gate", tone: "text-sky-300 border-sky-500/40 bg-sky-500/10", hint: "Pure workflow / UI gate — never busts a cache." },
  "display-only": { label: "display only", tone: "text-slate-300 border-slate-500/40 bg-slate-500/10", hint: "Display / report policy — never touches a fit." },
};

function Facts({ field, live }: { field: SchemaField | undefined; live: SchemaField | undefined }) {
  if (!field) return <span className="text-[10px] text-rose-400">not in schema</span>;
  const range = formatRange(field);
  const bundled = formatDefault(field);
  const running = live ? formatDefault(live) : null;
  const differs = running !== null && running !== bundled;
  return (
    <dl className="grid grid-cols-[4.5rem_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]">
      <dt className="text-slate-500">type</dt><dd className="text-slate-300">{field.type}{field.optional ? " · nullable" : ""}</dd>
      <dt className="text-slate-500">default</dt>
      <dd className="text-slate-300">
        {bundled}
        {differs && <span className="ml-1 rounded border border-amber-500/40 bg-amber-500/10 px-1 text-amber-300" title="The running server persisted a different default (Options ▸ Save as default)">running: {running}</span>}
      </dd>
      {range && <><dt className="text-slate-500">range</dt><dd className="text-slate-300">{range}</dd></>}
      {field.enum && <><dt className="text-slate-500">choices</dt><dd className="text-slate-300">{field.enum.join(" · ")}</dd></>}
    </dl>
  );
}

function SettingCard({ doc, liveSchema, highlighted }: { doc: SettingDoc; liveSchema: SettingsSchema | null; highlighted: boolean }) {
  const links = useHelpLinks();
  const wb = useWorkbench();
  const field = schemaField(doc.model, doc.key);
  const live = liveSchema?.models[doc.model]?.fields.find((f) => f.name === doc.key);
  const cache = CACHE_LABEL[doc.cacheEffect];
  const openOptions = () => {
    wb.openDialog("options");
    window.setTimeout(() => document.getElementById(doc.section)?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
  };
  return (
    <EntryCard
      id={domId(doc.key)}
      kind="setting"
      kindLabel={doc.model}
      title={<>{doc.label} <span className="ml-1 font-mono text-[11px] font-normal text-slate-500">{doc.key}</span></>}
      meta={doc.unit ? `unit: ${doc.unit}` : undefined}
      summary={doc.summary}
      highlighted={highlighted}
      actions={<>
        {doc.section !== "market" && <button onClick={openOptions} className={ACTION_BTN}>Open in Options</button>}
        {doc.section === "market" && <button onClick={() => links.run("lens.forwards")} className={ACTION_BTN}>Open the Forwards lens</button>}
        {doc.related?.map((r) => (
          <button key={r} onClick={() => links.open(r.startsWith("help:") ? r : `help:settings:${r}`)} className={GHOST_BTN}>{r.replace(/^help:/, "")}</button>
        ))}
        {doc.docs?.map((d) => <button key={d} onClick={() => links.open(`help:docs:${d}`)} className={GHOST_BTN}>📄 {d}</button>)}
      </>}
    >
      <div className="mt-2 grid gap-3 md:grid-cols-[1fr_17rem]">
        <div>
          <Markdown source={doc.details} handlers={links} />
          <div className="mt-2 rounded-md border border-slate-800/80 bg-surface-950/60 p-2">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Example</div>
            <Markdown source={doc.example} handlers={links} />
          </div>
        </div>
        <div className="flex flex-col gap-2 rounded-md border border-slate-800/80 bg-surface-950/60 p-2">
          <Facts field={field} live={live} />
          <div className="flex flex-wrap gap-1">
            <span className={["rounded border px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider", cache.tone].join(" ")} title={cache.hint}>{cache.label}</span>
            {!doc.surfaced && <span className="rounded border border-slate-600/50 px-1.5 py-px text-[9px] uppercase tracking-wider text-slate-400" title="No control in the Options dialog — set it through the API or a workspace file">API only</span>}
          </div>
          {doc.activation && <div className="text-[10px] text-slate-400"><span className="font-semibold text-slate-300">Read only while:</span> {doc.activation}</div>}
        </div>
      </div>
    </EntryCard>
  );
}

export default function SettingsReference({ anchor }: HelpPageProps) {
  const { live } = useWorkflowContext();
  const [filter, setFilter] = useState("");
  const [section, setSection] = useState<string>("all");
  const [liveSchema, setLiveSchema] = useState<SettingsSchema | null>(null);
  useAnchorFlash(anchor, useCallback((a: string) => domId(a), []));

  // The running server's schema (defaults may differ from the bundled JSON).
  useEffect(() => {
    if (!live) { setLiveSchema(null); return; }
    let cancelled = false;
    api.get<SettingsSchema>("/help/settings-schema").then((s) => { if (!cancelled) setLiveSchema(s); }).catch(() => { if (!cancelled) setLiveSchema(null); });
    return () => { cancelled = true; };
  }, [live]);

  // The anchored field's section is expanded regardless of the filter.
  useEffect(() => {
    if (!anchor) return;
    const d = SETTING_DOCS.find((x) => x.key === anchor);
    if (d) { setSection("all"); setFilter(""); }
  }, [anchor]);

  const q = filter.trim().toLowerCase();
  const visible = useMemo(() => {
    const secs = section === "all" ? SETTINGS_SECTIONS : SETTINGS_SECTIONS.filter((s) => s.id === section);
    return secs.map((s) => ({
      ...s,
      docs: docsBySection(s.id).filter((d) => !q || [d.key, d.label, d.summary, d.details, d.unit ?? ""].join(" ").toLowerCase().includes(q)),
    })).filter((s) => s.docs.length > 0);
  }, [section, q]);
  const total = SETTING_DOCS.length;
  const shown = visible.reduce((n, s) => n + s.docs.length, 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter settings"
          placeholder="Filter settings — key, label, unit, words from the explanation…"
          className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-surface-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-accent-600/60 focus:outline-none" />
        <span className="font-mono text-[10px] text-slate-500">{shown} / {total} · schema {SETTINGS_SCHEMA.generatedAt}{liveSchema ? " · live" : ""}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        <button onClick={() => setSection("all")} className={["rounded-full border px-2 py-0.5 text-[10px] font-medium", section === "all" ? "border-accent-500/60 bg-accent-500/15 text-accent-300" : "border-slate-700 text-slate-400 hover:text-slate-200"].join(" ")}>All</button>
        {SETTINGS_SECTIONS.map((s) => (
          <button key={s.id} onClick={() => setSection(s.id)} title={s.blurb}
            className={["rounded-full border px-2 py-0.5 text-[10px] font-medium", section === s.id ? "border-accent-500/60 bg-accent-500/15 text-accent-300" : "border-slate-700 text-slate-400 hover:text-slate-200"].join(" ")}>
            {s.label}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-slate-500">
        Cache badges say what a change invalidates: <em>refits everything</em> (Fit settings), <em>refits parametric</em>, <em>LV only</em>, <em>filter only</em>, <em>that ticker</em>, <em>workflow gate</em> or <em>display only</em> — a display field never touches a fit. "API only" marks fields with no dialog control.
      </p>
      {visible.map((s) => (
        <section key={s.id} className="flex flex-col gap-2">
          <h3 className="mt-2 flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {s.label} <span className="text-[10px] font-normal normal-case tracking-normal text-slate-600">{s.blurb} · {s.docs.length}</span>
          </h3>
          {s.docs.map((d) => <SettingCard key={d.key} doc={d} liveSchema={liveSchema} highlighted={anchor === d.key} />)}
        </section>
      ))}
      {visible.length === 0 && <p className="text-xs text-slate-500">No setting matches “{filter}”.</p>}
    </div>
  );
}
