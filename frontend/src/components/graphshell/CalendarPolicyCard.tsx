// Calendar policy card (P5b U2) — the messages-mode Calendar card grown into
// a POLICY editor: global enable, the §8/§9.2 dials (via the U1 sections), a
// LIVE +1pt example recomputed from the knobs (lib/messagePreview math — the
// same formulas the solver runs), per-ticker policy overrides (backend
// CalendarPolicyOverride: enable / precision scale / shape exponent, unset ⇒
// inherit), and the per-ticker LADDER view with β/σ chips + |β|-cap warnings.
// Row-level relation edits stay in the MessageEdgeEditor (advanced overrides).
import { useState } from "react";
import PrecisionField from "../PrecisionField";
import { MessageCalendarSection } from "../MessagePanel";
import {
  BETA_CAP,
  calendarLadder,
  effectiveCalendarPolicy,
} from "../../lib/calendarPolicy";
import { calendarBeta, calendarPrecision } from "../../lib/messagePreview";
import { relationSentence } from "../../lib/precisionUnits";
import type { CalendarOverride, SolverParams } from "../../state/useGraph";
import type { UniverseExpiry } from "../../state/useSmile";

interface CalendarPolicyCardProps {
  params: SolverParams;
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
  /** U1 units lens (σ pts default / raw precision). */
  raw: boolean;
  /** Selected universe (tickers + expiry ladders), or null before it loads. */
  tickers: string[];
  expiries: Record<string, UniverseExpiry[]>;
}

const INHERIT: CalendarOverride = { enabled: true, precisionScale: null, betaExponent: null };

const numCls =
  "w-14 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right " +
  "font-mono text-[10px] text-slate-100 outline-none hover:border-slate-600 " +
  "focus:border-accent-500 disabled:cursor-not-allowed disabled:opacity-40";

