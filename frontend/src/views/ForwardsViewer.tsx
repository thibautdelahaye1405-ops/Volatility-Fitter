// Forwards lens (UI SHELL v2): the active tab's TICKER — forwards & dividends
// across its whole expiry ladder, the per-expiry editor on the tab's expiry.
//
// All forward/dividend tuning in one place, shared by the Parametric and Local
// Vol lenses (both read the active forward through the backend's forwards
// version, so an edit here refits every lens). Top: the forward-curve chart
// with dividend markers. Left: the forward ladder (parity / theoretical /
// manual / active / borrow, optional joint borrow/de-Am columns); clicking a
// row opens that node's tab (preview), which moves the editor. Right: the
// per-expiry ForwardPanel (mode + manual override + carry r/q + the
// dividend-schedule editor), reused verbatim.
//
// Live backend only (GET /forwards/{ticker}); offline shows a card.
import { useCallback, useEffect, useState } from "react";
import ForwardPanel from "../components/ForwardPanel";
import ForwardCurveChart from "../components/ForwardCurveChart";
import type { ForwardsResponse } from "../components/ForwardPanel";
import { useSmileSession } from "../state/smileSession";
import { useExpiryFormat } from "../state/expiryFormat";
import { useOptionalWorkbench } from "../state/workbench";
import { formatExpiry } from "../lib/expiryFormat";
import { cardClass } from "../lib/ui";
import { api } from "../state/api";

/** Equity-level forward formatting; em-dash for missing values. */
const fmtFwd = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : v.toFixed(2);

/** Per-expiry joint-carry read off GET /carry/{ticker}?joint=true (R2 item 11). */
interface CarryJointPoint {
  expiry: string;
  jointBorrowBp: number | null;
  jointIterations: number | null;
  jointConverged: boolean | null;
  jointDeamFailures: number | null;
  borrowNoiseFloorBp: number | null;
  ivBorrowSensBpPer100: number | null;
}
interface CarryResponse {
  points: CarryJointPoint[];
}

