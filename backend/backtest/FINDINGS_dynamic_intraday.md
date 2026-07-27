# Dynamic-harmonic intraday async replay — pre-registered design & gate

**Status: ADJUDICATED 2026-07-27 (56 parts, 7 arms × 8 sessions,
13,356 scored rows/arm). VERDICT: RECORD, HOLD ADOPTION — the residual
MECHANISM is validated for the first time (interior half-life optimum
H\* ≈ 0.1d with the §16.2 persistence shape and calibrated bands —
everything the daily campaign could not see), but gate B fails: the
static precision-message operator beats every layered arm on this
universe, so the layered carrier, not the memory, is the bottleneck.**

## Campaign results (async_once POST phase, pooled R∈{0,1}, n=1908/arm)

| arm               | ATM RMS bp | ζ std | cov80 | cov95 |
|-------------------|-----------|-------|-------|-------|
| transported prior | 172.7     |       |       |       |
| `intra_base`      | 168.6     | 0.57  | 0.921 | 0.996 |
| `intra_msg`       | **65.8**  | 0.88  | 0.861 | 0.964 |
| `intra_dyn_mless` | 80.6      | 0.83  | 0.887 | 0.974 |
| `intra_dyn_desk`  | 108.1     | 2.75  | 0.356 | 0.540 |
| `intra_dyn_hl1`   | 75.6      | 0.88  | 0.828 | 0.939 |
| `intra_dyn_hl01`  | **73.7**  | 0.80  | 0.879 | 0.973 |
| `intra_dyn_hl002` | 77.1      | 0.82  | 0.871 | 0.966 |

**The H-curve has an INTERIOR optimum** — mless(H→0) 80.6 → hl002 77.1
→ **hl01 73.7** → hl1 75.6 → desk(∞) 108.1 — the exact structure the
daily campaign's monotone "H→0" could not exhibit. Memory skill vs the
memoryless ablation decays with elapsed-since-lit precisely as OU
predicts (hl01: **18.1 → 10.0 → 6.4 → 2.5 bp** across the four
buckets; hl1 overshoots to −3.1 late; desk collapses to −54.4 late with
ζ 2.75 — carrying a residual FLAT is harmful at every measured horizon,
the decay is load-bearing). Wing median: hl01 48.1 vs base 50.6 / msg
50.9 — no intraday wing regression (the campaign-2 shape_beta fix held).

## §16.3-style gate table (filled 2026-07-27)

| gate | criterion                                              | verdict |
|------|--------------------------------------------------------|---------|
| A    | interior-H optimum < memoryless AND < desk             | **PASS** (hl01: 73.7 < 80.6 < 108.1; robust per-R) |
| B    | that arm < base AND < msg on the same rows             | **FAIL** (73.7 << base 168.6 ✓ but > msg 65.8; msg wins both targets) |
| C    | first-bucket memory skill largest, decaying by bucket  | **PASS** (18.1 → 10.0 → 6.4 → 2.5 bp, monotone) |
| D    | ζ std ∈ [0.8, 1.3]; cov80/95 near nominal              | **PASS (marginal-conservative)** (0.80; 0.879/0.973 — the benign side; campaign 2 was 1.68 overconfident) |
| E    | async_dark invariant across layered arms               | **PASS** (all five byte-equal: 80.6/72.6 per R) |

**DECISION (pre-registered rule A ∧ B ∧ D): NOT declared valuable —
RECORD, HOLD.** `layered_dynamic_harmonic` stays opt-in; `smooth_field`
stays the default; no production change.

## What the verdict actually says (recorded findings)

