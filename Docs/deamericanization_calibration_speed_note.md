# De-Americanization and Calibration Throughput

*Technical note - 2026-06-20. This note explains how American-option quote
preparation currently affects the local-vol calibration path, quantifies the
cost on the Bloomberg fixture, and proposes a staged roadmap for making it
faster without weakening the price-quality contract.*

> **Implementation status (2026-06-21).** Stages 0–2 SHIPPED.
> - **Stage 1** — `BATCH_BISECTIONS 45 → 24` (`core/american.py`). Isolated de-Am
>   perf rail **825 ms → 390 ms (~2.1×)**; IV drift vs the 45-bisection baseline
>   locked `< 0.01 vol bp` (`test_quotes_deam.test_batch_bisections_24_matches_45_baseline`).
> - **Stage 2** — `service._prepared_key` is now a **content digest** of the actual
>   resolved de-Am inputs (forward, discount, cash-dividend schedule, `t`, `tau`,
>   as-of) instead of the broad global version counters. Fit-only tuning (grid,
>   roughness, var-swap, calendar) no longer re-runs de-Am, and the key is
>   ticker-scoped (one ticker's forward edit no longer busts another's prepared
>   quotes). Invalidation table: `test_prepared_cache_key.py` (6).
> - **Stage 0** — drift + invalidation rails added above (a full Bloomberg
>   `prepare_quotes` timing rail remains a nice-to-have).
> - **Not yet done:** Stages 3 (pre-filter), 4 (Numba kernel), 5 (selective
>   parallelism), 6 (analytic American), 7 (cross-update reuse), 8 (research).
> Full suite **639 passed, 1 skipped**; ruff + strict-TS green.

---

## 1. Executive summary

De-Americanization is currently a material part of the calibration process, even
though it happens before the local-vol optimizer starts. For an American equity
chain, `prepare_quotes` selects the OTM side, estimates and strips early-exercise
premium from bid/mid/ask, then inverts the resulting pseudo-European prices into
total variance points. That step is intentionally conservative and well tested,
but it is expensive enough to dominate user-perceived latency when a wide chain
is fetched or recalibrated repeatedly.

The main measured datapoint is the Bloomberg SPY fixture:

```text
SPY, 5 expiries, 2122 raw option rows
prepared quote time across expiries: about 10.9 s
local perf rail deamericanize_chain: 825 ms / 1800 ms budget
```

The highest-confidence improvement is to reduce the batch de-Am implied-vol
bisection count. The current default, 45 bisections, solves far beyond the
precision needed by the calibration. On the worst SPY expiry in the fixture,
keeping the same 192-step CRR tree but dropping to 24 bisections was about 1.8x
faster with effectively zero implied-volatility drift versus the current
baseline.

The proposed build order is:

1. Reduce batch bisections from 45 to about 24, with explicit IV-drift tests.
2. Narrow prepared-quote cache invalidation so fit-only changes do not rerun
   de-Americanization.
3. Add conservative pre-filters before CRR inversion.
4. Move the CRR/bisection kernel to Numba with a pure-Python fallback.
5. Parallelize prepared-quote work only above a measured size threshold.
6. Benchmark analytic American approximations as optional fast paths for
   continuous-yield, non-cash-dividend cases.
7. Reuse de-Am work across unchanged chains and warm brackets across small quote
   updates.

The main non-goal: do not reduce the CRR tree depth by default yet. Lower tree
depths are much faster, but the fixture showed visible IV drift at 128 steps and
below. The default path should first remove over-solving and cache churn before
touching numerical fidelity.

---

## 2. Current code path

The relevant pipeline is:

```text
raw option rows
  -> resolve forwards/discounts/dividends
  -> select OTM call/put side
  -> de-Americanize American rows
  -> static bounds and wing filtering
  -> Black inversion to total variance
  -> local-vol calibration inputs
```

Code map:

