// View tab: display / UX preferences that are purely client-side — colour
// scheme, contrast, brightness and the expiry-label format. Kept separate from
// the (quant-heavy) Options tab so the meta-parameters stay uncluttered.
import { useState } from "react";
import {
  BRIGHTNESS_RANGE,
  COLOR_SCHEMES,
  CONTRAST_RANGE,
  useViewSettings,
} from "../state/viewSettings";
import { useExpiryFormat } from "../state/expiryFormat";
import { EXPIRY_FORMATS, formatExpiry } from "../lib/expiryFormat";

const card = "rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30";
const sectionTitle = "mb-1 text-sm font-semibold text-slate-100";
const sectionHint = "mb-3 text-[11px] text-slate-500";

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center gap-3">
      <span className="w-20 text-xs text-slate-400">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 flex-1 cursor-pointer accent-accent-500"
      />
      <span className="w-12 text-right font-mono text-[11px] text-slate-300">
        {Math.round(value * 100)}%
      </span>
    </label>
  );
}

/** Static miniature smile chart for the Preview card: dashed prior, accent fit
 *  curve and red quote bid–ask bars — the exact colours the real SmileChart
 *  uses, so the scheme choice is judged on realistic content. Not interactive. */
function MiniSmile() {
  // Quote columns: (x, y-on-fit) with a ±5px bid–ask beam around the mid.
  const quotes: [number, number][] = [
    [24, 32], [54, 45], [84, 59], [114, 72], [144, 78], [174, 73], [204, 63],
  ];
  return (
    <svg width={230} height={112} aria-hidden className="shrink-0">
      {/* Frame + ATM gridline */}
      <line x1={10} y1={98} x2={222} y2={98} className="stroke-slate-700" />
      <line x1={130} y1={12} x2={130} y2={98} strokeDasharray="2 4" className="stroke-slate-700" />
      {/* Prior (dashed) and current fit (accent) */}
      <path
        d="M10,31 C45,48 80,68 120,80 C150,88 190,76 220,66"
        fill="none" strokeDasharray="4 4" strokeWidth={1.2} className="stroke-slate-500"
      />
      <path
        d="M10,25 C45,42 80,62 120,74 C150,82 190,70 220,60"
        fill="none" stroke="var(--color-accent-500)" strokeWidth={1.8}
      />
      {/* Quotes: bid–ask beams with caps + mid ticks (SmileChart red) */}
      {quotes.map(([x, y]) => (
        <g key={x} stroke="rgb(248 113 113 / 0.95)" strokeWidth={1.2}>
          <line x1={x} x2={x} y1={y - 5} y2={y + 5} />
          <line x1={x - 3} x2={x + 3} y1={y - 5} y2={y - 5} />
          <line x1={x - 3} x2={x + 3} y1={y + 5} y2={y + 5} />
          <line x1={x - 2.5} x2={x + 2.5} y1={y} y2={y} strokeWidth={2} />
        </g>
      ))}
      {/* Axis labels */}
      <text x={12} y={108} className="fill-slate-500 font-mono text-[8px]">-0.4</text>
      <text x={127} y={108} className="fill-slate-500 font-mono text-[8px]">0</text>
      <text x={210} y={108} className="fill-slate-500 font-mono text-[8px]">0.4</text>
      <text x={12} y={18} className="fill-slate-500 font-mono text-[8px]">σ</text>
    </svg>
  );
}

