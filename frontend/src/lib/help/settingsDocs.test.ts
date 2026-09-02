// Settings documentation locks (HELP CENTER ARC, H1): the corpus is complete
// against the GENERATED schema (every field of every model documented exactly
// once, no orphan docs), every entry carries the three prose parts with a
// one-sentence summary, sections and related keys resolve, and the two
// schema formatters render the known shapes.
import { describe, expect, it } from "vitest";
import {
  SETTINGS_MODELS,
  SETTINGS_SCHEMA,
  SETTINGS_SECTIONS,
  SETTING_DOCS,
  docsBySection,
  formatDefault,
  formatRange,
  schemaField,
  settingDoc,
} from "./settingsDocs";
import type { SettingsModel } from "./types";

/** "model.key" — the identity a doc must match in the schema. */
const qualified = (model: SettingsModel, key: string) => `${model}.${key}`;

const SCHEMA_KEYS: string[] = SETTINGS_MODELS.flatMap((m) =>
  SETTINGS_SCHEMA.models[m].fields.map((f) => qualified(m, f.name)),
);
const DOC_KEYS: string[] = SETTING_DOCS.map((d) => qualified(d.model, d.key));
const ALL_SETTING_KEYS = new Set(
  SETTINGS_MODELS.flatMap((m) => SETTINGS_SCHEMA.models[m].fields.map((f) => f.name)),
);

/** Loose one-sentence check: no sentence break (". " + capital) inside. */
const hasInnerSentenceBreak = (s: string) => /\.\s+[A-Z]/.test(s.trim());

describe("settings docs — completeness against settingsSchema.json", () => {
  it("documents every field of every model exactly once", () => {
    const counts = new Map<string, number>();
    for (const k of DOC_KEYS) counts.set(k, (counts.get(k) ?? 0) + 1);
    const missing = SCHEMA_KEYS.filter((k) => !counts.has(k));
    const duplicated = [...counts.entries()].filter(([, n]) => n > 1).map(([k]) => k);
    expect(missing, `schema fields without a SettingDoc: ${missing.join(", ")}`).toEqual([]);
    expect(duplicated, `SettingDoc keys documented more than once: ${duplicated.join(", ")}`).toEqual([]);
  });

  it("has no doc whose key is missing from the schema of its model", () => {
    const orphans = SETTING_DOCS.filter((d) => schemaField(d.model, d.key) === undefined).map(
      (d) => qualified(d.model, d.key),
    );
    expect(orphans, `SettingDocs with no schema field: ${orphans.join(", ")}`).toEqual([]);
  });

  it("resolves settingDoc() for every schema field", () => {
    for (const m of SETTINGS_MODELS) {
      for (const f of SETTINGS_SCHEMA.models[m].fields) {
        expect(settingDoc(f.name)?.key, `settingDoc(${f.name})`).toBe(f.name);
      }
    }
  });
});

describe("settings docs — prose contract", () => {
  it("has a non-empty summary, details and example on every entry", () => {
    const empty = SETTING_DOCS.filter(
      (d) => !d.summary.trim() || !d.details.trim() || !d.example.trim() || !d.label.trim(),
    ).map((d) => d.key);
    expect(empty, `entries with an empty label / summary / details / example: ${empty.join(", ")}`).toEqual([]);
  });

  it("keeps every summary to one sentence", () => {
    const multi = SETTING_DOCS.filter((d) => hasInnerSentenceBreak(d.summary)).map((d) => d.key);
    expect(multi, `summaries with more than one sentence: ${multi.join(", ")}`).toEqual([]);
  });

  it("files every entry under a known section", () => {
    const ids = new Set(SETTINGS_SECTIONS.map((s) => s.id));
    const bad = SETTING_DOCS.filter((d) => !ids.has(d.section)).map((d) => `${d.key}: ${d.section}`);
    expect(bad, `entries with an unknown section: ${bad.join(", ")}`).toEqual([]);
  });

  it("names an existing setting key in every non-help related entry", () => {
    const bad: string[] = [];
    for (const d of SETTING_DOCS) {
      for (const r of d.related ?? []) {
        if (r.startsWith("help:")) continue;
        if (!ALL_SETTING_KEYS.has(r)) bad.push(`${d.key} → ${r}`);
      }
    }
    expect(bad, `related entries naming no setting: ${bad.join(", ")}`).toEqual([]);
  });

  it("places the Market model in the market section and the others in an opt-* section", () => {
    const misfiled = SETTING_DOCS.filter((d) =>
      d.model === "market" ? d.section !== "market" : !d.section.startsWith("opt-"),
    ).map((d) => `${d.key}: ${d.model} / ${d.section}`);
    expect(misfiled).toEqual([]);
  });
});

describe("settings docs — sections", () => {
  it("lists every section once with a label and a blurb, and every section has docs", () => {
    const ids = SETTINGS_SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const s of SETTINGS_SECTIONS) {
      expect(s.label.trim()).not.toBe("");
      expect(s.blurb.trim()).not.toBe("");
      expect(docsBySection(s.id).length, `section ${s.id} has no docs`).toBeGreaterThan(0);
    }
  });

  it("keeps the Options-dialog order, Market last", () => {
    expect(SETTINGS_SECTIONS.map((s) => s.id)).toEqual([
      "opt-parametric",
      "opt-localvol",
      "opt-calibration",
      "opt-prior",
      "opt-filter",
      "opt-events",
      "opt-graph",
      "opt-workflow",
      "opt-dynamics",
      "market",
    ]);
  });
});

describe("settings docs — schema formatters", () => {
  it("formats inclusive ranges as 'lo – hi'", () => {
    const f = schemaField("fit", "nOrder");
    expect(f).toBeDefined();
    expect(formatRange(f!)).toBe("4 – 24");
  });

  it("formats an exclusive lower bound with interval notation", () => {
    const f = schemaField("options", "autoUpdateSeconds");
    expect(f).toBeDefined();
    expect(formatRange(f!)).toBe("(0, 86400]");
  });

  it("formats a lower-bound-only field and an unbounded one", () => {
    expect(formatRange(schemaField("options", "graphKappaScale")!)).toBe("> 0");
    expect(formatRange(schemaField("fit", "sviPenaltyWeight")!)).toBe("≥ 0");
    expect(formatRange(schemaField("market", "rate")!)).toBeNull();
  });

  it("formats defaults: bool → on/off, null → —, list joined, enum as value", () => {
    expect(formatDefault(schemaField("options", "enforceCalendar")!)).toBe("on");
    expect(formatDefault(schemaField("options", "asOfMismatchGate")!)).toBe("off");
    expect(formatDefault(schemaField("fit", "midAnchorTauRef")!)).toBe("—");
    expect(formatDefault(schemaField("options", "priorOperatorSet")!)).toBe("ATM, RR25, BF25, VarSwap");
    expect(formatDefault(schemaField("fit", "model")!)).toBe("lqd");
    expect(formatDefault(schemaField("options", "autoUpdateSeconds")!)).toBe("5");
  });
});