| Concern | File |
|---|---|
| CRR American/European pricing and batch de-Am | `backend/volfit/core/american.py` |
| Quote preparation and early-exercise-premium stripping | `backend/volfit/api/quotes.py` |
| Forward debiasing for American put-call parity | `backend/volfit/data/forwards.py` |
| Cash-dividend model and forward-consistent schedules | `backend/volfit/data/dividends.py` |
| Prepared quote cache key and local-vol orchestration | `backend/volfit/api/service.py` |
| Global versions and prepared cache storage | `backend/volfit/api/state.py` |
| Performance rail | `backend/tests/test_perf.py` |
| De-Am contract tests | `backend/tests/test_quotes_deam.py`, `backend/tests/test_discrete_deam.py`, `backend/tests/test_american.py` |

Important implementation details:

- `backend/volfit/core/american.py` has `DEFAULT_BATCH_STEPS = 192` and
  `BATCH_BISECTIONS = 45`.
- `deamericanize_batch` solves, per quote, for the volatility that makes a CRR
  American price match the observed American price, then returns the
  corresponding European Black price.
- `quotes._early_exercise_premiums` applies that to bid, mid, and ask by
  subtracting the estimated early-exercise premium.
- `prepare_quotes` runs de-Am after OTM-side selection but before the later
  static-bound and wing filters.
- Forward extraction has a separate coarse de-Am refinement so American put-call
  parity does not bias the resolved forward.
- Discrete cash dividends are supported through an escrowed-Hull-style CRR
  schedule, with cash amounts scaled to be forward-consistent.

The correctness baseline is good and should be preserved. Tests already cover
batch/scalar consistency, known-smile recovery, forward debiasing, and the
important cash-dividend kink case where continuous-yield de-Am is not enough.

---

## 3. What de-Americanization is doing

For each selected American option quote, the code conceptually computes:

```text
given: observed American price A_obs
find:  sigma* such that CRR_American(S, K, T, r, q/divs, sigma*) = A_obs
return: European pseudo-price E = Black_European(S, K, T, r, q, sigma*)
```

The early-exercise premium estimate is:

```text
EEP = A_obs - E
```

The quote-prep code strips that premium from bid, mid, and ask before applying
the European static-arbitrage and implied-vol machinery.

This is the usual industry workflow: convert American quotes to pseudo-European
quotes, then calibrate the European-style model. The tradeoff is that the CRR
tree is run many times during quote preparation: one batch inversion has a tree
price inside every bisection, for every quote in the expiry.

In current defaults, each batch is roughly:

```text
192 time steps * 45 volatility bisections * number of OTM rows
```

The implementation is vectorized across quotes, so that expression is not a
literal Python loop count, but it is still the right mental model for cost.

---

## 4. Measured workload on the Bloomberg fixture

The fixture used for this analysis was:

```text
backend/tests/fixtures/lv_benchmark_bloomberg.json
```

SPY:

| Expiry | Raw OTM rows sent to de-Am | Prepared rows retained | prepare_quotes wall time |
|---|---:|---:|---:|
| 2026-07-17 | 238 | 165 | 2202.5 ms |
| 2026-08-21 | 242 | 189 | 2081.9 ms |
| 2026-09-18 | 305 | 267 | 2571.8 ms |
| 2026-12-18 | 126 | 103 | 1193.2 ms |
| 2027-06-17 | 142 | 136 | 1189.7 ms |
| **Total** | **1053** | **860** | **10239.1 ms** |

The same run was described as about 10.9 s end-to-end across the five expiries
depending on local run noise and measurement wrapper. The important conclusion is
stable: quote preparation can consume many seconds before the local-vol
calibration optimizer begins.

NVDA:

| Expiry | Raw OTM rows sent to de-Am | Prepared rows retained | prepare_quotes wall time |
|---|---:|---:|---:|
| 2026-07-17 | 42 | 34 | 494.8 ms |
| 2026-09-18 | 40 | 40 | 496.8 ms |
| 2026-12-18 | 114 | 114 | 1218.6 ms |
| **Total** | **196** | **188** | **2210.2 ms** |

The existing perf rail also passes comfortably:

```text
pytest tests/test_perf.py -k deamericanize_chain -q -s
deamericanize_chain 825.3 / 1800.0 ms (46% of budget)
```

That perf rail is healthy, but it is narrower than the full user path: the full
path prepares several expiries and can rerun when cache keys are invalidated.

---

## 5. Bisection precision experiment

The strongest near-term finding came from varying bisection count and tree depth
on the worst SPY expiry, 2026-09-18, with 305 rows. The baseline was the current
default:

