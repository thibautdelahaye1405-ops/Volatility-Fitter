# Dynamic-harmonic intraday async replay — pre-registered design & gate

**Status: MACHINERY COMPLETE 2026-07-27; CAMPAIGN = USER ACTION.**
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

## Pre-registered gate (fill from `report`; async_once post phase,
## all-pairs, both R)

| gate | criterion                                                        | verdict |
|------|------------------------------------------------------------------|---------|
| A    | some finite-H layered arm post-lit ATM RMS < memoryless AND < desk (an INTERIOR optimum exists intraday) |  |
| B    | that arm also < base AND < msg on the same rows                  |  |
| C    | first post-lit bucket (0-0.75h) shows the largest memory skill, decaying by bucket (§16.2 persistence shape) |  |
| D    | ζ std ∈ [0.8, 1.3] and cov80/cov95 near nominal on post rows     |  |
| E    | async_dark rows ~invariant across layered arms (internal consistency — no residual exists there by design) | check |

**Decision rule (pre-registered):** the intraday residual state is
declared VALUABLE only on A ∧ B ∧ D (C reported as shape evidence).
A pass does NOT flip any production default by itself — it re-opens the
§16.3 adoption case with intraday evidence; a fail closes the residual
question at every measured horizon (daily campaign 2 + this).

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
