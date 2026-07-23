# Dynamic-harmonic Phase-5 adjudication — findings & decision table

**Status: ADJUDICATED 2026-07-23 (campaign 2, tags `_p5b_dyn_*`).
VERDICT: RECORD, HOLD ADOPTION — the layered mode stays opt-in; no
default change; residual memory has NEGATIVE marginal value at the
one-day horizon.**

## Campaign-2 results (21,958 intersected OOS rows across 7 arms)

ATM RMS, bp, all OOS pairs (warm-only in parens — first store-cold date
per regime excluded):

| arm            | full_loo        | liquid_split |
|----------------|-----------------|--------------|
| transported prior | 286.3 (254.5) | 318.0 (282.4) |
| `_b14_base`    | 279.3 (245.9)   | 317.9 (282.3) |
| `_p4_msg_learned` | 280.9 (247.4) | 320.1 (283.6) |
| `_p5_dyn` memoryless | 280.2 (240.7) | 323.9 (284.1) |
| `_p5b_dyn_desk` (H=∞) | 333.1 (308.0) | 323.9 (284.1) |
| `_p5b_dyn_hl1` | **285.1 (247.3)** | 323.9 (284.1) |
| `_p5b_dyn_hl5` | 290.1 (253.7)   | 323.9 (284.1) |
| `_p5b_dyn_hl20` | 305.5 (273.5)  | 323.9 (284.1) |

Internal consistency: liquid_split identical across all dyn variants and
equal to the memoryless arm (names dark all week ⇒ no residual exists) —
the harness fix measured exactly what it should.

### The two headline findings

1. **Residual memory does not earn its keep at the one-day horizon.**
   full_loo skill is MONOTONE in half-life: desk(∞) 333 → hl20 305 →
   hl5 290 → hl1 285 → memoryless 280. The optimum is H → 0: a one-day-
   old idiosyncratic dislocation carries more noise than signal on this
   universe. hl1 beats the transported prior (−1.2bp) but loses to the
   smooth-field base (+5.8), the message arm (+4.2), and its own
   memoryless ablation (+4.9).
2. **The layered SPATIAL solve has a real stressed-regime edge — and a
   calm-regime cost.** Memoryless-layered full_loo (warm): spike 271.6
   vs base 286.3 (−14.7bp), high 205.8 vs 215.0 (−9.2bp), but calm
   low_jul2023 247.2 vs 241.0 (+6.2bp, and hl1 258.9 is worse still).
   The directed clamp+cut helps exactly when systematic moves dominate.

## §16.3 decision table (all-pairs, pre-registered)

| gate | criterion                                              | verdict |
|------|--------------------------------------------------------|---------|
| 1    | full_loo dark RMS < prior AND base AND msg_learned     | **FAIL** (hl1: beats prior only) |
| 2    | liquid_split non-degrading vs msg_learned              | **FAIL (marginal)** (+3.8bp; warm ≈ tie +0.5) |
| 3    | stressed regimes non-degrading                         | PASS (spike/high full_loo IMPROVE vs base+msg) |
| 4    | ζ std ≈ 1; cov80/cov95 near nominal                    | **FAIL** (hl1 std 1.68, cov80 0.92; base 0.74, msg 2.07) |
| 5    | reverse leakage zero (structural)                      | PASS (by construction) |
| 6    | wing RMS non-deteriorating                             | **FAIL** (full_loo 131 vs 126 transport; liquid_split 193 vs 121 — see follow-up) |

**Half-life selection (if forced):** hl1 — but the monotone trend says
H → 0, i.e. don't carry the state at this horizon.

**DECISION: RECORD VERDICT, HOLD ADOPTION.** `layered_dynamic_harmonic`
stays a selectable research mode; `smooth_field` remains the default;
the message-arc P4 verdict is unchanged. No production wiring changes.

## Recorded follow-ups (would need to clear before re-adjudication)

1. **Wing-RMS regression (liquid_split 192.6 vs 121.1 bp, n drop 8682 →
   7603 = more retarget failures).** Shared by the memoryless arm ⇒ a
   SPATIAL-layer issue, not memory. Prime suspect: the harness taxonomy
   broadcasts vol-normalized ATM betas to all three handles, so dark
   skew/curvature predictions from directed anchors are wrong-scale and
   reconstruction suffers.
   **FIXED IN THE HARNESS 2026-07-23 (partial mitigation, verified):**
   `build_message_edges` cross rows now carry `shape_beta = 1.0` for
   skew/curvature while the ATM beta stays vol-normalized (calendar
   keeps the maturity ratio on all handles). Single-pair smoke (spike
   2024-08-13, liquid_split, ssr 0, vs the stored `_p5b` rows for the
   same slice): res_atm bit-identical 196/196 (ATM untouched, as
   required); wing_full_g 231.8 → 214.0 bp; retarget failures recovered
   (144 → 166 of 196 nodes computable); skew/curv residual RMS 0.192 →
   0.186 / 29.1 → 27.8. The REMAINING gap vs baseline transport
   (~140 bp on that slice) is full-amplitude shape transfer through
   directed anchors — candidates for a future pass: a shape amplitude
   below one, or zero cross shape transfer. Existing campaign parts are
   untouched; any re-adjudication runs on the fixed taxonomy.
2. **Calibration narrowness (ζ std ~1.7).** The diagonal unary anchors
   (D6 v1) understate dark-node variance when predictions share parents
   — the D6 joint form exists in the solver and is the first candidate.
3. **Scope caveat, honestly stated:** this campaign tests DAILY
   granularity where every full_loo node relights each day. The
   framework's target regime — sparse intraday asynchrony (the §5 A/B
   story: a name lit once mid-session, marked against a moving liquid
   source) — is NOT what this harness measures. The asynchronous
   timestamp replay at the finest stored frequency (§16.1) remains the
   decisive future experiment for the residual state; at day granularity
   the answer is "don't carry it".

## Campaign 1 post-mortem (2026-07-22, tags `_p5_dyn_*` — INVALID for the
## half-life question, RETAINED as the memoryless-layered ablation arm)

All four `_p5_dyn_*` variants produced **byte-identical parts** (hash-equal
per regime). Root cause: the harness's cross-relation betas are
vol-normalized from each day's data, so they drift daily; the structural
residual-config hash included beta values; therefore **every pair looked
like a config change and purged the residual store** (golden 15.13 firing
on estimation drift). Residuals never survived a single day — the layered
mode ran spatially (rows differ from `_b14_base` everywhere: 0/1772
matching residuals) but with zero temporal memory, making the half-life
knob inert. Fix: `residualConfigVersion` on the request — a caller-owned
stable store identity (the harness pins `p5:<mode>:<half-life>`); the
structural hash remains the default so explicit beta edits still
invalidate (both behaviours test-locked). The stale `_p5_dyn_*` parts are
a valid **layered-without-memory** arm: any `_p5b_*` full_loo improvement
over `_p5_dyn_*` is attributable to the residual state specifically.
Also: `_p5_dyn_hl20` never wrote its low_jul2023 part (run interrupted);
the `_p5b_*` tags cover it.

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