```text
192 CRR steps / 45 bisections
```

Comparison:

| Variant | Wall time | Speedup | Max IV drift vs baseline | p99 IV drift | Median IV drift |
|---|---:|---:|---:|---:|---:|
| 192 steps / 45 bisections | 2998.0 ms | 1.00x | baseline | baseline | baseline |
| 192 / 32 | 2231.1 ms | 1.34x | 0.000 vol bp | 0.000 vol bp | 0.000 vol bp |
| 192 / 28 | 1800.4 ms | 1.67x | 0.000 vol bp | 0.000 vol bp | 0.000 vol bp |
| 192 / 24 | 1676.8 ms | 1.79x | 0.000 vol bp | 0.000 vol bp | 0.000 vol bp |
| 192 / 22 | 1568.2 ms | 1.91x | 0.001 vol bp | near zero | near zero |
| 128 / 24 | 720.2 ms | 4.16x | 14.922 vol bp | 10.681 vol bp | 1.881 vol bp |
| 96 / 24 | 392.4 ms | 7.64x | 25.341 vol bp | 18.339 vol bp | larger |
| 64 / 24 | 193.6 ms | 15.49x | 41.884 vol bp | larger | larger |
| 48 / 20 | 102.5 ms | 29.26x | 61.127 vol bp | larger | larger |

Interpretation:

- The current 45 bisections are solving to unnecessary precision.
- Reducing bisections to 24 keeps the 192-step CRR discretization unchanged and
  should be low risk.
- Reducing tree depth is much more attractive on speed but changes the numerical
  target. It belongs behind an explicit fast/rough mode, not as a default change.

Recommendation:

```text
Default candidate: 192 steps / 24 bisections
Aggressive candidate after tests: 192 steps / 22 bisections
Do not change default CRR steps yet.
```

---

## 6. Why not skip de-Americanization?

The fixture does not support a blanket skip. Early-exercise premium is often
small for calls and short-dated low-dividend cases, but puts, longer maturities,
rates, and cash dividends can make it material.

Empirical observation from the fixture:

- SPY has many rows with meaningful EEP, especially at longer expiries.
- NVDA front expiry has only a few rows above one cent of EEP, but later expiries
  have more.
- The cash-dividend tests show that a continuous-yield approximation can leave an
  ATM kink, while the discrete schedule removes it.

Therefore, the right optimization is not "skip American adjustment"; it is:

```text
skip only rows that are provably irrelevant,
reuse work when inputs are unchanged,
and solve the necessary American inversions less expensively.
```

---

## 7. Cache invalidation problem

The prepared quote cache is supposed to avoid repeating quote preparation,
including de-Am. The cache is version-keyed, which is correct in spirit, but the
current key is broader than the data actually needed for prepared quotes.

Current issue areas:

- `service._prepared_key` includes broad settings/options/event/forward/data
  versions.
- `state.settings_version` increments on any `FitSettings` change.
- `state.options_version` includes several fit-affecting options that do not
  alter prepared quotes.
- `state.forwards_version` is global, so a forward-policy change for one ticker
  can invalidate prepared quote work for other tickers.

This matters because the de-Am cost is paid again whenever the prepared key
changes, even if the raw chain, forwards, discounting, dividends, and quote-prep
semantics are effectively unchanged.

Prepared quotes should depend on:

```text
ticker
reference date
raw option chain identity/content
resolved forward and discount for the expiry
dividend/cash schedule used by de-Am
events settings only if they alter quote-prep tau or filtering
quote-prep settings that affect filtering or inversion
implementation version for the de-Am algorithm
```

Prepared quotes should not depend on:

```text
local-vol grid size
roughness weight
var-swap inclusion
calendar penalty
prior-surface anchor
optimizer tolerances
display-only settings
```

The roadmap should introduce either:

1. a separate prepared-quote version key, or
2. a structured prepared-input digest.

The digest approach is more precise and easier to reason about in tests.

---

## 8. Roadmap

### Stage 0 - Guardrails and measurement

Status: mostly present; add a few de-Am-specific rails.

Existing useful tests:

