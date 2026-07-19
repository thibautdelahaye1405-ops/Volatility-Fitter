// Relationship-uncertainty input (P5b U1): ONE input, two lenses.
//
// Default lens = σ_edge = 1/√p in VOL POINTS (what traders reason in); the
// raw conditional precision p (1/vol²) sits behind the caller's units toggle.
// The stored/wire value is ALWAYS the precision — this component only changes
// how it is read and typed.
import { precisionFromSigmaPts, sigmaPtsFromPrecision } from "../lib/precisionUnits";

interface PrecisionFieldProps {
  /** The stored conditional precision p (1/vol²) — the wire unit. */
  precision: number;
  /** True = show the raw precision; false (default lens) = σ_edge in pts. */
  raw: boolean;
  onChange: (precision: number) => void;
  className: string;
  disabled?: boolean;
  /** Tooltip per lens (callers phrase the taxonomy + provenance). */
  titleSigma: string;
  titleRaw: string;
}

export default function PrecisionField({
  precision,
  raw,
  onChange,
  className,
  disabled = false,
  titleSigma,
  titleRaw,
}: PrecisionFieldProps) {
  if (raw) {
    return (
      <input
        type="number"
        step={100}
        min={1}
        value={Math.round(precision)}
        title={titleRaw}
        disabled={disabled}
        onChange={(e) => {
          const v = e.target.valueAsNumber;
          if (Number.isFinite(v) && v > 0) onChange(v);
        }}
        className={className}
      />
    );
  }
  const sigma = sigmaPtsFromPrecision(precision);
  return (
    <input
      type="number"
      step={0.05}
      min={0.01}
      value={Number.isFinite(sigma) ? Number(sigma.toFixed(2)) : 0}
      title={titleSigma}
      disabled={disabled}
      onChange={(e) => {
        const v = e.target.valueAsNumber;
        if (Number.isFinite(v) && v > 0) onChange(precisionFromSigmaPts(v));
      }}
      className={className}
    />
  );
}
