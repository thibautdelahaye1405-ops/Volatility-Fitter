// Relationship-confidence slider (GRAPH ERGONOMICS ARC, E4/E5): ONE control,
// two lenses — the stored/wire value is always the conditional precision p
// (1/vol², decimal vol); the slider moves in the U1 default lens, the
// relationship uncertainty σ = 1/√p in VOL POINTS (log scale, tight on the
// right so "more confident" reads as a push to the right), and the readout
// switches to the raw precision behind the pane's units toggle.
import Slider from "../Slider";
import { precisionFromSigmaPts, sigmaPtsFromPrecision } from "../../lib/precisionUnits";

/** Slider span in σ vol points (0.25 tight … 10 wide) — the same anchors the
 *  canvas arrow width uses (lib/edgeStyle), so the slider and the arrow agree. */
export const SIGMA_MIN_PTS = 0.25;
export const SIGMA_MAX_PTS = 10;

interface SigmaSliderProps {
  label: React.ReactNode;
  /** The stored precision p (1/vol²). */
  precision: number;
  /** Raw-precision readout (the pane's units toggle). */
  raw: boolean;
  onChange: (precision: number) => void;
  title?: string;
  onReset?: () => void;
  resetTitle?: string;
  disabled?: boolean;
  muted?: boolean;
  badge?: React.ReactNode;
  testId?: string;
}

export default function SigmaSlider({
  label,
  precision,
  raw,
  onChange,
  title,
  onReset,
  resetTitle,
  disabled,
  muted,
  badge,
  testId,
}: SigmaSliderProps) {
  // The slider value is "confidence" = 1/σ so that right = more confident;
  // we keep the range in σ but invert via the value mapping below.
  const sigma = sigmaPtsFromPrecision(precision);
  const conf = Number.isFinite(sigma) ? 1 / sigma : 1 / SIGMA_MAX_PTS;
  return (
    <Slider
      label={label}
      title={title}
      value={conf}
      min={1 / SIGMA_MAX_PTS}
      max={1 / SIGMA_MIN_PTS}
      log
      format={() =>
        raw
          ? `p ${Math.round(precision)}`
          : `σ ${Number.isFinite(sigma) ? sigma.toFixed(2) : "∞"} pt`
      }
      onChange={(c) => onChange(precisionFromSigmaPts(1 / c))}
      onReset={onReset}
      resetTitle={resetTitle}
      disabled={disabled}
      muted={muted}
      badge={badge}
      testId={testId}
    />
  );
}
