// View tab: display / UX preferences that are purely client-side — colour
// scheme, contrast, brightness and the expiry-label format. Kept separate from
// the (quant-heavy) Options tab so the meta-parameters stay uncluttered.
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

export default function ViewSettingsViewer() {
  const { scheme, contrast, brightness, setScheme, setContrast, setBrightness, reset } =
    useViewSettings();
  const { format, setFormat } = useExpiryFormat();

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4 overflow-y-auto p-4">
      {/* Colour scheme */}
      <div className={card}>
        <h3 className={sectionTitle}>Colour scheme</h3>
        <p className={sectionHint}>Re-skins the whole app instantly; persisted on this device.</p>
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
        <button
          onClick={reset}
          className="mt-3 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] text-slate-400 transition-colors hover:text-slate-200"
        >
          Reset to defaults
        </button>
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

      {/* Live preview strip so the scheme/contrast effect is obvious. */}
      <div className={card}>
        <h3 className={sectionTitle}>Preview</h3>
        <div className="mt-2 flex flex-col gap-1 rounded-lg border border-slate-800 bg-surface-800 p-3">
          <div className="text-sm font-semibold text-slate-100">Heading text</div>
          <div className="text-xs text-slate-200">Body text — primary readout</div>
          <div className="text-xs text-slate-400">Label / secondary text</div>
          <div className="text-[11px] text-slate-500">Hint / tertiary text</div>
          <div className="mt-1 flex gap-2">
            <span className="rounded bg-accent-600/25 px-2 py-0.5 text-[11px] text-accent-400">accent chip</span>
            <span className="rounded border border-slate-700 px-2 py-0.5 font-mono text-[11px] text-slate-300">
              mono 21.87%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