export default function ForwardsViewer() {
  const { ticker, expiry: sessionExpiry, source, reload, setExpiry: setSessionExpiry } = useSmileSession();
  const { format } = useExpiryFormat();
  const wb = useOptionalWorkbench();
  const live = source === "live";

  const [data, setData] = useState<ForwardsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped to refetch the table after an edit is applied.
  const [nonce, setNonce] = useState(0);
  // Joint borrow/de-Am fixed point (R2 item 11): opt-in — the solve runs a
  // de-Am pass per iteration per expiry on first fetch (then state-cached).
  const [jointOn, setJointOn] = useState(false);
  const [joint, setJoint] = useState<Record<string, CarryJointPoint>>({});

  // The edited expiry = the tab's (session) expiry when it is on the ladder,
  // else the first rung — the editor always has a valid target.
  const expiry =
    data?.entries.some((e) => e.expiry === sessionExpiry)
      ? sessionExpiry
      : (data?.entries[0]?.expiry ?? "");
  /** Row click: open that node's tab (preview) — the session follows. */
  const selectExpiry = (e: string) => {
    if (wb !== null) wb.openNode({ ticker, expiry: e }, { preview: true });
    else setSessionExpiry(e);
  };

  useEffect(() => {
    if (!jointOn || !live || ticker === "") {
      setJoint({});
      return;
    }
    const controller = new AbortController();
    api
      .get<CarryResponse>(`/carry/${ticker}?joint=true`, { signal: controller.signal })
      .then((res) => {
        const byExpiry: Record<string, CarryJointPoint> = {};
        for (const p of res.points) byExpiry[p.expiry] = p;
        setJoint(byExpiry);
      })
      .catch(() => setJoint({})); // advisory columns: never break the table
    return () => controller.abort();
  }, [jointOn, live, ticker, nonce]);

  // (Re)load the ticker's forwards table.
  useEffect(() => {
    if (!live || ticker === "") return;
    const controller = new AbortController();
    api
      .get<ForwardsResponse>(`/forwards/${ticker}`, { signal: controller.signal })
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [live, ticker, nonce]);

  // After a forward/dividend edit: refetch the table and refit every lens.
  const onApplied = useCallback(() => {
    setNonce((n) => n + 1);
    reload();
  }, [reload]);

  if (!live) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className={`${cardClass} max-w-sm p-8 text-center`}>
          <h2 className="mb-2 text-sm font-semibold text-slate-100">Forwards require the live backend</h2>
          <p className="text-xs text-slate-500">Start the FastAPI server on :8000 to tune forwards &amp; dividends.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      {/* Header: ticker · spot · exercise style · joint-carry toggle */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold text-slate-100">{ticker} forwards &amp; dividends</h2>
        {error && (
          <span className="truncate text-[10px] text-amber-400/80" title={error}>{error}</span>
        )}
        {data && (
          <span className="ml-auto flex items-center gap-2 font-mono text-[11px] text-slate-500">
            {data.zeroCarry && (
              <span
                className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400"
                title="The feed gated NBBO quotes, so this chain was synthesized from the provider's per-contract IVs at zero carry (every price is Black at forward = spot, discount = 1, zero spread). Parity carries no information here, so the forward is pinned to that convention — not a market read."
              >
                IV-synthesized · zero carry · F pinned to spot
              </span>
            )}
            <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5">spot {data.spot.toFixed(2)}</span>
            <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5">{data.exerciseStyle}</span>
            <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5">{data.entries.length} expiries</span>
          </span>
        )}
        <label
          className={`${data ? "" : "ml-auto "}flex cursor-pointer items-center gap-1.5 text-xs text-slate-400`}
          title="Joint borrow/de-Am fixed point per expiry (R2 item 11): de-Americanize at the split carry, iterate to the parity/theoretical fixed point. Adds Joint and ±σ columns."
        >
          <input type="checkbox" checked={jointOn} disabled={!live}
            onChange={(e) => setJointOn(e.target.checked)} className="accent-accent-500" />
          Joint carry
        </label>
      </div>

      {/* Forward-curve chart with dividend markers + click-to-add manual divs */}
      {data && data.entries.length > 0 && (
        <div className={`${cardClass} h-60 shrink-0 p-4`}>
          <ForwardCurveChart ticker={ticker} disabled={!live} entries={data.entries}
            spot={data.spot} refreshKey={nonce} onApplied={onApplied} />
        </div>
      )}

      {/* Body: forwards ladder + per-expiry ForwardPanel */}
      <div className="flex min-h-0 flex-1 gap-3">
        <div className={`${cardClass} flex min-w-0 flex-1 flex-col p-4`}>
          <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-100">
            Forward ladder · click a row to edit its policy
          </h2>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="w-full border-collapse font-mono text-[11px] leading-tight">
              <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
                <tr>
                  {["Expiry", "T", "Parity", "Theo", "Manual", "Active", "Borrow",
                    ...(jointOn ? ["Joint", "±σ"] : []), "Source"].map((h) => (
                    <th key={h} className={["px-2 py-1.5 font-medium whitespace-nowrap",
                      h === "Expiry" || h === "Source" ? "text-left" : "text-right"].join(" ")}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {(data?.entries ?? []).map((e) => (
                  <tr
                    key={e.expiry}
                    onClick={() => selectExpiry(e.expiry)}
                    onDoubleClick={() => wb?.openNode({ ticker, expiry: e.expiry })}
                    className={["cursor-pointer hover:bg-surface-800/60",
                      e.expiry === expiry ? "bg-accent-600/10 text-accent-300" : "text-slate-200"].join(" ")}
                  >
                    <td className="px-2 py-1 text-left text-slate-400">{formatExpiry(e.expiry, e.t, format)}</td>
                    <td className="px-2 py-1 text-right">{e.t.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.parityForward)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.theoForward)}</td>
                    <td className="px-2 py-1 text-right">{fmtFwd(e.manualForward)}</td>
                    <td className="px-2 py-1 text-right font-semibold text-accent-400">{fmtFwd(e.activeForward)}</td>
                    <td
                      className="px-2 py-1 text-right text-slate-400"
                      title={typeof e.impliedBorrowBp === "number"
                        ? "Option-implied borrow (parity vs theoretical forward), bp/yr"
                        : "Carry unidentified at this expiry (thin parity / zero-carry / non-parity mode) — not a zero"}
                    >
                      {typeof e.impliedBorrowBp === "number" ? `${e.impliedBorrowBp.toFixed(0)} bp` : "—"}
                    </td>
                    {jointOn && (() => {
                      const j = joint[e.expiry];
                      const has = typeof j?.jointBorrowBp === "number";
                      return (
                        <>
                          <td
                            className={["px-2 py-1 text-right",
                              has && j!.jointConverged === false ? "text-amber-400" : "text-slate-300"].join(" ")}
                            title={has
                              ? `Joint borrow/de-Am fixed point: ${j!.jointIterations} iterations, ` +
                                `${j!.jointConverged ? "converged" : "NOT converged"}, ` +
                                `${j!.jointDeamFailures} tree failures. ` +
                                `ATM IV sensitivity ${j!.ivBorrowSensBpPer100?.toFixed(0) ?? "—"} bp per 100bp borrow.`
                              : "No joint read (thin parity / zero-carry / unsupported dividend mix)"}
                          >
                            {has ? `${j!.jointBorrowBp!.toFixed(0)} bp` : "—"}
                          </td>
                          <td className="px-2 py-1 text-right text-slate-500"
                            title="1σ noise floor on the borrow read (parity residuals / (t·√n)): a read is only as good as this, whatever solver produced it.">
                            {typeof j?.borrowNoiseFloorBp === "number" ? `±${j.borrowNoiseFloorBp.toFixed(0)}` : "—"}
                          </td>
                        </>
                      );
                    })()}
                    <td className="px-2 py-1 text-left text-slate-500">{e.activeSource}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 shrink-0 text-[10px] text-slate-600">
            Active forward feeds every fit (Parametric &amp; Local Vol) via the forwards
            version — edits refit both lenses. A row click opens the node's tab.
          </p>
        </div>

        {/* Per-expiry forward / dividend editor */}
        <aside className={`${cardClass} w-80 shrink-0 overflow-y-auto p-5`}>
          <ForwardPanel disabled={!live || expiry === ""} ticker={ticker} expiry={expiry} onApplied={onApplied} />
        </aside>
      </div>
    </div>
  );
}
