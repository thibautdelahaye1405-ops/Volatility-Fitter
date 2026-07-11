# Trader due-diligence Q&A — answers with evidence, and slide amendments

Prepared 2026-07-09 against deck REV 6 (`volfitter_deck.html`). Each answer cites the
module / note / findings file that backs it, and flags where the honest answer is a
known gap. Amendment recommendations are collected at the end.

---

## Slide 3 — Architecture: where can a trader override, and is it persisted/audited?

**Answer.** Overrides exist at every pipeline stage:

- **Quotes**: exclude / include / amend-mid per quote, per node, with bounded undo/redo
  and a minimum-5-included-quotes guard (`volfit/api/session.py`, `edits.py`).
- **Targets & weights**: fit target mid / band / haircut (haircut margin is a dial),
  weight scheme equal / tv-density (`calib/band.py`, `weights.py`).
- **Inputs**: dividend editor per ticker, event clock, var-swap quote per node (own
  undo/redo, `varswap_session.py`), spot slider / scenario regime.
- **Model & hyperparameters**: the whole Options tab (`OptionsSettings`), persisted.
- **Priors**: save prior, 7-mode menu, operator strengths, gate parameters.
- **Graph**: lit/dark per node, persisted edge editor (weights + β), η auto-tune.
- **Tails**: wing priors on A_L/A_R, `extrapEnforce` opt-in, LV put-wing slope.

**Persistence**: settings, priors, universes, graph-edge overrides, and *every fit*
(keyed by chain-snapshot timestamp) persist to SQLite when `VOLFIT_DB` is set
(`api/history.py`, `settings_persist.py`).

**Honest gap**: quote-edit sessions are in-memory only — no durable audit log of who
amended which quote when; graph-edge overrides persist as a last-saved blob, not a
version history. Auditability of *automated* decisions is strong (prior diagnostics
table, filter gain badge, graph attribution card); auditability of *manual* overrides
is the roadmap item.

---

## Slide 4 — Worked example

**Why +150 bp SPY?** It is a controlled, exactly-reproducible demo (synthetic feed),
sized to dominate quote noise so every arrow is legible — a pedagogical specimen, not
evidence. The evidence for the same mechanism on real history is slide 30's LOO
backtest (25 assets × 3 regimes, ~47k held-out scores). Note the demo is honest work:
SPY is genuinely recalibrated on the shifted quotes and the propagated object is the
*innovation* (+97…+151 bp), never the level.

**Stale, contradictory NVDA quotes?** Two cases. If NVDA stays *dark*, its quotes are
simply not used — the slide-28 caption already shows the posterior disagreeing with
the untouched quotes by ζ = −0.56, inside its own band, by design. If NVDA is *lit*
with bad quotes, containment applies twice: (i) its innovation enters the graph
weighted by the lit fit's own observation precision — rms × quote-density × spread ×
freshness (`graph/precision.py`) — so a noisy wide-band calibration propagates weakly;
(ii) upstream, the observation filter's residual inflation ρ = χ²/dof widens R when a
chain contradicts itself, cutting the gain on exactly the contaminated handles
(`calib/observation_measurement.py`).

**Is the ±1.9–2.0 vol-pt band OOS-calibrated?** In the demo it is internally
consistent (marginal posterior covariance). Out-of-sample calibration is measured in
the LOO backtest: standardized residuals ζ ≈ 0 with std 0.70–1.10 in most cells.
The one exception found — calm-regime fully-dark single names at std ≈ 1.9 (bands
too narrow) — is FIXED as of 2026-07-10: the idiosyncratic ATM-band floor
(`volfit/graph/idio.py`, on by default) moved those cells to std 1.02/1.03, validated
offline on the stored benchmark rows; skew/curvature band widening remains open (see
slide 30). Answer both halves; do not claim OOS calibration for the demo band itself.

---

## Slide 5 — Vocabulary: what happens when ζ is not normal?

