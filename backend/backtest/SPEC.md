# Backtest harness — capture & compute specification

What the overnight backtest captures and computes, end to end. Source of truth:
`backtest/universe.py` (sample set), `backtest/capture.py` (capture),
`backtest/dispatch.py` + `run_compute.py` (compute). Production defaults are read
from `volfit.api.schemas` (FitSettings / OptionsSettings) so the harness mirrors the
app.

---

## 1. What is being CAPTURED

### Assets
Display ticker → OCC option roots (index options need several) → exercise style.

| set | tickers |
|---|---|
| **Pilot (8)** | SPX, NDX, RUT (indices, **European**, roots SPX+SPXW / NDX+NDXP / RUT+RUTW), EEM, EFA (ETFs, **American**), AAPL, NVDA, JPM (single names, **American**) |
| **Full (25)** | + MSFT, AMZN, GOOGL, META, AVGO, TSLA, BRK.B (mega-caps) and XOM, CVX, LLY, UNH, WMT, COST, HD, CAT, GS, NFLX (sector breadth) |

### Periods / days
Three regimes (one snapshot per trading day = weekdays in the window):

| regime | window | trading days | character |
|---|---|---|---|
| `spike_aug2024` | 2024-07-29 → 2024-08-23 | ~20 | yen-carry vol spike + fast snapback |
| `high_oct2022` | 2022-09-26 → 2022-10-21 | ~20 | sustained-high bear lows |
| `low_jul2023` | 2023-07-17 → 2023-08-11 | ~20 | low / stable (~VIX 13–14) |

Pilot = `spike_aug2024` only. (Low/stable relaxed to 2023; true sub-12 VIX needs
pre-2021, where the quotes tier thins out.)

### Daily snapshot
**15:45 ET ("before close")** — tight two-sided markets, not the noisy official
print. One instant per day, resolved to UTC with DST handled via the IANA tz db.