export default function ViewSettingsViewer() {
  const {
    scheme, contrast, brightness,
    setScheme, setContrast, setBrightness,
    reset, saveDefault, dirty,
  } = useViewSettings();
  const {
    format, setFormat,
    saveDefault: saveExpiry, dirty: expiryDirty,
  } = useExpiryFormat();

  const [flash, setFlash] = useState(false);
  const anyDirty = dirty || expiryDirty;

  // Save the whole View tab (look + expiry format) as this device's default.
  const saveAll = () => {
    saveDefault();
    saveExpiry();
    setFlash(true);
    setTimeout(() => setFlash(false), 1200);
  };

  // Revert the look AND the expiry format to the built-in defaults (live only;
  // press Save to make the reset stick across a reload).
  const resetAll = () => {
    reset();
    setFormat("dmy");
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4 overflow-y-auto p-4">
      {/* Colour scheme */}
      <div className={card}>
        <h3 className={sectionTitle}>Colour scheme</h3>
        <p className={sectionHint}>Re-skins the whole app instantly; "Save as default" persists it on this device.</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {COLOR_SCHEMES.map((s) => (
            <button
              key={s.id}
              onClick={() => setScheme(s.id)}
              title={s.hint}
              className={[
                "rounded-lg border px-3 py-2 text-left transition-colors",
                s.id === scheme
                  ? "border-accent-600/60 bg-accent-600/15"
                  : "border-slate-700 bg-surface-800 hover:border-slate-600",
              ].join(" ")}
            >
              <div
                className={[
                  "text-xs font-semibold",
                  s.id === scheme ? "text-accent-400" : "text-slate-200",
                ].join(" ")}
              >
                {s.label}
              </div>
              <div className="mt-0.5 text-[10px] text-slate-500">{s.hint}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Contrast / brightness */}
      <div className={card}>
        <h3 className={sectionTitle}>Contrast &amp; brightness</h3>
        <p className={sectionHint}>
          Global display correction (applied as a CSS filter on the app canvas).
        </p>
        <div className="flex flex-col gap-3">
          <Slider
            label="Contrast"
            value={contrast}
            min={CONTRAST_RANGE.min}
            max={CONTRAST_RANGE.max}
            step={CONTRAST_RANGE.step}
            onChange={setContrast}
          />
          <Slider
            label="Brightness"
            value={brightness}
            min={BRIGHTNESS_RANGE.min}
            max={BRIGHTNESS_RANGE.max}
            step={BRIGHTNESS_RANGE.step}
            onChange={setBrightness}
          />
        </div>
      </div>

      {/* Expiry label format (also surfaced in Options + the chart headers). */}
      <div className={card}>
        <h3 className={sectionTitle}>Expiry label format</h3>
        <p className={sectionHint}>Applied across every view; also a ↻ toggle in the chart headers.</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {EXPIRY_FORMATS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFormat(f.id)}
              className={[
                "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors",
                f.id === format
                  ? "border-accent-600/60 bg-accent-600/15 text-accent-400"
                  : "border-slate-700 bg-surface-800 text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {f.label}
            </button>
          ))}
          <span className="ml-2 font-mono text-[11px] text-slate-500">
            e.g. {formatExpiry("2026-12-18", 1.25, format)}
          </span>
        </div>
      </div>

      {/* Live preview: a NON-INTERACTIVE specimen (mini smile chart + text
          tiers + palette) so the scheme / contrast effect is obvious. */}
      <div className={card}>
        <h3 className={sectionTitle}>Preview</h3>
        <p className={sectionHint}>
          Live sample of the current scheme — how a chart, the text tiers and the
          palette will render. Nothing here is a setting.
        </p>
        <div className="flex flex-wrap items-center gap-6 rounded-lg border border-slate-800 bg-surface-800 p-3">
          <MiniSmile />
          <div className="flex min-w-44 flex-col gap-1">
            <div className="text-sm font-semibold text-slate-100">Heading text</div>
            <div className="text-xs text-slate-200">Body text — primary readout</div>
            <div className="text-xs text-slate-400">Label / secondary text</div>
            <div className="text-[11px] text-slate-500">Hint / tertiary text</div>
            <div className="mt-1 flex gap-2">
              <span className="rounded bg-accent-600/25 px-2 py-0.5 text-[11px] text-accent-400">accent</span>
              <span className="rounded border border-slate-700 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                mono 21.87%
              </span>
            </div>
            {/* Palette dots: surface stack · accent · status colours */}
            <div className="mt-2 flex items-center gap-1.5">
              {[
                "bg-surface-950", "bg-surface-900", "bg-surface-700",
                "bg-accent-500", "bg-emerald-500", "bg-amber-400", "bg-rose-500",
              ].map((c) => (
                <span key={c} className={`h-3 w-3 rounded-full border border-slate-700/60 ${c}`} />
              ))}
              <span className="ml-1 text-[10px] text-slate-500">palette</span>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky Save/Reset bar — mirrors the Options tab. Changes preview live;
          Save persists the whole View tab (look + expiry format) on this device. */}
      <div className="sticky bottom-0 mt-auto flex items-center gap-3 border-t border-slate-800 bg-surface-950/80 py-3 backdrop-blur">
        <span className="text-[11px] text-slate-500">
          {anyDirty ? "Unsaved view changes" : flash ? "Saved as default ✓" : "View saved"}
        </span>
        <button
          onClick={resetAll}
          title="Revert the scheme, contrast/brightness and expiry format to the built-in defaults"
          className="ml-auto rounded-md border border-slate-700 bg-surface-800 px-3 py-1.5 text-[11px] font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
        >
          Reset to defaults
        </button>
        <button
          onClick={saveAll}
          disabled={!anyDirty && !flash}
          title="Save the current view as this device's default (restored on the next app restart)"
          className={[
            "rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            flash
              ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
              : anyDirty
                ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
                : "cursor-not-allowed border-slate-700 text-slate-600",
          ].join(" ")}
        >
          {flash ? "Saved ✓" : "Save as default"}
        </button>
      </div>
    </div>
  );
}