**Answer.** ζ is a *measured audit*, not an assumption the system needs to hold.
Where non-Gaussianity shows up as fat-tailed innovations, the mechanisms that widen
uncertainty are variance-based, not distribution-based:

- Filter: innovation-gated adaptive inflation — a standardized innovation beyond the
  3σ gate inflates the predicted covariance by (ζ/gate)², capped 25×, so a genuine
  jump re-opens the gain (`calib/observation_filter.py`; validated: SPX shock win
  rate 0.42 → 1.00).
- Filter: ρ = χ²/dof residual inflation on R when the fit's residuals run worse than
  its stated spread noise.
- Graph: precision floors/caps and provenance/age/transport decay of the baseline.

There is **no automatic distribution-free band recalibration**; the guardrail is the
empirical ζ audit per regime and cell. The one dishonest cell it found (calm-regime
dark names, ζ std ≈ 1.9) is now closed at the ATM level by the idiosyncratic band
floor (`volfit/graph/idio.py`, shipped 2026-07-10, on by default: ζ std 1.91→1.02,
1.85→1.03, mean-invariant); skew/curvature widening in idiosyncratic tape is the
remaining open item.

---

## Slide 6 — LQD: empirical superiority, parameter stability, density constraints

**Empirical cases vs SVI.** Not "more flexible in the abstract": on 1,576 replayed
NBBO nodes (spike regime) LQD-12 fits 7.6 bp in-sample / 9.8 bp OOS vs SVI-JW
24.3/26.8 — OOS tracks in-sample, so the gap is signal SVI's 5 parameters cannot
express (index-chain curvature), not overfit. Consistent 0.31–0.45× across all three
regimes. Under the band target the gap widens (2.3/4.0 vs 12.8/15.5 bp). Plus two
structural wins: real butterfly-arb rate 0.0% (vs SVI 9.2% even after fencing) and
exact ATM handles feeding priors/filter/graph.

**Day-over-day stability.** Honest answer: raw LQD coefficients are non-unique (Note
01 §Limitations — higher Legendre orders can trade off), so stability is defined and
carried at the *handle* level (σ₀, s₀, κ₀ exact in closed form), which is what the
prior, filter and graph transport. Indirect temporal evidence is the consecutive-day
prior harness (1,116 nodes). **Gap**: no dedicated handle-drift-by-day table — a cheap
backlog item (the fits table already stores handles per snapshot).

**Constraints beyond positivity.** One hard constraint (A_R < 1, finite forward) plus
a softplus barrier at 0.90; a high-order ridge λ·n^{2r}·a_n² that suppresses
oscillation while leaving skew/curvature orders free; structural exponential tails
whose Lee slopes are reported per fit; optional wing priors and an exact closed-form
var-swap penalty pinning the tail-loaded integral. "Economically odd" shapes are
suppressed by the ridge and made *visible* by the reported A_L/A_R and g(k).

---

## Slide 7 — LQD backtest: split fairness and breakdowns

**Held-out strikes.** Deterministic leave-every-3rd-strike-out over the ordered strike
vector (`backtest/dispatch.py:_oos_rms_bp`), identical mask for every model, only on
chains with ≥ 9 quotes. It samples ATM and wings uniformly — not wing-biased, and it
cannot favor LQD's basis because the mask is model-agnostic. The fairness issue the
repo *did* find and fix was in the arb metric (FD noise), not the split.

**Breakdowns.** Every result row carries regime, sector, exercise style, asset,
expiry, tenor, quote count, weight scheme, fit target — so per-asset / expiry-bucket /
moneyness / liquidity-decile slices are one `analyze.py` extension away, but the
*shipped* report only aggregates by model and exercise style. Say so, and fold the
per-bucket report into the already-planned slide-7 refresh (footer promises it).

---

## Slide 8 — Distribution views: tail sensitivity and stability

