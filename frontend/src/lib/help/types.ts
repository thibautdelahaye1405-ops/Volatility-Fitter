// Help Center contracts (HELP CENTER ARC, H1) — the data shapes every help
// corpus module fills in (lib/help/*), the pages render and the search index
// ranks. PURE TYPES: no React, no runtime imports, so the content modules and
// their vitest locks stay dependency-free.
//
// Content convention (all corpora): `summary` is ONE plain sentence in the
// imperative desk voice; `details` and `example` are Markdown rendered by
// lib/help/markdown.tsx. Two link schemes are understood inside Markdown:
//   [label](help:<page>[:<anchor>])   deep link inside the Help Center
//                                      (e.g. help:settings:gridXNodes, help:guides:graph)
//   [label](cmd:<command.id>[?arg])   an action button that runs a registry command
// Ordinary http(s) links open in a new tab.

import type { Activity } from "../../state/workbenchPersist";

/** Pages of the Help Center nav (order defined in lib/help/pages.ts). */
export type HelpPageId =
  | "welcome"
  | "guides"
  | "commands"
  | "settings"
  | "shortcuts"
  | "glossary"
  | "tips"
  | "docs"
  | "ask"
  | "whatsnew";

/** A parsed deep link: the page plus an optional anchor (an entry id). */
export interface HelpLink {
  page: HelpPageId;
  anchor?: string;
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/** Documentation of one registry command (lib/commands.ts) or one dynamic
 *  prefix (DYNAMIC.*). Locked complete by commandDocs.test.ts. */
export interface CommandDoc {
  /** Registry id ("calibrate.both") or a DYNAMIC prefix ("universe.load:"). */
  id: string;
  /** One sentence: what the command does. */
  summary: string;
  /** Markdown: what happens, side effects, where the result shows up. */
  details: string;
  /** Markdown: one concrete scenario ("You fetched SPY at 14:30 …"). */
  example: string;
  /** Plain text: when the row is enabled (omit = always). */
  enabledWhen?: string;
  /** Guide page that covers the surrounding workflow. */
  guide?: GuideId;
  /** Related command ids or help links ("help:settings:autoCalibrate"). */
  related?: string[];
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

/** The three backend settings models (volfit/api/schemas*.py). */
export type SettingsModel = "fit" | "options" | "market";

/** The Options-dialog section rail ids (views/OptionsViewer.tsx SECTIONS),
 *  plus "market" (Forwards lens dividend editor) for MarketSettings. */
export type SettingsSectionId =
  | "opt-parametric"
  | "opt-localvol"
  | "opt-calibration"
  | "opt-prior"
  | "opt-filter"
  | "opt-events"
  | "opt-graph"
  | "opt-workflow"
  | "opt-dynamics"
  | "market";

/** Which cache / version a field bumps when it changes (the invalidation
 *  discipline of Docs/handoff/SETTINGS_REFERENCE.md §4). */
export type CacheEffect =
  /** FitSettings: folded into every fit-cache key — all views refit. */
  | "fit-version"
  /** Calibration-affecting OptionsSettings field — parametric refits. */
  | "options-version"
  /** LV-only: folds into the affine key, never invalidates parametric fits. */
  | "lv-affine-key"
  /** Observation-filter overlay: lightweight filter version only. */
  | "filter-version"
  /** Per-ticker market inputs: that ticker's version only. */
  | "per-ticker-version"
  /** Pure workflow / UI gate — never busts a cache. */
  | "workflow-gate"
  /** Display / report policy — never touches a fit. */
  | "display-only";

/** Documentation of one settings field, keyed by its wire name. Machine
 *  facts (type, default, range, enum) come from settingsSchema.json — never
 *  hand-copied here. Locked complete by settingsDocs.test.ts. */
export interface SettingDoc {
  /** Wire name ("gridXNodes"). */
  key: string;
  model: SettingsModel;
  section: SettingsSectionId;
  /** The label the Options dialog shows (or a readable name when the field
   *  is not surfaced in the dialog). */
  label: string;
  /** Unit of the value ("vol pt", "bp", "minutes", "%", "count" …). */
  unit?: string;
  /** One sentence: what the knob controls. */
  summary: string;
  /** Markdown: what it does, why the default is what it is, what you see
   *  when you move it. */
  details: string;
  /** Markdown: one concrete value and the observable effect. */
  example: string;
  /** Plain text: read only while … (omit = always active). */
  activation?: string;
  cacheEffect: CacheEffect;
  /** Rendered in the Options dialog / a lens panel (false = API + palette only). */
  surfaced: boolean;
  /** Related setting keys or help links. */
  related?: string[];
  /** Documentation ids from docsCatalog.ts that derive the knob. */
  docs?: string[];
}

/** One field of the GENERATED settings schema (settingsSchema.json). */
export interface SchemaField {
  name: string;
  /** Simplified type label: "bool" | "int" | "float" | "str" | "enum" | "list" | "dict" | "object". */
  type: string;
  /** JSON-encoded default (already a JSON value). */
  default: unknown;
  min?: number;
  max?: number;
  /** Whether min / max are exclusive bounds. */
  exclusiveMin?: boolean;
  exclusiveMax?: boolean;
  /** Literal choices for enum fields. */
  enum?: string[];
  /** The field accepts null. */
  optional?: boolean;
}

export interface SchemaModel {
  title: string;
  fields: SchemaField[];
}

export interface SettingsSchema {
  generatedAt: string;
  models: Record<SettingsModel, SchemaModel>;
}

// ---------------------------------------------------------------------------
// Glossary · tips · guides · tour · what's new · docs
// ---------------------------------------------------------------------------

export interface GlossaryEntry {
  /** Kebab-case id ("lit-dark"). */
  id: string;
  term: string;
  /** One sentence. */
  short: string;
  /** Markdown, 2–6 sentences. */
  long: string;
  /** Related glossary ids. */
  related?: string[];
  /** Documentation ids (docsCatalog.ts) and help links. */
  links?: string[];
}

export interface TipAction {
  /** Registry command id. */
  command: string;
  arg?: string;
  /** Button label ("Try it: open the palette"). */
  label: string;
}

export interface Tip {
  id: string;
  title: string;
  /** Markdown, 1–3 sentences. */
  body: string;
  /** The lens it belongs to, or "shell" for workbench-wide tips. */
  scope: Activity | "shell";
  level: "basic" | "pro";
  action?: TipAction;
}

/** Guide pages (lib/help/guides/*). */
export type GuideId =
  | "getting-started"
  | "workbench"
  | "universe"
  | "data-sources"
  | "workflow"
  | "graph"
  | "forwards"
  | "parametric"
  | "localvol"
  | "quality"
  | "options"
  | "priors"
  | "filter"
  | "files";

export interface GuidePage {
  id: GuideId;
  title: string;
  /** The lens this guide documents (F1 maps the active lens here). */
  lens?: Activity;
  /** One sentence shown in the guides index. */
  summary: string;
  /** Markdown body (## sections; help:/cmd: links welcome). */
  body: string;
  related?: string[];
}

/** Spotlight anchors: `data-tour="<id>"` attributes on the live shell. */
export type TourAnchor =
  | "brand"
  | "menu.file"
  | "menu.options"
  | "menu.universe"
  | "menu.help"
  | "center"
  | "menu.view"
  | "menu.layout"
  | "activity"
  | "nodes"
  | "tabs"
  | "main"
  | "status";

export interface TourStep {
  id: string;
  anchor: TourAnchor;
  title: string;
  /** Markdown, 2–4 sentences. */
  body: string;
  /** Preferred side of the spotlight for the card. */
  placement?: "right" | "left" | "top" | "bottom";
  /** Optional "Try it" action. */
  action?: TipAction;
}

export interface WhatsNewEntry {
  /** ISO date of the change. */
  date: string;
  title: string;
  /** Markdown bullets (one string each). */
  items: string[];
}

export type DocKind = "note" | "supplement" | "paper" | "book" | "handoff" | "guide";

/** One document of the shipped documentation set (Docs/, Papers/). */
export interface DocEntry {
  /** Stable id ("14_graph_messages"). */
  id: string;
  title: string;
  kind: DocKind;
  /** Note series number ("14") when applicable. */
  number?: string;
  /** Short topic tag ("Graph", "LQD", "Local vol" …). */
  topic: string;
  /** 1–3 sentences. */
  abstract: string;
  /** Markdown edition served by GET /help/docs/{id} (root + file name). */
  markdown?: { root: string; name: string };
  /** PDF served by GET /help/files/{root}/{name}. */
  pdf?: { root: string; name: string };
  related?: string[];
}
