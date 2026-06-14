// Forwards workspace (ROADMAP Phase 10): per-ticker forwards & dividends.
//
// All forward/dividend tuning in one place, shared by the Parametric and Local
// Vol workspaces (both read the active forward through the backend's forwards
// version, so an edit here refits every workspace). Left: a forwards table
// across the whole expiry ladder (parity / theoretical / manual / active),
// rows select the expiry. Right: the per-expiry ForwardPanel (mode + manual
// override + carry r/q + the dividend-schedule editor), reused verbatim.
//
// Live backend only (GET /forwards/{ticker}); offline shows a retry card.
import { useCallback, useEffect, useState } from "react";
import ForwardPanel from "../components/ForwardPanel";
import ForwardCurveChart from "../components/ForwardCurveChart";
import type { ForwardsResponse } from "../components/ForwardPanel";
import { useSmileSession } from "../state/smileSession";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import { api } from "../state/api";

const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** Equity-level forward formatting; em-dash for missing values. */
const fmtFwd = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : v.toFixed(2);

export default function ForwardsViewer() {
  const { universe, ticker, setTicker, source, reload } = useSmileSession();
  const { format } = useExpiryFormat();
  const live = source === "live";
  const tickers = universe?.tickers ?? [];

  const [data, setData] = useState<ForwardsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<string>("");
  // Bumped to refetch the table after an edit is applied.
  const [nonce, setNonce] = useState(0);

  // (Re)load the ticker's forwards table; keep a valid selected expiry.
  useEffect(() => {
    if (!live || ticker === "") return;
    const controller = new AbortController();
    api
      .get<ForwardsResponse>(`/forwards/${ticker}`, { signal: controller.signal })
      .then((res) => {
        setData(res);
        setError(null);
        setExpiry((prev) =>
          res.entries.some((e) => e.expiry === prev)
            ? prev
            : (res.entries[0]?.expiry ?? ""),
        );
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [live, ticker, nonce]);

  // After a forward/dividend edit: refetch the table and refit every workspace.
  const onApplied = useCallback(() => {
    setNonce((n) => n + 1);
    reload();
  }, [reload]);

  if (!live) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Forwards require the live backend
          </h2>
          <p className="text-xs text-slate-500">
            Start the FastAPI server on :8000 to tune forwards &amp; dividends.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: underlying + spot + exercise style */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Underlying
          <select
            className={selectClass}
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            disabled={tickers.length === 0}
          >
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        {data && (
          <span className="font-mono text-[11px] text-slate-500">
            spot {data.spot.toFixed(2)} · {data.exerciseStyle} ·{" "}
            {data.entries.length} expiries
          </span>
        )}
        {error && (
          <span className="ml-auto truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </span>
        )}
      </div>

      {/* Forward-curve chart with dividend markers + click-to-add manual divs */}
      {data && data.entries.length > 0 && (
        <div className="h-64 shrink-0 rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <ForwardCurveChart
            ticker={ticker}
            disabled={!live}
            entries={data.entries}
            spot={data.spot}
            refreshKey={nonce}
            onApplied={onApplied}
          />
        </div>
      )}

      {/* Body: forwards table + per-expiry ForwardPanel */}
      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-100">
            Forward ladder · click a row to edit its policy
          </h2>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="w-full border-collapse font-mono text-[11px] leading-tight">
              <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
                <tr>
                  {["Expiry", "T", "Parity", "Theo", "Manual", "Active", "Source"].map((h) => (
                    <th
                      key={h}
                      className={[
                        "px-2 py-1.5 font-medium whitespace-nowrap",
                        h === "Expiry" || h === "Source" ? "text-left" : "text-right",
                      ].join(" ")}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {(data?.entries ?? []).map((e) => (
                  <tr
                    key={e.expiry}
                    onClick={() => setExpiry(e.expiry)}
                    className={[
                      "cursor-pointer hover:bg-surface-800/60",
                      e.expiry === expiry ? "bg-accent-600/10 text-accent-300" : "text-slate-200",
                    ].join(" ")}
                  >
                    <td className="px-2 py-1 text-left text-slate-400">
                      {formatExpiry(e.expiry, e.t, format)}
                    </td>
                    <td className="px-2 py-1 text-right">{e.t.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.parityForward)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.theoForward)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.manualForward)}</td>
                    <td className="px-2 py-1 text-right font-semibold text-accent-400">
                      {fmtFwd(e.activeForward)}
                    </td>
                    <td className="px-2 py-1 text-left text-slate-500">{e.activeSource}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 shrink-0 text-[10px] text-slate-600">
            Active forward feeds every fit (Parametric &amp; Local Vol) via the
            forwards version — edits refit both workspaces.
          </p>
        </div>

        {/* Per-expiry forward / dividend editor (reused from the smile aside) */}
        <aside className="w-80 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <ForwardPanel
            disabled={!live || expiry === ""}
            ticker={ticker}
            expiry={expiry}
            onApplied={onApplied}
          />
        </aside>
      </div>
    </div>
  );
}