**Sensitivity of digitals/tails to wing ticks.** Three dampers: (i) in band/haircut
mode a wing-mid twitch inside its spread costs the fit nothing (the band only stops
punishing), so tiny wing changes don't move the density at all; (ii) the tail is
two structural scales (A_L, A_R) under a ridge and barrier, not a local spline —
a single quote can't reshape it; (iii) tail scales and Lee slopes are printed with
every fit, so a tail move is observable, and a var-swap quote pins the tail integral
exactly (closed form). **Gap**: no formal digital-sensitivity study (∂digital/∂wing-
tick table) — a good backup-slide candidate.

**Trading vs diagnostic.** The density *is* the pricing object (closed-form
asset-share integral), so digitals/var-swaps are consistent by construction; temporal
stability comes from band-fitting + prior persistence + the filter. Quantified
day-over-day density stability is not tabulated — same backlog item as slide 6.

**Tail moments when quotes stop early.** Structural exponential tails obeying Lee's
bound by construction; behavior beyond the last quote is a stated contract (slide 19)
optionally pinned by wing priors or the var-swap.

---

## Slide 9 — SVI conversion singularities in live workflows

**Answer.** The optimizer never leaves raw (a,b,ρ,m,σ) coordinates, kept structurally
valid by reparametrization — so live fitting cannot hit a JW singularity. The JW map is
an analytical/benchmark coordinate system, NOT a wired workflow: production stores raw
SVI and displays model-agnostic ATM handles; `jw_to_raw`'s only caller is a benchmark
test, there is no backend `raw_to_jw`, and JW entry/bump/export are roadmap. The
conversion is exact on its documented regular domain — v>0, p,c>0, −p/2<ψ<c/2, ψ≠0,
ṽ<v — with the ψ=0 (ATM-at-the-vertex) singularity stated as a contract, and the
domain + failure modes are test-locked as of 2026-07-11 (`test_svi_domain.py`).
Practical consequence: a degenerate JW *readout* is possible in pathological corners,
a degenerate *fit* is not.

---

## Slide 10 — Arbitrage fencing: grid vs analytic, and between-point risk

**Answer — separate measurement from enforcement.**

- *Measurement* (the per-fit diagnostic and backtest metric) is analytic per model:
  LQD is structurally positive (no g needed), SVI and MCS evaluate g(k) from
  closed-form w, w′, w″ — that is the 28.3% → 0.0% story on the slide.
- *Enforcement* (the penalties) samples on grids: MCS put-wing hinge on 49 points
  extending 2 standardized-moneyness units past the traded range (put side ×2);
  calendar floors on 41 data-confined points (SVI/MCS) and a ~320-point subgrid (LQD).

**Between-grid arbitrage?** For LQD, structurally impossible. For SVI/MCS, possible in
principle between penalty samples, but (i) g is an analytic smooth function of the
5–14 parameters, so oscillation between adjacent samples at these densities is
limited, and (ii) the shipped *diagnostic* is analytic and reported on every fit — a
violation would be flagged even where the penalty grid missed it.

**How often does the penalty bite?** Measured: post-fencing real arb rates SVI 9.2%,
SIV-0 10.0% (mostly slices where the penalty is actively trading fit vs cleanliness);
the EFA ablation quantifies the cost when it must fight corrupted inputs (slide 12).
On clean slices the hinge is exactly zero — byte-identity is test-locked.

---

## Slide 12 — MCS: why cap at two hats globally?

**Answer.** The cap is *not* only global — there are two caps, and one is exactly the
adaptivity the question asks for: (i) an identifiability budget R ≤ (N_quotes − 6)/4 —
hats scale with quote density; (ii) a global ceiling of 2 because the backtest showed
a third hat buys no out-of-sample accuracy while being super-linear in cost (SIV-3:
2 s/fit, 76% of spike nodes carrying g < 0, 64% of violations in the put wing).
The ceiling is evidence-based and revisitable per event type if a case appears where
two zero-wing hats can't express a real event shape (two hats already cover a W).
Persisted settings with nCores > 2 load clamped, test-locked.