- `test_american.py`: scalar/batch invariants.
- `test_quotes_deam.py`: known smile recovery and American-vs-naive behavior.
- `test_forward_debias.py`: forward extraction debiasing.
- `test_discrete_deam.py`: cash-dividend de-Am contract.
- `test_perf.py`: `deamericanize_chain`.

Add or sharpen:

- A regression fixture that compares current default de-Am output to proposed
  192/24 output and asserts max IV drift within a tiny tolerance.
- A full `prepare_quotes` timing rail across the Bloomberg SPY fixture, because
  the existing chain perf rail is smaller than the real user path.
- Diagnostic counters: raw rows, OTM rows, rows de-Amed, rows retained, rows
  rejected by reason, and de-Am wall time by expiry.

Acceptance gate:

```text
No quote-quality regression.
Perf rail records both isolated de-Am and full prepare_quotes time.
```

### Stage 1 - Reduce batch bisections

Change:

```text
BATCH_BISECTIONS: 45 -> 24
DEFAULT_BATCH_STEPS: unchanged at 192
```

Why first:

- It is the smallest behavior change.
- It targets pure numerical over-solving.
- It does not change tree discretization, dividend logic, or quote filtering.
- The measured speedup was about 1.8x on the worst SPY expiry.

Tests:

- Batch/scalar consistency still passes.
- Known-smile recovery remains within existing tolerances.
- Discrete cash-dividend kink test remains green.
- New IV-drift test versus old 45-bisection baseline.

Acceptance gate:

```text
Max IV drift versus 45-bisection baseline <= 0.01 vol bp on fixtures.
deamericanize_chain perf improves materially.
No change to prepared row counts.
```

Possible refinement:

- If 24 is comfortably inside tolerance, evaluate 22 as the next step.
- Keep 24 as the conservative default unless repeated fixtures show 22 is
  equally invisible.

### Stage 2 - Narrow prepared-quote cache invalidation

Change:

- Split prepared-quote cache invalidation from fit/cache invalidation.
- Replace broad global versions with a prepared-input digest.
- Make forward and event invalidation ticker-scoped where possible.

Example digest fields:

```text
{
  ticker,
  reference_date,
  raw_option_chain_digest,
  expiry,
  forward,
  discount,
  carry_or_dividend_schedule_digest,
  events_quote_prep_digest,
  quote_filtering_digest,
  deam_algorithm_version
}
```

Why second:

- It avoids paying de-Am repeatedly while users tune local-vol options.
- It has no intended numerical effect.
- It helps every later optimization by making reuse more predictable.

Tests:

- Changing grid density should not invalidate prepared quotes.
- Changing roughness should not invalidate prepared quotes.
- Changing var-swap settings should not invalidate prepared quotes.
- Changing raw options, forward policy, dividends, or events that affect tau
  should invalidate prepared quotes.
- Changing one ticker's forward settings should not invalidate another ticker's
  prepared quotes.

Acceptance gate:

```text
Prepared quote cache hit rate improves during option-tuning workflows.
All invalidation tests are explicit and readable.
No stale prepared quotes after raw chain or forward/dividend changes.
```

### Stage 3 - Conservative pre-filter before CRR

Change:

- Move cheap rejects before de-Am where they are independent of the
  de-Americanized price.
- Add a conservative pre-wing screen with a buffer, then keep the existing final
  post-de-Am filters.

Candidate pre-filters:

- finite positive bid/mid/ask
- non-crossed bid/ask
- OTM-side selection, already present
- obvious outside-wing moneyness using a wide buffer
- tiny-vega rows that cannot influence calibration materially
- duplicate or stale strike rows, if present in vendor data

Why third:

- The SPY fixture de-Amed rows that were later dropped.
- On the front SPY expiry, 238 rows were de-Amed but only 165 survived.
- A pre-filter does not need to be aggressive to save real time.

Risk:

- Filtering before de-Am can accidentally drop rows whose de-Am adjustment would
  move them back into bounds.

Mitigation:

- Use a generous buffer.
- Keep existing post-de-Am filters as the final authority.
- Add a debug mode that reports rows saved and rows that would have survived
  under the old path.

Acceptance gate:

```text
Prepared row set unchanged on current fixtures, or differences are reviewed and
explained.
Rows sent to de-Am decrease on wide chains.
No loss of quote coverage near ATM or in calibration-relevant wings.
```