export default function CalendarPolicyCard({
  params,
  setParam,
  raw,
  tickers,
  expiries,
}: CalendarPolicyCardProps) {
  const [ladderTicker, setLadderTicker] = useState("");
  const activeTicker = ladderTicker !== "" ? ladderTicker : (tickers[0] ?? "");

  const setOverride = (ticker: string, patch: Partial<CalendarOverride>) => {
    const prev = params.calendarOverrides[ticker] ?? INHERIT;
    setParam("calendarOverrides", {
      ...params.calendarOverrides,
      [ticker]: { ...prev, ...patch },
    });
  };
  const removeOverride = (ticker: string) => {
    const next = { ...params.calendarOverrides };
    delete next[ticker];
    setParam("calendarOverrides", next);
  };
  const overriddenTickers = Object.keys(params.calendarOverrides).sort();
  const addable = tickers.filter((t) => !(t in params.calendarOverrides));

  // LIVE +1pt example on the canonical 3M/6M pair (spec §8.2/§9.2): the exact
  // transfer and relationship uncertainty the current dials imply.
  const exBeta = calendarBeta(0.25, 0.5, params.alphaT);
  const exPrecision = calendarPrecision(
    0.25, 0.5, params.calPrecision, params.calEpsilon, params.calDecay,
  );
  const example = relationSentence({
    sourceLabel: "6M",
    targetLabel: "3M",
    beta: exBeta,
    precision: exPrecision,
    rho: params.ampCal,
  });

  // Ladder view under the ACTIVE ticker's effective policy.
  const policy = effectiveCalendarPolicy(params, activeTicker);
  const rungs =
    policy.enabled && activeTicker !== ""
      ? calendarLadder(expiries[activeTicker] ?? [], {
          alphaT: policy.alphaT,
          scale: policy.scale,
          epsilon: params.calEpsilon,
          decay: params.calDecay,
        })
      : [];
  const cappedCount = rungs.filter((r) => r.capped).length;

  return (
    <div>
      {/* Policy switch: suppresses every calendar-class factor (auto ladders
          AND persisted calendar rows); cross relations keep flowing. */}
      <label
        className="mb-2 flex items-center gap-2 text-xs text-slate-300"
        title="Calendar policy switch — off suppresses all calendar factors (auto ladders and persisted calendar rows); cross-asset relations keep flowing"
      >
        <input
          type="checkbox"
          checked={params.calendarEnabled}
          onChange={(e) => setParam("calendarEnabled", e.target.checked)}
          className="accent-accent-500"
        />
        Calendar messages
      </label>

      {!params.calendarEnabled ? (
        <p className="text-[10px] text-slate-600">
          Calendar factors suppressed — smiles only talk across tickers.
        </p>
      ) : (
        <>
          <MessageCalendarSection params={params} setParam={setParam} raw={raw} />

          {/* LIVE example: recomputed from the dials above. */}
          <p
            className="mb-2 rounded-md border border-slate-800 bg-surface-800/60 px-2 py-1 font-mono text-[10px] text-slate-400"
            data-testid="cal-live-example"
            title="Live example on the canonical 3M/6M pair — exactly the solver's §8.2 shape and §9.2 precision family under the current dials"
          >
            {example}
          </p>

          {/* Per-ticker policy overrides (unset fields inherit the dials). */}
          <div className="mb-1 mt-2 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Per-ticker overrides
            </span>
            {addable.length > 0 && (
              <select
                className="rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono text-[10px] text-slate-400 outline-none focus:border-accent-500"
                value=""
                onChange={(e) => {
                  if (e.target.value !== "") setOverride(e.target.value, {});
                }}
                title="Add a per-ticker calendar-policy override"
              >
                <option value="">+ ticker…</option>
                {addable.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
          </div>
          {overriddenTickers.length === 0 ? (
            <p className="text-[10px] text-slate-600">
              None — every ticker runs the policy above.
            </p>
          ) : (
            <div className="divide-y divide-slate-800/60">
              {overriddenTickers.map((ticker) => {
                const o = params.calendarOverrides[ticker] ?? INHERIT;
                return (
                  <div key={ticker} className="flex items-center gap-1.5 py-1">
                    <label
                      className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-xs text-slate-300"
                      title={`Calendar messages on/off for ${ticker}`}
                    >
                      <input
                        type="checkbox"
                        checked={o.enabled}
                        onChange={(e) => setOverride(ticker, { enabled: e.target.checked })}
                        className="accent-accent-500"
                      />
                      <span className="font-medium">{ticker}</span>
                    </label>
                    {/* σ@ref / raw scale override; empty = inherit. */}
                    {o.precisionScale !== null ? (
                      <PrecisionField
                        precision={o.precisionScale}
                        raw={raw}
                        onChange={(p) => setOverride(ticker, { precisionScale: p })}
                        className={numCls}
                        disabled={!o.enabled}
                        titleSigma={`${ticker} uncertainty @ref override (vol pts); ↺ to inherit`}
                        titleRaw={`${ticker} precision-scale override (1/vol²); ↺ to inherit`}
                      />
                    ) : (
                      <button
                        className="w-14 rounded-md border border-dashed border-slate-700 px-1 py-1 text-[9px] italic text-slate-600 hover:border-slate-600 hover:text-slate-400"
                        onClick={() => setOverride(ticker, { precisionScale: params.calPrecision })}
                        title={`Inheriting the policy scale — click to set a ${ticker}-specific uncertainty`}
                      >
                        inherit
                      </button>
                    )}
                    {/* αT override; empty = inherit. */}
                    <input
                      type="number"
                      step={0.25}
                      value={o.betaExponent ?? ""}
                      placeholder={String(params.alphaT)}
                      onChange={(e) => {
                        const v = e.target.valueAsNumber;
                        setOverride(ticker, {
                          betaExponent: Number.isFinite(v) ? v : null,
                        });
                      }}
                      disabled={!o.enabled}
                      title={`${ticker} shape exponent αT override (empty = inherit ${params.alphaT})`}
                      className={numCls}
                    />
                    <button
                      onClick={() => removeOverride(ticker)}
                      title={`Remove the ${ticker} override (back to the policy)`}
                      className="px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* Calendar LADDER view: the ticker's adjacent-pair factors. */}
          <details className="mt-2">
            <summary className="cursor-pointer text-[11px] text-slate-500 transition-colors hover:text-slate-300">
              Ladder view
            </summary>
            <div className="mt-1.5">
              <select
                className="mb-1.5 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500"
                value={activeTicker}
                onChange={(e) => setLadderTicker(e.target.value)}
                title="Ticker whose calendar ladder to display"
              >
                {tickers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              {!policy.enabled ? (
                <p className="text-[10px] text-slate-600">
                  Calendar messages are off for {activeTicker}.
                </p>
              ) : rungs.length === 0 ? (
                <p className="text-[10px] text-slate-600">
                  No adjacent live expiries — the ladder needs at least two.
                </p>
              ) : (
                <>
                  {cappedCount > 0 && (
                    <p className="mb-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-300">
                      ⚠ {cappedCount} rung{cappedCount > 1 ? "s" : ""} with |β| &gt;{" "}
                      {BETA_CAP} — wide maturity gap; consider an αT override.
                    </p>
                  )}
                  <div className="space-y-0.5">
                    {rungs.map((r) => (
                      <p
                        key={`${r.shortExpiry}|${r.longExpiry}`}
                        className="font-mono text-[10px] text-slate-400"
                        title={relationSentence({
                          sourceLabel: `${activeTicker} ${r.longExpiry.slice(5)}`,
                          targetLabel: `${activeTicker} ${r.shortExpiry.slice(5)}`,
                          beta: r.beta,
                          precision: r.precision,
                          rho: params.ampCal,
                        })}
                      >
                        {r.shortExpiry.slice(5)}{" "}
                        <span className="text-accent-400">←</span> {r.longExpiry.slice(5)}
                        {" · "}
                        <span className={r.capped ? "text-amber-300" : "text-slate-300"}>
                          β {r.beta.toFixed(2)}
                        </span>
                        {" · σ "}
                        {Number.isFinite(r.sigmaPts) ? r.sigmaPts.toFixed(2) : "∞"} pt
                      </p>
                    ))}
                  </div>
                </>
              )}
            </div>
          </details>
        </>
      )}
    </div>
  );
}