---

## Slide 13 — Local Vol: grid stability and boundary behavior

**Stability under quote noise.** The band objective makes intra-spread noise free
(the strongest stabilizer for a many-vertex model), plus the roughness penalty,
positive-node constraint, and warm-started recalibration; per-expiry diagnostics name
degradation causes. **Gap**: no formal noise-perturbation study of the nodal grid —
candidate for the backtest harness.

**Boundary behavior to trust.** Beyond the last strike node local variance
extrapolates *flat* on the call side, controlled-linear on the put side only when a
var-swap identifies the deep tail; the opt-in convexity hinge acts only below the
deepest observed quote (≤ 5Δ put). Implied wing slopes stay under Lee's cap —
measured and reported, not assumed. Contract: conservative, stated, and never active
on quoted strikes (the SPY 25.7 → 2.6 bp confinement case).

---

## Slide 14 — LV solver: diagnostics, hard cases, gradient testing

**Diagnostics a trader sees.** Per-expiry side-channel (`api/affine_diag.py`):
vertices-in-range (strike under-resolution), vega-floor fraction, PDE steps, prior
rows — plus solver status, nfev vs cap, active bounds, and wall-time split in the
backtest metrics; the Quality tab is the publish-readiness screen.

**Hard cases.** Very short expiries: the weekly case file (3 vertices → 108 bp; fix =
per-expiry coverage floor + maturity-aware step → 23.5 bp, long expiries
byte-identical). Dividends: absorbed into the forward; escrowed-spot handling upstream;
a true short-dated event spike is only approximated (stated limitation). Sparse wings:
the convex hinge is confined to the extrapolation tail after it flattened SPY.

**Gradients.** Yes — tangent sensitivities match finite differences (1e-6 tolerance),
adjoint passes the ⟨Jv,w⟩ = ⟨v,Jᵀw⟩ identity test, GN matches TRF on a golden
surface; the one production crash on this path (LinearizedJacobian.T fallback) was
found by the backtest, fixed, and test-locked.

---

## Slide 15 — De-Americanization: dividends, borrow, huge EEP

**Dividend robustness.** Discrete cash dividends via an escrowed-spot lattice
(recombining tree, exercise checked against true cum-dividend spot); per-ticker
dividend editor; the tree only prices the American−European *difference*, so
discretization error largely cancels. Depth 192 + 24 bisections is a numerical-target
setting, not a speed dial.

**Borrow/specials.** Honest answer: borrow is **not a standalone input** — it is
absorbed into the parity-implied forward (carry = r − q), which is usually the right
place since parity sees the same borrow the option market prices. Note 05 states the
limitation explicitly: for names with hard-to-model borrow, σ* is only as good as the
forward. The zero-carry pin (schema v5) protects against the provider-synthesized-
chain failure mode. Hard-to-borrow names: no dedicated module — flagged limitation,
mitigated by the parity forward and the wing/bid pre-screen.

**Huge EEP.** A conservative pre-screen drops quotes that cannot survive static
bounds (non-positive bids, wing buffer); prices below intrinsic return NaN and are
excluded. There is **no EEP-magnitude-based downweight** on surviving quotes — the
view is that a correctly-inverted deep-ITM quote is valid; the trader can exclude or
haircut it. Reasonable Q&A position, but say it plainly.

---

## Slide 17 — Objective: bands → weights, wide-band stability

**Answer.** Bands are not converted into weights — they *are* the loss: a squared
hinge outside [bid, ask] plus a small mid anchor (θ = 0.05), so "inside the band is
free" is exactly true up to that anchor, which is precisely what breaks the wide-band
degeneracy the question worries about. Liquidity enters separately through
tv-density weights (time value × Voronoi spacing correction, capped 10×,
mean-normalized so switching schemes never re-tunes the regularization balance).
Parameter stability when bands are wide comes from the anchor + each model's ridge +
the prior pulls where data is silent — and the wide band is itself "a regularizer
that costs no bias" (Note 07). The haircut dial spans mid-fitting ↔ band-fitting
continuously.

