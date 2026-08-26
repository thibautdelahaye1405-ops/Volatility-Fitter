// Centered "requires the live backend" card shared by the live-only lenses
// (Graph, Local Vol, Forwards, Quality) and the Universe dialog: title, the
// standard hint, the last error (truncated, full text in the tooltip) and an
// optional Retry.
import { buttonClass, cardClass } from "../../lib/ui";

export default function OfflineCard({
  title,
  hint = "Start the FastAPI server on :8000 and retry.",
  error = null,
  onRetry,
}: {
  title: string;
  hint?: string;
  error?: string | null;
  onRetry?: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center p-4">
      <div className={`${cardClass} max-w-sm p-8 text-center`}>
        <h2 className="mb-2 text-sm font-semibold text-slate-100">{title}</h2>
        <p className="mb-1 text-xs text-slate-500">{hint}</p>
        {error && (
          <p className="mb-5 truncate text-[10px] text-amber-400/80" title={error}>{error}</p>
        )}
        {onRetry && (
          <button className={buttonClass} onClick={onRetry}>Retry</button>
        )}
      </div>
    </div>
  );
}
