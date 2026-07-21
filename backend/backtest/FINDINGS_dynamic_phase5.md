# Dynamic-harmonic Phase-5 adjudication — findings & decision table

**Status: AWAITING CAMPAIGN** (launch `run_dynamic_adjudication.ps1` from the
user's window; this file is filled from the tagged parts afterward).

Framework: `Docs/dynamic_directed_harmonic_graph_framework.md` §16 (metrics,
replay designs, adoption gate §16.3). Machinery: `backtest/graph_loo.py`
threads ONE residual store per (design, ssr) cell chronologically through the
day pairs; holdout solves read a pre-day-T snapshot (no self-leakage) and
never write (update_store=False end to end).

## Variants

| tag             | mode                     | residual half-life |
|-----------------|--------------------------|--------------------|
| `_b14_base`     | smooth_field (campaign 1)| —                  |
| `_p4_msg_learned` | precision_messages (c.1)| —                 |
| `_p5_dyn_desk`  | layered_dynamic_harmonic | persistent (none)  |
| `_p5_dyn_hl1`   | layered_dynamic_harmonic | 1 day              |
| `_p5_dyn_hl5`   | layered_dynamic_harmonic | 5 days             |
| `_p5_dyn_hl20`  | layered_dynamic_harmonic | 20 days            |

Relation semantics in the harness taxonomy: calendar ladders → reciprocal
harmonic; index/ETF → constituent rows (class broad_index / sector_etf) →
DIRECTED arcs (the §9.2 defaults — the benchmark exercises the real layered
topology, liquid → illiquid, DAG by construction).

## What each design measures

- **full_loo** = the lit→dark ONE-STEP TRANSITION test: every node records a
  residual on day T−1; the held node's day-T prediction is
  `systematic_T + φ(1d)·u_{T−1}`. This is where temporal memory must EARN
  its keep vs the memoryless arms.
- **liquid_split** = pure directed systematic + boundary clamp: names are
  dark all week, so no residual memory exists for them by design. Isolates
  the layered mode's spatial half.

## Known caveats (pre-registered)

1. Chunk cold-start: each chunk's first OOS pair runs with an empty store —
   identical across variants (fair), slightly anti-dynamic (conservative).
2. Store causality verified by test locks (`test_graph_dynamic_production`):
   holdout solves read-only on a pre-day-T snapshot.
3. Reverse leakage is structurally zero (Phase-2 cut + Phase-4 wiring locks);
   reported as a contract, not measured.
4. liquid_split under-represents the dynamic edge (see above) — a NEGATIVE
   full_loo verdict cannot be rescued by liquid_split, but not vice versa.

## §16.3 decision table (fill from parts)

| gate | criterion                                              | verdict |
|------|--------------------------------------------------------|---------|
| 1    | full_loo dark RMS < prior AND base AND msg_learned     |         |
| 2    | liquid_split non-degrading vs msg_learned              |         |
| 3    | stressed regimes non-degrading                         |         |
| 4    | ζ std ≈ 1; cov80/cov95 near nominal                    |         |
| 5    | reverse leakage zero (structural)                      | PASS (by construction) |
| 6    | wing RMS non-deteriorating                             |         |

**Half-life selection:** best full_loo skill × coverage; ties → longer H.

**DECISION:** _(pending)_