1. **The residual state works as designed intraday.** A ∧ C ∧ D: an
   idiosyncratic dislocation observed once mid-session carries ~2.4h of
   genuine signal (H\* ≈ 0.1d), decaying exactly as the OU law assumes,
   with slightly conservative bands. The daily verdict ("don't carry
   it") and this one compose into a consistent picture: the residual's
   value lives INSIDE the session and is gone by the next day.
2. **The layered spatial carrier is the bottleneck, not the memory.**
   The spatial deficit vs the message operator (dark rows: msg 67.0/58.0
   vs layered 80.6/72.6 per R, ~13-15bp) exceeds the memory gain
   (~7bp pooled). On three near-exchangeable broad ETFs the directed
   cut discards target→hub information that reciprocal pooling keeps —
   this universe maximally punishes directedness by construction.
3. **Per-target asymmetry supports that reading**: hl01 recovers most of
   the gap on QQQ (70.9 vs msg 68.6) but none on IWM (76.3 vs 63.0) —
   the small-cap target is least served by an SPY-anchored systematic.
4. **smooth_field is nearly inert intraday** at default reach (168.6 vs
   transport 172.7): intraday innovations propagate through the message/
   layered operators, not the legacy smoothness prior.

## Decisive next experiment (recorded, not scheduled)

The NAMES universe campaign — capture SPY + genuinely asymmetric single
names (NVDA/AAPL; recipe below) and rerun the same launcher. That is the
regime where the directed cut should EARN its structural cost (a name
cannot inform the index), i.e. where gate B has a fair shot. If msg
still dominates there, the layered mode's remaining case reduces to its
stressed-regime edge (campaign 2 gate 3) + the zero-reverse-leakage
contract.
This is the §16.1 decisive experiment the campaign-2 verdict deferred to
(FINDINGS_dynamic_phase5.md, scope caveat 3): daily granularity relights
every node each day and cannot see the framework's target regime — a name
lit ONCE mid-session, marked against moving liquid sources thereafter.
At the day horizon the answer was "don't carry the residual" (skill
monotone in half-life, optimum H → 0). The intraday question is whether
an interior optimum exists at SESSION horizons.

## Design (locked before the campaign)

Harness: `backtest/graph_intraday.py` (parts per (tag, day), resumable;
`report` aggregates). Data: `results/intraday.sqlite` — SPY/QQQ/IWM ×
8 sessions (2026-06-30 … 2026-07-10) × 13 instants (10:00–15:45 ET).
Universe: the ETF triangle; hub SPY relabelled a DIRECTED broad-market
informer (layered semantics), QQQ↔IWM reciprocal peers, calendar ladders
reciprocal — the §5 A/B topology (DAG by construction). Same-day expiry
rungs excluded (calendar t = 0 is degenerate in the graph clock).

Per session: the FIRST stored instant is the frozen prior for every
ticker; each later instant is a full rebuilt state (intraday clock ON,
persistence off — pure market innovations) solved with the arm under
test; `solve(now_day=<fractional day>, obs_ages_days={})` so residual
age/half-life decay act within the session and stored chains certify
fresh AS OF their instant. Residual stores threaded chronologically per
(design, target) cell, reset per day (overnight carry was campaign 2's
question, answered negative).

Designs (target rotates over QQQ and IWM; the non-target stays lit):

- **async_once** — target lit only at `--lit-idx 3` (11:30 ET): scored
  dark pre (spatial only) and post (spatial + decayed residual);
- **async_dark** — target never lit: the memory-free control. Post-lit
  async_once skill ABOVE its own async_dark rows on the same
  (ts, node) is attributable to the residual state specifically.

Arms (tags):

| tag              | mode                     | residual half-life (days) |
|------------------|--------------------------|---------------------------|
| `intra_base`     | smooth_field             | —                         |
| `intra_msg`      | precision_messages       | —                         |
| `intra_dyn_mless`| layered, `--memoryless`  | store cleared per instant |
| `intra_dyn_desk` | layered                  | inf (persistent)          |
| `intra_dyn_hl1`  | layered                  | 1.0                       |
| `intra_dyn_hl01` | layered                  | 0.1  (~2.4h)              |
| `intra_dyn_hl002`| layered                  | 0.02 (~30min)             |

SSR sweep R ∈ {0, 1} (bracketing, as in every prior campaign). Metrics
per row: three-handle residuals vs the transported-prior baseline, ζ,
retargeted smile RMS, elapsed-since-lit + persistence bucket (§16.2).

## Pre-registered gate (as registered BEFORE the campaign; the filled
## table is at the top of this file)

Criteria as pre-registered: A — some finite-H layered arm's post-lit
ATM RMS < memoryless AND < desk (an interior optimum exists intraday);
B — that arm also < base AND < msg on the same rows; C — the first
post-lit bucket shows the largest memory skill, decaying by bucket;
D — ζ std ∈ [0.8, 1.3] and cov80/cov95 near nominal on post rows;
E — async_dark rows ~invariant across layered arms (consistency check).

**Decision rule (pre-registered):** the intraday residual state is
declared VALUABLE only on A ∧ B ∧ D (C reported as shape evidence).
A pass does NOT flip any production default by itself — it re-opens the
§16.3 adoption case with intraday evidence; a fail closes the residual
question at every measured horizon (daily campaign 2 + this).
**Applied verbatim 2026-07-27: A ∧ C ∧ D ∧ E pass, B fails → RECORD,
HOLD (see the top of this file).**

Smoke evidence the machinery measures what it should (2026-07-27, one
day, 3 instants, hl 0.1): post-lit async_once differs from async_dark by
up to 106bp and reduced |res_atm| on every matched row — and the
identical-rows bug that preceded it (wall-clock ages demoting every
anchor, store never written) is fixed + test-locked
(`tests/test_graph_intraday_replay.py`).

## Run (USER'S WINDOW — hours; tool background jobs get killed)

```powershell
powershell -ExecutionPolicy Bypass -File backend\backtest\run_dynamic_intraday.ps1
# then:
cd backend ; ..\.venv\Scripts\python -m backtest.graph_intraday report
```

Optional richer universe (single names vs SPY, new capture first —
needs VOLFIT_MASSIVE_KEY; ~30s/instant/ticker):

```powershell
cd backend
..\.venv\Scripts\python -m backtest.capture_intraday_rest --start 2026-07-20 --end 2026-07-24 `
    --tickers SPY,NVDA,AAPL --db backtest\results\intraday_names.sqlite
powershell -ExecutionPolicy Bypass -File backend\backtest\run_dynamic_intraday.ps1 `
    -Db backtest\results\intraday_names.sqlite -Tickers SPY,NVDA,AAPL
```

(NB the intraday capture ladder is 0-7 DTE + 2 monthly anchors —
adequate for shared weekly expiries; a full term-ladder capture is a
separate extension, see the survey note in the session wrap.)