---

## Slide 19 — Wing/tail discipline: where does trader judgement enter?

**Answer — enumerate the levers, each a stated contract.** Haircut margin; per-quote
exclude/amend; LQD wing priors pinning A_L/A_R (Lee slopes); the var-swap quote (pins
the tail integral exactly); prior-anchor strength; the opt-in `extrapEnforce`
(quarter-quote-budget hinges over the time-value envelope, exact no-op on clean
pairs); LV put-wing slope multiplier (free only when a var-swap identifies the tail).
Everything else is moment logic (Lee) that judgement cannot override — by design.

---

## Slide 23 — Prior persistence: precision gaming, wrong-yesterday failure

**How observed precision is measured.** Effective weighted quote count per operator
leg via a Gaussian kernel in log-moneyness, combined harmonically across legs (a
missing put leg keeps an RR precision low); gate = max(1 − obs/required, 0)^γ
(`calib/operators.py`, `precision.py`).

**Can many bad quotes game it?** Yes — and be candid, because the failure direction
is *conservative*: the support measure is a count proxy (no spread, no vega), so a
dense cluster of bad quotes drives the gate to zero and switches the prior **off** —
data wins. Gaming cannot amplify the prior; it can only forfeit its help, and then
the bad quotes are a quote-quality problem addressed one layer up (filter ρ-inflation
reads a dense-but-contradictory cluster as noise). Folding spread into operator
support is a sensible refinement — offer it as roadmap.

**When yesterday's shape is wrong.** Four guards: the gate itself (quoted features
are never pulled — the no-damp guarantee, test-locked); hybrid anchors only the deep
tail below the shallowest active operator; prior precision decays with age (30d
half-life) and transport distance (large overnight move ⇒ mechanically weaker prior);
the filter reset policy reseeds on broken clocks. The residual failure mode is
irreducible: a *dark* region inherits yesterday's wrong shape because nothing else
exists — and the bands widen with age/transport to say so.

---

## Slide 24 — Prior validation: node concentration, the two failed modes

**Concentration — yes, and the slide should say so.** All 1,116 nodes are from a
single regime (Aug-2024 spike), 8 pilot assets (3 indices, 2 ETFs, 3 single names),
19 consecutive-day pairs; node count skews to the expiry-rich indices. The findings
file itself queues the cross-regime rerun. **Amend the slide** (see list below).

**The two failed modes.** `quote_operator` and `smile_factor` — median improvement
exactly 0.0 vs no-prior, win rates 0.30/0.34. Mechanism: both remember *level-
invariant baskets* (RR/BF, ATM-local factors) that carry no absolute wing level, so
on a chain thinned to ATM they reconstruct nothing in the held-out wing; the wing is
delivered by the deep-tail anchor, present only in `hybrid` and `strike_gap`. They
still do their no-damp job — they fail *this task*, not their design purpose.

---

## Slide 25 — Filter: regime breaks, noise granularity

**Preventing over-smoothing of real breaks.** Five mechanisms, all shipped: the 3σ
innovation gate inflating P⁻ up to 25× (SPX shock win 0.42 → 1.00); per-handle
diagonal updates (junk curvature cannot drag ATM — the EEM/EFA case file);
ρ-inflation raising R exactly in unidentified directions; a gain cap (Joseph-form,
PSD); and a reset policy (source/as-of/edit change or calendar gap ⇒ reseed rather
than predict across a broken clock).