### Stage 4 - Numba CRR and de-Am kernel

Change:

- Implement a compiled CRR/bisection path using `numba.njit(cache=True,
  nogil=True)`.
- Keep the current NumPy/Python path as a fallback.
- Avoid per-bisection temporary allocations where possible.

Why fourth:

- After bisection reduction and cache fixes, the remaining necessary CRR work is
  still large.
- Numba is already used in the local-vol stack, so this is consistent with the
  repo's performance direction.
- `nogil=True` enables useful threaded concurrency later.

Design sketch:

```text
deamericanize_batch(...)
  if numba_available and input shape supported:
      return deamericanize_batch_numba(...)
  return deamericanize_batch_numpy(...)
```

Kernel responsibilities:

- CRR backward induction for calls and puts.
- Escrowed discrete cash-dividend adjustment.
- Vectorized or parallel quote loop.
- Fixed bisection count.
- Robust handling of impossible/no-arbitrage inputs.

Tests:

- Numba output equals current path within tight price/IV tolerance.
- Fallback path still works without Numba.
- Cash-dividend tests run through both paths when possible.
- Cache warmup does not pollute timing rails.

Acceptance gate:

```text
No numerical contract change.
At least 2x speedup over 192/24 NumPy path on wide chains after JIT warmup.
No first-call compile cost is counted in steady-state perf rails.
```

### Stage 5 - Selective parallel prepared-quote work

Change:

- Parallelize per-expiry preparation only when the chain is large enough.
- Prefer threads after the Numba path releases the GIL.
- Keep sequential behavior for small chains.

Observed experiment:

```text
SPY sequential expiry prepare: about 10.9 s
SPY threaded expiry prepare:   about 8.2 s
NVDA sequential:               about 2.5 s
NVDA threaded:                 about 3.7 s
```

Interpretation:

- Threading helps large/wide chains but hurts small chains.
- A threshold is required.
- The threshold should be based on number of expiries and total rows sent to
  de-Am.

Candidate rule:

```text
if american and expiry_count >= 4 and otm_rows_to_deam >= 500:
    use bounded thread pool
else:
    prepare sequentially
```

Acceptance gate:

```text
SPY-like chains improve.
NVDA-like chains do not regress.
Errors preserve expiry context and remain deterministic enough to debug.
```

### Stage 6 - Optional analytic American approximations

Change:

- Benchmark Barone-Adesi-Whaley, Bjerksund-Stensland, and Ju-Zhong style
  approximations as optional fast paths.
- Restrict candidates to continuous-yield cases without discrete cash schedules.
- Keep CRR as the correctness fallback.

Why not earlier:

- These approximations change the numerical American pricing target.
- They are fast, but they require careful validation across rate, dividend,
  maturity, and moneyness regimes.
- The current discrete-cash-dividend path is a key feature and should not be
  approximated casually.

Possible use cases:

1. Fast path when approximation and CRR agree within a small EEP tolerance on
   sentinel strikes.
2. Initial volatility bracket/seed for CRR bisection.
3. Explicit "fast de-Am" mode for interactive rough calibration.

Acceptance gate:

```text
Approximation never silently replaces CRR outside validated regimes.
Continuous-yield fixtures show material speedup with sub-bp IV drift.
Discrete-cash-dividend chains stay on CRR by default.
```

### Stage 7 - Reuse across quote updates

Change:

- Cache de-Am results by a chain/expiry digest, not just by broad application
  versions.
- If only mids move slightly while strikes/forwards/dividends are stable, reuse
  previous solved volatilities as brackets or seeds.

Why:

- Vendor refreshes often keep strike grids stable.
- Users often tune local-vol settings without changing raw market data.
- Reusing solved American vols can reduce bisection work even when exact prices
  changed.

Potential digest:

```text
expiry
S/F/discount/dividend schedule
strike
call_put
bid/mid/ask rounded to vendor precision
deam algorithm version
```

Acceptance gate:

```text
Exact chain repeat gives near-zero de-Am cost.
Small quote update uses warm brackets but still converges to the same result as
cold bisection.
Cache memory remains bounded by ticker/session.
```

### Stage 8 - Research track: shape-aware de-Am or direct American calibration