### Fields per quote (real NBBO)
From the Massive/Polygon **`quotes_v1`** flat files (the OPRA NBBO firehose):
- **bid** and **ask** (the contract's last NBBO at-or-before 15:45 ET), plus ask size;
- **mid** = (bid+ask)/2, derived (one-sided / crossed dropped);
- **spot** = put-call-parity forward proxy from the reconstructed mids;
- a 0 bid is treated as "no bid" (one-sided → dropped).

### Strikes & expiries
- **All strikes** present in OPRA for the selected expiries (calls **and** puts).
  The deep-wing filter (|k| ≤ 4·√w_atm) is applied later, at FIT time, by the
  production `prepare_quotes` — capture stores the full set.
- **Expiry ladder** per (asset, date): all in-range 3rd-Friday **monthlies** + the
  nearest **3 weeklies**, DTE ∈ [7, 400], capped at **10** expiries.

### Stored (immutable JSON per (asset, date))
spot · exercise style · sector · expiry list · **parity forwards** per expiry
(forward, discount, n_strikes, parity residual RMS, n_outliers — de-biased for
American exercise) · the **raw NBBO quotes** (bid/ask/ask_size). De-Americanization
is NOT applied at capture (it is a compute-time, model-independent step).

---

## 2. What is being COMPUTED

### Parametric model sweep (per smile slice)
Each node is de-Am'd + inverted **once**, then every model is calibrated directly
(clean per-model timing). 10 models:

| model | free params | knob |
|---|---|---|
| **SVI-JW** (baseline) | 5 (raw a,b,ρ,m,σ) | — |
| LQD-6 / 8 / 10 / 12 | Legendre order N (≈ N−1 interior coeffs + 2 endpoint tail scales) | order N |
| SIV-0 | 6 (base Multi-Core SIV: v0,s0,k0,z0,κ_p,κ_c) | base only |
| SIV-1 / 2 / 3 | 6 + R zero-wing "hat" cores | core count R |

(SIV-4 dropped: ~8.6 s/fit with no precision gain over SIV-3.)

### Local-Vol surface (per asset, all expiries jointly)
Piecewise-**affine local-variance** surface on a **delta-spaced strike grid × √T
time grid**, default floor **12 × 10 ≈ up to ~120 nodal variances**, calibrated by
the **Dupire forward PDE** (arb-free by construction). One surface fit per (asset,
date).

### Hyperparameters (production defaults — the harness uses these verbatim)

| group | setting | value |
|---|---|---|
| LQD | regLambda (n^{2r} damping) / regPower r | 1e-6 / 1.0 |
| LQD | A_R soft barrier center / scale | 0.90 / 50.0 |
| SVI | no-arb penalty weight / Lee slope max | 1e3 / 2.0 |
| SIV | hat-amplitude ridge | 1e-2 |
| all | band-mode mid-anchor weight | 0.05 |
| LV grid | strike nodes (floor, delta-spaced) / time nodes (floor, √T) | 12 / 10 |
| LV | convex wing / front tie / left-wing slope× / vol-cap× | off / on (1e-2) / 1.5 / 3.0 |
| LV | roughness reg λ / ρ (time–strike balance) | 1e-4 / 1.0 |

### The other levers
- **Fit target:** run under **both** `mid` and `haircut(0.5)`. The haircut is a
  *fractional* 50% band — each side moved halfway from the quote (bid/ask) toward
  mid, per-quote and spread-aware (the engine's `haircut` field is absolute vol
  points; the harness builds the fractional band directly). Mid scores model−mid;
  haircut scores band violation (≈0 inside band). Every (weight × fit-target)
  combination is a separate result table.
- **Forward:** parity-implied, **American-de-biased** per expiry (discount from
  parity). Theoretical (dividend-model) and manual overrides available, unused here.
- **Quote weighting:** run under **both** `equal` and `tv_density` (time-value
  density — down-weights illiquid deep wings toward the tradable core). tv_density is
  the production-representative precision metric.
- **Arb-fix:** *static* (butterfly) is measured per slice via the Durrleman g(k)
  no-arbitrage functional (g<0 ⇒ arb), plus LQD's exact martingale-mass check. The
  LV surface enforces no-arb jointly (Dupire). NOTE: *calendar* (across-expiry
  w_far ≥ w_near) coupling is NOT applied in the per-slice parametric sweep (each
  slice fit independently); it is an available app fit-mode and a planned sweep axis.
- **De-Am:** binomial (CRR) inversion of the American chain to European-equivalent;
  timed and attributed (model-independent, ~0 for European indices).

### Metrics recorded (per fit, → JSON table)
- **Parametric:** in-sample RMS (bp, weighted), **out-of-sample RMS** (leave-every-
  3rd-strike-out, refit), max error, optimizer eval count, **prep_ms** (de-Am +
  inversion) vs **fit_ms**, butterfly min-g + negative-grid fraction, LQD martingale
  deviation, n quotes, n de-Am'd, exercise style, regime, sector, weight scheme.
- **Local-Vol:** surface RMS + per-expiry RMS/max-err, vertex count, nfev / max-nfev
  (+ hit flag), Jacobian evals, solver status, active-bound count, wall-time split
  (total / PDE value / PDE sensitivity / assembly / optimizer).

The report (`analyze.py`) renders the model **Pareto vs SVI-JW** (precision + speed +
arb), the **time attribution** (de-Am vs fit, split by exercise style), and the
**break inventory** (fit failures, butterfly-arb slices, RMSE z>3 outliers).

---

## 3. GRAPH extrapolation (planned — Phase 6, runs once ≥2 days are captured)

- **Leave-one-node-out** over validation-clean nodes: hold a calibrated node out of
  the graph solve, predict its smile from the rest, score the residual + standardized
  residual; aggregate RMSE (bp) and ζ mean/std (calibration of the uncertainty).
- **Baseline = transported prior.** Each node's prior is resolved by the locked
  hierarchy active_transported → nearest_expiry_transported → today_bootstrap →
  flat_atm; graph-posterior is compared against this transported-prior baseline.
- **Temporal protocol:** for date D, date **D-1's** calibration is loaded as the
  active prior (else every node is bootstrap = excluded as circular).
- **Transport / SSR assumption:** the prior is moved to the current forward by the
  total-variance horizontal shift **w₁(k) = w₀(k + R·h)**, with h the forward
  log-ratio. The LOO runs under **both** transport regimes:
  **sticky-moneyness** (R = 0 — the smile in moneyness is unchanged) and
  **SSR = 1.0** (R = 1). Each regime yields its own LOO calibration vs the
  transported-prior baseline.
- **Precision model:** observation precision = 1/rms² × quote-density × bid-ask ×
  freshness; baseline precision = provenance-tier × age × transport-distance. Per-edge
  **β** scales the directed increment amplitude (separate from edge trust/weight).

---

## 4. Schedule (nightly window)

The capture runs **only 23:30 → 06:30 local time** (`--window 23:30-06:30`) so the
machine is free during the day. Granularity is **per day**: a day already scanning
when 06:30 passes **runs to completion** (never killed mid-scan — that would waste
the partial download, since the per-day cache writes only on completion); no **new**
day starts outside the window. Fully resumable (captured days are skipped).

**Cost reality:** the `quotes_v1` day-file is a single non-splittable gzip (the OPRA
firehose). The Aug-5-2024 spike day took **~8.85 h** to scan; other days are hours
too. So one 7-hour window likely **cannot finish a full day** — expect ~1 day per
night with some morning overrun, i.e. the 20-day pilot spans ~3 weeks of nights. If
that is too slow, the alternative is per-contract REST quotes at the 15:45 timestamp
(thousands of small calls, potentially minutes/day) — needs a rate-limit probe.