**Q and R granularity.** R: estimated per node per fit — the solver's own information
matrix propagated through the handle map, scaled by per-quote bid-ask spreads,
ρ-inflated, with a short-maturity floor. Q: **fixed global per-handle knobs**
(30 bp/√day ATM etc., flipped from 10 by one-sided backtest evidence), modulated per
node only by dt and the node's own spot move — *not* estimated per asset/expiry.
Honest: per-asset Q estimation is a natural refinement; the current default was
chosen by 39,190 backtested steps, not taste.

---

## Slide 26 — Filter validation: contradiction days, economics, MAP underperformance

**"Contradiction day" definition.** Staged, precise: on the thinned day-T chain, two
adjacent near-ATM strikes are kinked ±2 vol points in opposite directions — local
curvature noise that must be rejected (harness `backtest/observation_filter.py`;
Note 15 states it identically). Say "staged" plainly; the organic counterpart is the
stale-quote case file on the slide.

**Are 5.6 vs 9.8 bp economically meaningful?** Frame honestly: that cell is high-vol
regime, >30 DTE, ATM marks — a 4 bp RMS improvement is real for re-marking a book
(deck's own yardstick: 10 bp ≈ tighter than most spreads) but the filter's value is
concentrated in the noisy tail: on plain median days its win rate is only 0.38–0.57
(≈ neutral). It is insurance against bad-quote days, not alpha on clean days.

**How often does active MAP underperform raw — and by how much?** Measured, and
material: on outright *shock* days active MAP trails the raw fit — 19.5 vs 3.8 bp
(spike) and 25.2 vs 5.8 bp (high-vol), because the adaptive-Q gate is currently
overlay-only (the MAP prior weight is fixed before the measurement exists). This is
the flagged blocker before active-by-default, and it is exactly the trader's
question 25 fear realized in one cell. **Amend the slide** — the current "one honest
exception" bullet undersells this (see list below).

---

## Slide 27 — Graph: initialization and mark provenance

**Initialization for a new universe.** Auto-lattice over the selected nodes: calendar
chains within each ticker + cross-ticker same-tenor edges, two visible weight dials,
**β seeded at 1** (the sector-aware β defaults of 0.6–0.8 live in the *backtest*
edge model, not production defaults). The desk then edits and persists; η is
LOO-auto-tunable in one click.

**Are graph marks distinguishable downstream?** In-app, fully: per-node `lit` flag,
separate posterior vs own-calibration curves, provenance badge with source-node
attribution, ζ quoted only for dark nodes. **Check before answering "yes"
end-to-end**: the export/publish path stamping graph-vs-observed provenance on the
way out is part of the open Phase-3 publish projection — commit to it rather than
claim it.

---

## Slide 28 — Graph mechanics: Gaussianity, jumpy shocks, double-counting

**Why Gaussian increments in handle space?** Three reasons: increments (innovations),
not levels, are the propagated object — closest to stationarity/Gaussianity of any
available coordinate; handle space is the shared vocabulary the whole stack speaks;
and conjugacy buys a closed-form posterior with *exact* per-edge attribution — the
auditable structure of slide 29 is a direct consequence. The assumption is then
audited, not trusted: ζ per regime and cell.

**Bands under nonlinear/jumpy shocks?** Answered by the same audit: spike-regime ζ
std 0.7–1.1 (honest); the calm-regime dark-name cell that measured ~1.9 is fixed at
the ATM level by the idio band floor (shipped 2026-07-10, ζ std → 1.02/1.03);
skew/curvature widening stays open. Do not claim more.

**Double-counting.** The posterior precision is three *disjoint additive* sources:
baseline/prior precision (provenance × age × transport), increment-prior precision
(edge structure), and lit-node observation precision (that node's own fit quality) —
each lit calibration enters exactly once as an innovation. On the filter side, active
MAP has an explicit no-double-count proposition (prediction enters as penalty rows in
the one fit; no second update against the same quotes). Bands use the marginal
covariance, never the precision diagonal — a stated caution on slide 29.

---

## Slide 29 — Edges & betas: governance, estimation, attribution

**Governance today.** β = 1 seeds + desk edits through the persisted edge editor
(SQLite). **Honest gap**: persistence is a last-saved blob — no version history or
edit audit. The slide's "versioned like one" phrase is slightly ahead of the code —
**amend or ship versioning** (see list). Backtesting the desk's choices, however, is
real today: the one-click LOO re-certifies any edge configuration on the desk's own
universe — that is the governance loop.

**Historical β without overfitting.** When it lands: estimate on one regime,
validate LOO on others (the harness already does exactly this for η); shrink toward
1 (the current prior); per-handle β only if the data demands it (flagged refinement).

**Attribution.** Yes, exact: contribution_j = gain_row × innovation_j sums *exactly*
to the posterior ATM shift; surfaced as the attribution card (top-20, per-edge β
shown, remainder folded into "others"), test-locked (`test_graph_attribution.py`).

---

## Slide 30 — Graph validation: calm-regime fix, breakdowns, baseline

**The overconfident cell — fix and severity.** Severity was bounded and quantified:
one cell (calm regime × fully-dark single names), skill ≈ +0.7 bp (never negative),
bands ~2× too narrow (ζ std 1.85–1.91); everywhere else 0.7–1.1. Risk profile: a
trader over-trusting a dark-name band in quiet, earnings-driven tape. **Fix SHIPPED
2026-07-10** — the idiosyncratic ATM-band floor (`volfit/graph/idio.py`, on by
default in production): the dark ATM band variance is floored at 0.30 × the node's
own strictly-causal trailing innovation RMS (EWMA half-life 5d, pool-shrunk), which
is mean-invariant by construction (a dark node's baseline precision enters only the
band, never the posterior mean). Validated offline on the stored benchmark rows: the
two calm cells moved ζ std 1.91→1.02 and 1.85→1.03 with the stressed cells intact.
Remaining open: widening the skew/curvature bands in idiosyncratic tape. Note the
superficially-obvious lever (dark base scale) was measured to be dead for the
posterior mean — the binding constraints are reach η and edge conductance; that
diagnosis is *why* the fix targets the band, not the mean.

**Breakdowns.** Today: by regime × asset kind (index/ETF/single-name) × design in the
benchmark artifact. Not yet: sector, market cap, earnings proximity, liquidity decile
— per-node data exists; earnings-proximity is the most relevant next cut given the
idiosyncratic diagnosis. Offer it as the next benchmark-pack extension.

**Baseline besides transported prior.** Honest: transported prior is the single
baseline — chosen because it is the strongest mechanical alternative (it is what the
system does with zero graph). A second naive baseline (β × index move rule) would
strengthen the claim and is cheap to add to the harness.

---

## Slide 33 — Performance: server hardware, 500–2,000 nodes, bottlenecks, cold start

**Server hardware.** None measured — every number states laptop i7-12700H, and the
slide says so. Offer: the perf rail is scripted; running it on target hardware is an
afternoon.

**500–2,000 node universes.** Partially measured: the graph layer has explicit rails —
1,000-node update ~0.7 s (budget 2.5 s) and a 2,000-chord scale guard < 5 s; dense
solve is documented fine to ~2k nodes, sparse solver deliberately deferred past
2–3k. Full *calibration* at that scale is extrapolation (35 ms/slice × process pool),
not measurement — say so, and note calibration parallelizes per-ticker while the
graph solve is the coupled step with its own rail.

**Single-thread bottlenecks.** Named: main-side GIL work in the parallel Calibrate
(de-Am prep + smile reconstruction + LV response assembly); inside a cold LV fit,
dense SVD ~52% + sensitivity march ~32% (no single per-eval lever left — four
attempts measured and shelved).

**Cold start / intraday recovery.** 96.6 s cold (process-pool spawn + Numba JIT +
de-Am) vs 7.6 s warm on the 30-node session; caches are content-addressed so
recovery re-pays only what the data changed — restart of the process, not refetch of
the world. If intraday process restarts matter to the desk, AOT-compiling the Numba
kernels is the known lever.

---

## Slide 34 — Trust: auditor reproduction, test composition, model-risk docs

**Can an auditor reproduce a number end-to-end?** For the automated pipeline, yes:
snapshot (SQLite, schema-versioned, WAL) → every fit persisted keyed by snapshot
timestamp → export artifacts; backtest numbers from immutable JSON fixtures through a
regenerable, provenance-stamped HTML/JSON artifact; every notes figure regenerated by
production code at build (drift fails the build). **Two gaps to state**: manual quote
edits are session-scoped (not in the reproduction chain), and graph-edge sets have no
version history — both roadmap items (same as slides 3/29).

**Test composition.** ~950+ tests, 138 files, four kinds: golden-vs-notes (80+ named
tests, each note carries a claim → equation → module → test traceability table, many
at 1e-10…1e-15); workflow/API tests (~25+, incl. serial-vs-parallel byte-identity);
replay/backtest-driven tests (arb metric, benchmark pack, LOO, temporal, filter);
perf rails (7). So: majority unit/math, but with genuine desk-workflow and
historical-replay coverage — and every FINDINGS remediation ends in a named test.

**Model-risk documentation.** The 16 notes are most of an SR 11-7-style pack already:
model description + assumptions (boxed equations, invariant boxes), limitations
(stated per note), developmental evidence (backtests, FINDINGS files), ongoing
monitoring (Quality tab, per-fit g(k), ζ audits), change control (byte-identity locks
+ golden tests). Missing for internal validation: a model inventory/versioning doc, a
formal approval workflow, and independent revalidation on data the developers didn't
choose. Offer the notes as the submission skeleton.

---

# Slide amendments — recommended

Priority order:

1. **Slide 26 (filter validation) — add the shock-day caveat.** Active MAP trails the
   raw fit on outright shock days (19.5 vs 3.8 bp spike; 25.2 vs 5.8 high) because
   the adaptive gate is overlay-only today; this is the stated blocker before
   active-by-default. The current "one honest exception" bullet undersells a
   material, measured weakness — and the deck's credibility rests on it volunteering
   exactly this kind of number.
2. **Slide 24 (prior validation) — scope the 1,116-node tile.** Add "(Aug-2024 spike
   regime, 8 assets; cross-regime rerun queued)" and optionally name the two failed
   modes (quote-operator, smile-factor) in the negative-result bullet.
3. **Slide 29 (edges) — soften "versioned like one"** to "persisted with the
   universe; version history on the roadmap", or ship a simple versioned edge-set
   history and keep the phrase.
4. **Slide 4 (worked example) — one-line cross-reference**: "band honesty is measured
   out-of-sample in the LOO backtest (slide 30)" — preempts the calibration question.
5. **Slide 3 / 34 (optional backup slide)** — "Override surface & audit": the
   override list above, what persists, what doesn't yet (quote-edit audit log).
6. **Slide 7 — no text change now**; fold per-asset/expiry/moneyness/liquidity
   breakdowns into the already-promised backtest refresh.

# Honest-gap register (for Q&A, not slides)

- Quote-edit audit log (in-memory sessions) — roadmap.
- Graph-edge version history — roadmap.
- Borrow not a standalone de-Am input (absorbed in parity forward) — stated limitation.
- Q (process noise) global per-handle, not per-asset — evidence-chosen default.
- Operator precision gameable by dense bad quotes — but fails conservative (prior off).
- No LQD handle-drift-by-day table; no digital-sensitivity study — cheap backlog.
- Single LOO baseline (transported prior); no earnings-proximity cut yet.
- No server-hardware timings; >30-node full-calibration timing is extrapolated.
- Export path does not yet stamp graph-vs-observed provenance (Phase 3 open).