This should not be on the immediate implementation path, but it is worth naming.

The literature notes that standard binomial de-Americanization typically fits
each quote independently under simplified assumptions. That is fast and widely
used, but it ignores the shape of the surrounding volatility surface. Recent work
explores neural-network de-Americanization that uses more surface context. A
more radical alternative is to calibrate directly to American prices.

These are interesting, but they are not near-term speed wins:

- They expand the model contract.
- They require new validation data.
- They make explainability harder.
- They risk mixing quote-cleaning concerns with local-vol calibration concerns.

Recommendation:

```text
Keep pseudo-European quote preparation as the production path.
Treat shape-aware de-Am as research only.
Do not move local-vol calibration itself to American exercise until the current
European-style path is faster and better instrumented.
```

---

## 9. Acceptance gates by risk

Low-risk gates:

- `BATCH_BISECTIONS` reduction has negligible IV drift.
- Prepared cache key changes produce intended hit/miss behavior.
- No prepared row count changes unless explicitly expected.

Medium-risk gates:

- Pre-filtering saves work without losing calibration-relevant rows.
- Numba path matches NumPy path across cash-dividend and continuous-yield cases.
- Threaded path improves large chains without regressing small chains.

High-risk gates:

- Analytic approximation fast paths match CRR in every enabled regime.
- Any rough/fast mode is visibly opt-in and never used for default calibration.

Suggested fixture set:

```text
SPY Bloomberg wide chain
NVDA Bloomberg shorter chain
synthetic flat smile with American puts
synthetic high-rate case
synthetic cash-dividend case with ATM kink risk
deep ITM put stress
short-dated near-expiry stress
```

---

## 10. Expected impact

Conservative stacked estimate for a wide American chain:

| Change | Expected impact | Notes |
|---|---:|---|
| 45 -> 24 bisections | about 1.7x to 1.9x on de-Am batches | measured directly |
| Better cache invalidation | workflow-dependent | can eliminate repeated de-Am entirely during fit tuning |
| Pre-filter before CRR | 10% to 30% on wide chains | depends on vendor row quality and wing width |
| Numba kernel | 2x+ after warmup target | needs implementation proof |
| Selective parallelism | 1.2x to 1.5x on large chains | thresholded; small chains stay sequential |

The first two stages are the most important because they reduce wasted work:

```text
Stage 1 removes numerical over-solving.
Stage 2 avoids repeating the work when nothing quote-prep-relevant changed.
```

If only Stage 1 ships, the SPY full prepare path should plausibly move from
about 10-11 seconds toward about 6 seconds, all else equal. If Stage 2 also
ships, repeated local-vol option tuning should avoid most of that cost entirely.

---

## 11. Sources and external context

The external literature supports the current architecture but also explains its
limits:

- Burkovska et al., *Calibration to American Options: Numerical Investigation of
  the de-Americanization Method*, describe the common workflow of converting
  American quotes to pseudo-European prices before calibration, while warning
  that the method is pragmatic rather than theoretically guaranteed.
  <https://arxiv.org/abs/1611.06181>
- Barone-Adesi and Whaley's quadratic approximation is a standard fast analytic
  American-option approximation.
  <https://ideas.repec.org/a/bla/jfinan/v42y1987i2p301-20.html>
- Bjerksund and Stensland propose efficient closed-form lower-bound
  approximations based on exercise-boundary assumptions.
  <https://derivativesacademy.com/storage/uploads/files/modules/resources/1703192811_bjerksund_stensland_2002_closed_form_valuation_of_american_options.pdf>
- Ju and Zhong improve analytic approximation accuracy while keeping the
  computation much cheaper than numerical trees in many regimes.
  <https://www.deriscope.com/docs/Ju_1999.pdf>
- Lind and Gatheral explore neural-network de-Americanization that uses more
  volatility-surface context than quote-by-quote binomial stripping.
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4616123>
- Numba's `nogil` and `cache` options are relevant for a compiled CRR kernel and
  later thread-level parallelism.
  <https://numba.pydata.org/numba-doc/dev/user/jit.html>

The practical conclusion for this codebase is not to replace the current
de-Americanization model immediately. It is to make the existing model solve
only to useful precision, cache it more accurately, and compile the remaining
necessary work.

