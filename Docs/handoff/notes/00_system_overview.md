# System Overview, Conventions & Hyperparameter Atlas

**Note 00 — system overview · reference edition · converted from 00_system_overview.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

*What the Vol-Fitter does, the pipeline, and the master index of every knob. Vol-Fitter Technical Notes, No. 00.*

> **Abstract.** This is the map of the territory. The Vol-Fitter is an implied-volatility surface fitter in the spirit of a professional vola-fitter, with one differentiating capability: it *extrapolates* sparse smile observations to a full universe of smiles, across expiries *and* assets, by propagating signal through a graph whose nodes are smiles $(\text{underlying},T)$. This note states the market and normalization conventions shared by the whole series, walks the end-to-end compute pipeline (fetch $\to$ forwards/carry $\to$ prepare [de-Americanize, screen, weight] $\to$ fit $\to$ views $+$ graph), catalogues what the application can do, and ends with an index of the *principal calibration controls*, cross-linked to the topic notes that derive each knob. One claim organizes the whole series: every guarantee is graded and *executable* — structural where a model can carry it, certified at the publish gate where it cannot, measured everywhere else — and the production incidents that taught each design rule are frozen as named certification cases that re-run on demand. It is the front door: read it once, then any other note in the series stands alone.

## 1. What the application is

At its core the Vol-Fitter solves one problem repeatedly — *given noisy, sparse option quotes for one expiry of one underlying, produce a smooth implied-volatility smile under explicit no-arbitrage control* — and then layers three ambitions on top of it:

1. **A choice of models, all arbitrage-aware.** Three slice parametrizations share the per-expiry calibration spine — the *LQD* log-quantile-density model (Note 01), *SVI / SVI-JW* (Note 02), and the *Multi-Core Sigmoid (MCS)* family (Note 03) — and a fourth model stands apart: the *piecewise-affine local-volatility surface* (Note 04), a *jointly* calibrated maturity $\times$ strike grid whose unknown is piecewise-affine local *variance*, priced through the Dupire PDE. On arbitrage the honest statement is graded — structural, certified, measured. LQD is butterfly-free *by construction* and the LV surface is structurally arbitrage-clean (positive local variance); SVI and MCS are *soft-fenced* by sampled penalties, which reduce but do not guarantee zero residual violation; and the grading no longer stops there: every *displayed* slice, whatever its model, must pass a dense-grid belly *butterfly certificate* over its traded range — Durrleman $g\ge-10^{-4}$ on an 801-point grid, computed from the model's own derivatives in a few dozen microseconds — before it counts as publishable; an uncertified slice cannot become a mark (Note 02). Residual violation rates are still measured and reported per fit, never assumed away.
2. **A professional desk workflow.** Real bid/ask handling (fit to mid, to the bid–ask band, or to a haircut band), var-swap targets, density-corrected weighting, event time dilation, dividend and forward treatment, spot–vol dynamics, a Bayesian prior-persistence machine that decides, feature by feature (operator by operator), whether the live quotes identify a smile feature or the saved prior should carry it, and a temporal observation filter (a per-handle Kalman/MAP estimator, Note 15) that denoises noisy or contradictory quotes while treating a genuine data gap as absent evidence rather than noise. The filter has three modes: `off` (byte-identical to the feature never existing), `overlay` (post-fit state and display update only), and `active` (the prediction enters the calibration objective before optimization); `active` is off by default and still carries a documented shock-day lag.
3. **Graph smile-extrapolation.** The headline differentiator (Note 14): a transported prior plus the lit-node calibration innovation are propagated through a *directed Bayesian graph* to reconstruct the *dark* nodes. The propagation operator is itself a menu — the pairwise *precision-message* operator (the options default since 2026-07-27), the `smooth_field` increment prior (the wire default and explicit rollback), and an opt-in layered dynamic-harmonic pipeline — with an optional optimal-transport regularization, off by default ($\lambda=0$). The defaults here were chosen by held-out adjudication, not preference (see "The smile graph").

> **Heuristic.** The unifying idea is that a volatility surface is not a curve to be drawn but a *family of probability laws* to be inferred — one risk-neutral law per $(\text{underlying},T)$ node — subject to no-arbitrage couplings (butterfly within a slice, calendar across expiries) and to a Bayesian prior that ties the whole universe together. Every design choice in the app follows from taking that sentence literally.

**Vocabulary.** Terms the whole series uses without ceremony, defined once. A *smile* is the implied-volatility curve of one $(\text{underlying},T)$; a *slice* is one smile's fitted model; a *surface* is all expiries of one underlying; a *node* is one $(\text{underlying},T)$ pair viewed as a graph vertex. A node is *lit* when its quotes are consumed and calibrated, and *dark* otherwise — operationally, dark means the quotes are absent, unusable, deliberately withheld, or simply not consumed; it does not necessarily mean nobody quoted. The *prior* is the saved previous fit, transported to today's market; the *innovation* is a lit node's fitted-minus-prior move. A *handle* is a scalar smile summary — the three ATM handles are level $\sigma_0$, skew $s_0$ and curvature $\kappa_0$. The *haircut band* is the bid–ask band shrunk by a fixed vol amount; a *vol bp* is $0.01$ vol point ($10^{-4}$ in volatility); a *WW smile* is a W-shaped smile (central trough with two shoulders, Note 03). Abbreviations: CRR (Cox–Ross–Rubinstein binomial tree), SSR (skew-stickiness ratio, Note 12), OT (optimal transport), MAP (maximum a posteriori), GN (Gauss–Newton), NBBO (national best bid/offer).

> **Invariants — the system-wide contracts every note protects, stated once.**
> 1. **Arbitrage-cleanliness is structural where possible, certified at the gate, measured always.** LQD and the LV surface are clean by construction; SVI/MCS are fenced by penalties that are exactly zero on admissible slices — which bounds but does not eliminate residual violation; the belly butterfly certificate hard-blocks readiness and publish for *any* uncertified displayed slice; and the residual rates are reported by explicit per-fit diagnostics, never assumed away.
> 2. **Every feature is strictly additive.** Bands, var-swap targets, calendar coupling, the event clock, priors, betas, the wing penalty, the observation filter: each is byte-identical to its absence when off — and that byte-identity is test-locked, not asserted.
> 3. **Numbers are measured, not copied.** Figures and tables are generated fresh by the production code; reference listings are executed against the modules they distill; claims carry test anchors.
> 4. **Versioned invalidation is scoped.** Editing one name's rate, dividends, events or prior bumps that ticker's version only — never the universe. Whether the name then *refits* immediately depends on the workflow gate: with `autoCalibrate` on it refits in the background; on the trigger-gated live server (which defaults `autoCalibrate` off) the existing fit is kept, marked stale, and waits for an explicit Calibrate.

Figure 1 shows the two static-arbitrage checks, each in its correct coordinates, on a four-expiry synthetic surface fitted by the production LQD calibrator. Panel (b) is the *butterfly* check: every implied density is non-negative, by construction. Panel (c) is the *calendar* check: stacked *total variance* $w(k,T)$, where for forward-normalized (mean-one) slices absence of calendar arbitrage at fixed log-moneyness is exactly the non-crossing ordering $w(k,T_{i+1})\ge w(k,T_i)$ at *every* $k$ — the same view the app's Stacked IV tab draws. Two tempting substitutes are not checks at all: stacked *vol* smiles carry no calendar content ($\sigma$ mixes $w$ with the clock, so clean surfaces cross freely in vol), and ATM-only monotonicity is necessary but far from sufficient. The four slices here are fitted independently, so the displayed dominance is *measured* — the generator asserts a positive minimum inter-expiry gap on the displayed grid before writing the figure — not enforced; the enforcement coupling is Note 10's calendar machinery.

> **Figure 1 — The two static-arbitrage checks (figure not included in this pack).** The two static-arbitrage checks, produced end to end by the production LQD fitter on a synthetic calendar-monotone surface. Panels a, b: the fits and their non-negative densities (no butterfly arbitrage, by construction). Panel c: stacked total variance, non-crossing at every displayed $k$ (no calendar arbitrage there — measured on independently fitted slices; enforcement is Note 10's coupling). *Description:* Panel (a) shows four fitted implied-volatility smiles, one per expiry of the synthetic surface, each threading its quotes. Panel (b) stacks the four implied risk-neutral densities recovered from those fits; every curve is non-negative across its whole strike range — the butterfly check passed structurally, since LQD parameterizes a valid density by construction. Panel (c) stacks the four total-variance curves $w(k,T)$ against log-moneyness: the curves are strictly ordered in maturity at every displayed $k$ with no crossings — the calendar check in its correct coordinates — and the generator asserted a positive minimum inter-expiry gap before writing the figure, so the displayed dominance is measured on independently fitted slices rather than enforced by a coupling.

## 2. Market conventions and normalization

These conventions hold across the entire series; individual notes assume them without restating.

**Definition (Forward measure and normalization).** For expiry $T$ with forward price $F_T$, work under the $T$-forward measure and in forward-normalized, undiscounted units. The log-moneyness is $k=\log(K/F_T)$, the log-forward return is $X_T=\log(S_T/F_T)$, and normalized call/put prices are $C_T(k)=\mathbb{E}^T[(e^{X_T}-e^k)^+]$ and $P_T(k)=\mathbb{E}^T[(e^k-e^{X_T})^+]$, with the martingale condition $\mathbb{E}^T[e^{X_T}]=1$.

**Definition (Total variance and the Black map).** The normalized Black call is $\mathrm{Bl}(k,w)=\Phi(d_+)-e^k\Phi(d_-)$ with $d_\pm=-k/\sqrt w\pm\sqrt w/2$. Total implied variance $w(k,T)$ is the unique $w$ solving $\mathrm{Bl}(k,w)=C_T(k)$ — a property of the *price*, independent of any time convention; the fitter inverts it by a vectorized scheme rather than a scalar root-find per strike. Annualizing $w$ by a clock gives an implied volatility: $\sigma^2=w/t$ under the calendar clock, $\sigma^2=w/\tau$ under the event clock below.

This one primitive underlies every model in the series; in normalized form it is a handful of lines (matches production to $10^{-12}$):

> **Algorithm — the normalized Black call $\mathrm{Bl}(k,w)$, the shared pricing primitive (distilled from `core/black.py`).** (Replaces the note's code listing; the pack carries no source code.) Inputs: log-moneyness $k=\log(K/F)$ and total implied variance $w$, both vectorizable. Steps: (1) set $\sqrt w$ and $d_+=-k/\sqrt w+\tfrac12\sqrt w$ (so $d_-=d_+-\sqrt w$); (2) price $=\Phi(d_+)-e^{k}\,\Phi(d_+-\sqrt w)$ with $\Phi$ the standard normal cdf; (3) intrinsic $=\max(1-e^{k},\,0)$; (4) return the price where $w>10^{-12}$, and the intrinsic value where $w\le10^{-12}$ (the degenerate-variance limit). Production agreement: $10^{-12}$.

Three conventions deserve emphasis because they recur:

- **Two clocks, one $w$.** Four objects, kept distinct: $t$ is the calendar year-fraction to expiry; $w$ is the clock-independent total variance inverted from the price; $\sqrt{w/t}$ is the calendar-annualized *market* IV; $\sqrt{w/\tau}$ is the *working* (event-time) IV, where $\tau$ is calendar time dilated by scheduled events (Note 11). Fits live on $\tau$ when the event clock is on. "Adding an event lowers IV" means precisely: at fixed price (hence fixed $w$), the event raises $\tau$ and so lowers the *working* IV — the market IV and the price are untouched. De-Americanization and carry always run on the calendar clock $t$.
- **Forward-normalized everything.** Prices, strikes and densities are quoted relative to $F_T$, so a single smile object is spot-independent until a dynamics rule (Note 12) transports it under a spot move.
- **Residual units are per-model.** LQD and the LV surface calibrate on price residuals divided by Black vega — a volatility-like objective whose every iterate is a valid price (Notes 01, 04, 07); SVI and MCS fit directly in implied-volatility units. The bid–ask/haircut band objective (Note 07) is expressed in vol space for all models.

## 3. The compute pipeline

Every smile the app shows is the output of the pipeline in Figure 2. The stages are deliberately decoupled and independently cached so that, e.g., editing a fit penalty never re-pulls data or re-runs de-Americanization.

> **Figure 2 — The end-to-end compute spine (figure not included in this pack; original is a block diagram).** The end-to-end compute spine. The forward, discount, dividends and clocks are resolved first (parity with an American de-bias refinement); quote preparation then selects the OTM side, de-Americanizes each quote, and inverts/screens/weights; calibration (per-expiry slices plus the jointly fitted LV surface) feeds the lit views *and* the graph extrapolator, whose dark-node reconstructions feed the same views. *Description:* The diagram is a left-to-right flow of six boxes. "Data feed (Yahoo / Bloomberg / Massive)" feeds "Forwards & carry (parity $F,D$ + de-Am refine, divs, clocks — Note 06)", which feeds "Prepare (OTM $\to$ de-Am (Note 05) $\to$ invert, screen, weight)"; these first three boxes are grouped under the label "quote preparation". Prepare flows down into "Calibrate (slices Notes 01–03, 07–13 + joint LV surface Note 04)". From Calibrate, an arrow labelled "lit fits" goes to "Views (smile / density / term)", and a second arrow labelled "prior + innovation" curves down to "Graph (extrapolate — Note 14)", whose own arrow labelled "dark nodes" feeds back into the same Views box — the graph's reconstructions are served through exactly the view machinery the lit fits use.

**Stage by stage.**

1. **Data feed.** A provider registry exposes Yahoo (US options), Bloomberg (xbbg; US + non-US indices/equities), and Massive (Polygon/OPRA), plus a synthetic source; an as-of selector serves Live / previous-close / EOD / captured-replay. US-options-only providers and the non-US Bloomberg path are handled transparently.
2. **Forwards, dividends and clocks** (Note 06). Resolved *before* any per-quote work, because everything downstream consumes them. Put–call parity on the raw chain yields the implied forward and discount (clamped against feed noise); the forward inference itself contains a near-ATM American de-bias loop, so the regressed forward is consistent with American quotes. Discrete dividends and the two clocks — calendar $t$ and event-dilated variance time $\tau$ — are resolved here too. One provider pathology is handled upstream of the regression: chains a delayed feed *synthesizes* at zero carry (NBBO gated, so the provider emits Black prices from its own IV marks at $F=$ spot, $D=1$) are flagged at capture and *pinned* to $F=$ spot, $D=1$ rather than parity-regressed — regressing quotes that already embed the provider's carry produced garbage forwards.
3. **Prepare** (Notes 05, 07). Per-expiry, given the resolved forward and clocks: select the out-of-the-money side of each strike; then *de-Americanize* every kept quote (Note 05) — listed equity options are American, and each is converted to its European-equivalent implied volatility by inverting a Cox–Ross–Rubinstein tree (bisection), with a Numba kernel for wide chains and a content-digest cache so fit-tuning never re-runs it; then normalize, invert to total variance (vectorized), apply the static no-arbitrage/wing screen — every dropped quote is quarantined with a reason, never silently discarded — run the wing-only, band-constrained convexity repair (holding the ATM core fixed), and assign observation weights (Note 07).
4. **Calibrate.** The three parametric families fit per-expiry slices; the LV surface is calibrated *jointly* across maturities and strikes from the same prepared quotes (Note 04). Each fit runs under the active objective: mid / bid–ask band / haircut (Note 07), optional var-swap target (Note 08), calendar coupling (Note 10), event clock (Note 11), and Bayesian prior persistence (Note 13). The observation Kalman filter (Note 15) sequences by mode: `off` adds nothing (byte-identical); `overlay` updates the filtered state and display *after* the fit commits; `active` inserts the prediction prior into the calibration objective *before* optimization.
5. **Views.** Every smile-derived view — smile, stacked densities, stacked total variance, quantile density, term structure, local-vol surface, SSR scenario — follows the chosen model and is downsampled for the UI. Views serve lit fits and, once the graph has run, the reconstructed dark nodes.
6. **Graph** (Note 14). The transported prior plus the lit-node innovation propagate through the directed Bayesian graph (OT term optional, off by default) to reconstruct dark-node smiles with credible bands, which flow back into the views.

## 4. The smile graph

The object that makes the app more than a slice fitter is the *smile graph* (Figure 3): nodes are smiles $(\text{underlying},T)$; edges encode that one node informs another. Calendar edges link expiries of one name; cross-asset edges link an index or sector ETF to its single names. A user marks nodes *lit* (quoted, calibrated) or *dark* (to be reconstructed). The graph carries the three ATM handles $(\sigma_0,s_0,\kappa_0)$ of each node as a Gaussian signal and propagates the lit innovation to the dark nodes. Three scalars do not make a smile: a dark node's full curve is obtained by *retargeting* — the node's transported prior smile (a complete curve, wings and all) is re-expressed in an ATM-orthogonal chart and its three handles are moved to the posterior values, leaving the prior's shape modes (wings, event convexity) untouched, so every reconstructed slice remains a valid arbitrage-clean smile. Note 14 develops the directed Bayesian solver behind the propagation (with an optional optimal-transport regularization, off by default: `graphLambdaScale` $=0$) and the leave-one-out backtest that measures its skill.

The propagation operator is versioned and adjudicated, and its history is a small case study in how defaults are set here. `precision_messages` — the options default since 2026-07-27 — replaces the smoothness field by pairwise *relation factors* (calendar ladders, index$\to$name pairs) whose per-edge precisions are first-class policy objects with their own editor, live preflight and draft/active lifecycle; its golden acceptance contracts — full transmission, competing signals, dead-informer zero dilution, baseline-uncertainty-enters-once — are locked three times over, against a brute-force Gaussian reference, through the production assembly, and through the HTTP API. Its own pre-registered *daily* gate did not clear (RMS tie, narrow bands, recorded verbatim); the default moved on the intraday async replay, where the smoothness field measures nearly inert while the messages carry the signal — and `smooth_field`, the increment prior of Note 14 and the solver the backtests validated, stays as the wire default, the byte-identity anchor and the explicit rollback. The layered dynamic-harmonic pipeline adds temporal, directed and harmonic structure on top of the messages; its pre-registered daily A/B campaign returned a *negative* verdict at that horizon (residual memory monotone against the half-life, optimum $H\to0$), and the intraday replay then *validated* the memory mechanism (interior optimum near a tenth of a day, OU-shaped decay) while measuring its directed spatial carrier behind the messages on the ETF triangle — so it stays opt-in, both verdicts recorded, not overwritten, an instance of the "measure first" rule of "The design rules that recur". Even the in-app autotune is the production leave-one-out harness, scoring candidate reach $\eta$ on real hold-outs rather than on a synthetic sandbox.

Two scoring conventions, used everywhere the graph is evaluated: *skill* is the reduction in held-out ATM error versus the transported-prior baseline, in ATM vol bps — positive means the graph beat mechanical transport; $\zeta$ is the standardized held-out residual (realized error divided by the posterior credible band), so $\operatorname{std}\zeta=1$ means the bands are honest, $>1$ overconfident (too narrow), $<1$ conservative. Skill is measured at scale: on the 25-asset benchmark across three historical regimes ($\sim$47k held-out scores), neighbour-supported indexes gain $+10$ to $+76$ ATM vol bps over the transported-prior baseline and ETFs $+3$ to $+7$; fully-dark single names behind lit indexes/ETFs — the product case — gain $+7.9$ to $+14.2$ bps in the August-2024 spike and $+3.8$ to $+7.2$ fully out-of-sample in the October-2022 bear, with unbiased standardized residuals. In the calm July-2023 regime the dark-name skill is $\approx0$ (never negative): single-name moves there are earnings-idiosyncratic, and the graph carries shared repricing, not idiosyncratic news. The one weakness that measurement flagged — calm-regime dark-name bands at $\operatorname{std}\zeta\approx1.9$, overconfident — is now closed for the ATM level: an *idiosyncratic band floor* (a strictly causal floor built from the node's own trailing unexplained moves while lit, on by default in production) moved the two calm cells $1.91\to1.02$ and $1.85\to1.03$ with the posterior mean untouched. Widening the skew/curvature bands in idiosyncratic tape remains open (Note 14).

> **Figure 3 — A fragment of the smile graph (figure not included in this pack; original is a node-edge diagram).** A fragment of the smile graph: lit index nodes (solid) inform dark single-name nodes (dashed) across both calendar and cross-asset edges. The graph posterior reconstructs the dark smiles from the lit innovation. *Description:* The diagram shows two rows of three circular nodes each. The top row, labelled SPX, holds lit nodes $T_1$, $T_2$, $T_3$ drawn solid; the bottom row, labelled AAPL, holds the same three expiries drawn dashed — dark. Teal "calendar" edges run horizontally along each row ($T_1\to T_2\to T_3$), and grey "index $\to$ name" edges run vertically from each SPX node down to the matching AAPL node. The picture states the propagation pattern in miniature: a lit index surface informs a fully dark single name through per-expiry cross-asset edges, while calendar edges tie each name's own expiries together.

## 5. Capability catalogue

Table 1 indexes what the app can do against the note that documents the mathematics. It doubles as a reading order.

**Table 1 — Capability $\to$ note index.**

| Capability | Summary | Note |
|---|---|---|
| LQD smile model | Arbitrage-free-by-construction log-quantile density; analytic Jacobian | 01 |
| SVI / SVI-JW | Raw and jump-wing SVI; structural chart, buffered Lee cap, belly certificate + one-shot repair | 02 |
| Multi-Core Sigmoid (MCS) | Sigmoid base + zero-wing hats for WW/event smiles | 03 |
| Local volatility | Jointly calibrated piecewise-affine local-*variance* surface (Dupire); GN/Numba calibration | 04 |
| De-Americanization | CRR tree + bisection, Numba kernel, cache digest, wing convex repair | 05 |
| Forwards / dividends | Parity forward + discount clamp, discrete divs | 06 |
| Weighting & bid–ask | Equal / time-value-density weights; band/haircut fit | 07 |
| Variance-swap targets | Replication, LQD closed form, source-PDE | 08 |
| Wings & Lee bounds | Tail control unified across models | 09 |
| Calendar arbitrage | Convex-order soft hinge, model-agnostic | 10 |
| Event variance clock | Dual calendar/variance time, day-weighted events | 11 |
| Spot–vol dynamics | Sticky strike/moneyness/local-vol, SSR transport | 12 |
| Prior persistence | 7-mode Bayesian menu, precision gate, two-pass | 13 |
| Graph extrapolation | Transported prior + directed increments; opt-in precision messages + layered dynamics; LOO backtest | 14 |
| Observation Kalman filter | Per-handle temporal denoising of the ATM handles; one-stage MAP active mode | 15 |

**Viewer and data capabilities (engineering, not derived here).** The workspace is organized into eight tabs — Parametric, Local Vol, Forwards, Options, Graph, Quality, Universe and View: charts of prior/current fit vs. quote bands in normalized or fixed strike, quantile and density functions, term structure and event-dilated calendar in vol and variance, var-swap levels, interactive quote select/erase/amend, universe selection, lit/dark node maps, and the graph editor. The Quality tab aggregates publish-readiness per node (fit quality, arbitrage diagnostics — including the belly certificate — and data-age staleness) and drives the export/reporting path; the same gates feed the client-facing certification report ("The design rules that recur"). Data plumbing (providers — including Massive intraday history via flat files where entitled — as-of replay, dividend editor, persistence of named universes and fit history) is described in the project README rather than in this mathematical series.

> **Remark (Current scope and limits).** What the application is *not*, as of this writing. The live universe is desk-scale: validation ran on a 25-asset, three-regime benchmark, and the graph solver is dense — comfortable to a few thousand nodes; a sparse solver is deferred until a universe needs it. The server is a single-process application state, deployed hosted single-tenant first; market-data entitlements are bring-your-own. Sub-daily expiries (0DTE) are research/replay-grade — their exit gates (bitwise replay, hard publish block, warm-slice latency) are certification-locked, but live 0DTE is a post-hosting, client-entitled feature. The app fits, extrapolates and publishes vanilla implied-vol surfaces: it does not price or risk-manage exotics, route orders, or forecast — dividends, borrow and forwards are inputs or option-implied estimates, never predictions.

## 6. The design rules that recur

Reading the series end to end, a handful of design rules appear again and again — each learned from a production incident, each now documented as a *case file* in its note. They are worth stating once as the app's engineering philosophy.

1. **The confinement principle** (Note 09). A constraint comparing *two* curves is sampled only where data pins both; a constraint intrinsic to *one* curve holds everywhere, wings included. Four instances: the calendar floor (confined, Note 10), the LV convex wing (confined, Note 04), the MCS Durrleman penalty (extended, Note 03), the de-Am convexity repair (extended, but its *authority* confined to the quoted band, Note 05).
2. **Trust the well-identified parameter.** The parity forward keeps the price level and refuses the noisy slope (Note 06); the prior gate trusts the market exactly where quotes identify a feature and yesterday exactly where they do not (Note 13).
3. **Persist shape, not level.** Operators and factors are level-invariant baskets, so an overnight jump is never damped (Note 13); the graph propagates *increments*, so "no change" is the default dark-node answer (Note 14).
4. **Route each model through its native object.** The var-swap is a closed form for LQD, arithmetic for SVI/MCS, a source PDE for LV (Note 08); the calendar constraint is the asset share for LQD and a total-variance hinge for the overlays (Note 10). Uniform implementations across non-uniform models are a trap.
5. **Measure first, fix second.** The short-dated LV failure was convicted by per-expiry counts before any model change (Note 04); the MCS wing penalty sits where the arb census located the violations (Notes 03, 09); the temporal backtests score priors, the graph and the observation filter against honest held-out baselines (Notes 13–15).

Table 2 indexes the production incidents documented across the series — the fastest way to learn the system is arguably to read these first. The index is not only documentation. Incidents marked † are registered, essentially verbatim, as named cases of the *certification pack* (`backend/backtest/certification.py`): 22 cases across three dimensions — market regimes, data failures, model stress — each pointing at the pytest locks that regression-guard it forever, so validation and production share one definition instead of drifting apart. One command (`python -m backtest.certification run`) re-executes every lock and emits a client-facing HTML report. In this series a case file is an *executable* object: the fastest way to learn the system is to read the incidents, and the fastest way to trust it is to run them.

**Table 2 — Case-file index: production incidents and their lessons.**

| Incident | Lesson | Note |
|---|---|---|
| The Lee cap that sat exactly on the broken boundary ($\beta=2$ passes the floor and wing screens with zero penalty yet $g(10)=-0.0485$; a live SPY wing sat at $2.0000$ — cap now $1.95$) † | a fence must not end on the broken boundary | 02, 09 |
| The certified-looking slice with a negative belly (Axel Vogt's classical parameters pass every wing screen; $\min g\approx-0.033$ mid-range — now the 801-point certificate gates publish) † | screens fence the wings; certify the belly | 02 |
| The six-day weekly that broke the LV strike grid (fit RMS $108\to23.5$ vol bp after the fix) † | measure first; per-expiry coverage floors | 04 |
| The convex wing that flattened SPY (fit RMS $25.7\to2.6$ vol bp once the constraint left the quoted range) † | constraints stay off quoted territory | 04 |
| The reverted global de-Am repair (ATM smile gap) † | repairs need confined authority | 05 |
| The delayed feed that gapped the ATM smile (discount clamp; failed rate-anchor) † | trust the well-identified parameter | 06 |
| The fit that took minutes (var-swap replication in the Jacobian) | native-object routing | 08 |
| The MCS that invented a put wing (R3$\times$R6 ablation, in-sample RMS: input repair alone $92\to25$ vol bp, output penalty alone $749$, both together $225$ with the violation gone) | input repair and output penalty compose | 09, 03 |
| The phantom calendar (NVDA/SPY flattened; the $151$-vol-bp flattening reproduced, then $\to0$ under confinement) † | the confinement principle | 10, 09 |
| The jump the strike anchor damped (operators persist shape) | persist shape, not level | 13 |
| The backtest that confirmed the hybrid default ($\sim$32 vol bp better on the held-out wing, 1117 nodes) | defaults are chosen by held-out evidence | 13 |
| The transient-name topology defect (cross-asset skill exactly $0.000$ bp) † | exact zeros are disconnection, not damping | 14 |
| The chart benchmark whose headline favoured the wrong arm (the raw SVI chart's lower arb rate was a survivorship artifact of its non-converged third; conditioned on convergence, the structural chart won every regime median) | condition on convergence before comparing arms | 02 |
| The A/B campaign whose arms were byte-identical (a config-hash change silently purged the residual store on every pair, so all four variants collapsed to the control) | an ablation must first prove its arms differ | 14 |
| The close-strike contradiction vs. the true gap (per-handle Kalman gains level/skew/curvature $=0.80/0.72/0.03$: high where quotes contradict, near zero where they are simply absent) | noise is not a gap: filter and prior split the work | 15 |
| The off-diagonal blow-up on coarse chains (cross-handle updates moved ATM vol by $3$–$28$ vol *points*) | per-handle updates; caps do not police cross-gains | 15 |

## 7. How the notes are organized

The topic notes, 01–15, are standalone and follow a common skeleton, codified in the series style guide (`Docs/notes/STYLE_GUIDE.md`): an opening that states the *production problem* and the *invariants* being protected (the amber box near the top of every note), a theorem-shaped body whose central object gets the note's single boxed equation, a worked example or *case file* told as a production incident, a *traceability table* tying each claim to its module and locking test, and three appendices — **A, a hyperparameter atlas** (every knob, surfaced or hidden, with its default), **B, performance** (measured optimizations, including the rejected ones), and **C, a reference implementation** ($\le50$ lines, executed against the production module before being committed). Figures run through the shared `figures/style.py` and their captions state the lesson, not the axes. Notes cross-reference each other (this note's Table 1 is the index) but never depend on one another's internals. Numbers and plots are *measured*, not copied: where a fresh run differs from an older design note, the fresh run wins. Every topic also carries one or more standalone *lecture editions* — tellings from a fresh angle (Note 01's percentile ruler, Note 02's two languages and its moment map, Note 14's three priors for a dark universe, …) — written to the register codified in `Docs/notes/LECTURE_REWRITE_GUIDE.md`. As of 2026-07-27 the lecture editions are the *prevailing* technical notes — audited against the code to the same standard — and the numbered series, this overview included, is kept as reference. This overview is the deliberate exception to the skeleton — it is a map, not a theorem, so it carries no boxed central equation, no traceability table and no performance or reference-implementation appendix; its single appendix is the control index below.

## Appendix A. Principal calibration controls

A *curated* index of the principal tunable parameters: surfaced (the user-facing `FitSettings` and `OptionsSettings`) and hidden (internal constants). It is deliberately not exhaustive — the single source of truth is the Pydantic schema pair in `volfit/api/schemas.py`, whose field docstrings state each knob's unit, activation condition and effect, plus each topic note's Appendix A. (Workflow and data-fetch controls — spot polling, chain refetch cadence, streaming refit — live in the same schema and are omitted here as non-calibration knobs.) Each row points to the note that derives its role; defaults are the shipped values. This is a directory, not a derivation — consult the referenced note for meaning.

**Table 3 — Surfaced parameters (principal; the schema is exhaustive).**

| Parameter | Default | Role | Note |
|---|---|---|---|
| `model` | `lqd` | smile family: `lqd` / `svi` / `sigmoid` (MCS) | 01–03 |
| `nOrder` | $16$ | LQD Legendre order (range $4$–$24$) | 01 |
| `regLambda` / `regPower` | $10^{-6}$ / $1$ | LQD high-order ridge | 01 |
| `barrierCenter` / `barrierScale` | $0.90$ / $50$ | LQD $A_R$ barrier | 01 |
| `nCores` | $2$ | MCS hat count (schema-clamped at 2) | 03 |
| `sigmoidRidge` | $10^{-2}$ | MCS hat-amplitude ridge | 03 |
| `sivWingPenaltyPct` | $100$ | MCS put-wing Durrleman penalty ($0=$ off) | 03 |
| `sviPenaltyWeight` | $10^{3}$ | SVI no-arbitrage penalty | 02 |
| `leeSlopeMax` | $1.95$ | SVI Lee wing-slope cap, strictly buffered under Lee's bound ($2.0$ = the broken boundary, explicit config only) | 02, 09 |
| `sviChart` | `structural` | SVI optimization chart (every iterate fence-clean); `raw` = historical rollback | 02 |
| `bellyRepair` | on | one-shot belly-hinge repair refit when the certificate fails (kept only if it certifies) | 02 |
| `fitMode` | `mid` | mid / bidask / haircut | 07 |
| `weightScheme` | `equal` | equal / tv-density weights | 07 |
| `haircut` | $0.005$ | band haircut (vol) | 07 |
| `midAnchorWeight` | $0.05$ | band mid anchor | 07 |
| `varSwapEnabled` | on | var-swap quotes surfaced + penalized | 08 |
| `varSwapWeightPct` | $10\%$ | var-swap budget | 08 |
| `varSwapMethod` | `static` | LV model var-swap: strike replication / source PDE | 08 |
| `jointCarry` / `jointCarryEngageBp` | off / $25$ | joint borrow/de-Am fixed-point forwards, engaged per expiry above the borrow gate (below it the parity forward is kept exactly) | 05, 06 |
| `enforceCalendar` | on | ascending-$T$ calendar coupling of Calibrate | 10 |
| `surfaceSolver` | `symmetric` | calendar coupling: screen + joint GN repair of violating runs (`sequential` = legacy one-sided floor) | 10 |
| `calendarWeight` | $10^{6}$ | calendar soft-constraint penalty | 10 |
| `extrapEnforce` | off | tapered no-arb enforcement in the extrapolated region (advisory measurement always on) | 09, 10 |
| `eventsEnabled` | on | event variance-clock master switch | 11 |
| `normalizeEvents` | off | rescale so the 1Y day-weight budget stays 365 | 11 |
| `gridStrikeMode` | `delta` | LV strike-vertex placement (`delta` / `linear`) | 04 |
| `gridXNodes` | $12$ | LV strike vertices — a *floor* in delta mode, exact only in linear mode | 04 |
| `gridXMinPerExpiry` | $8$ | LV short-dated coverage floor | 04 |
| `gridTNodes` | $10$ | *floor* on positive LV time vertices (the base set — $0$, pre-front node, every lit expiry — is always kept) | 04 |
| `gridRegLambda` / `gridRegRho` | $10^{-2}$ / $1$ | LV roughness penalty / ratio | 04 |
| `convexWingWeight` | $10^{3}$ | LV wing-convexity penalty (`convexWing` off by default; tail-confined) | 04 |
| `frontTieWeight` | $10^{-2}$ | ties the free $t=0$ row to the first data-identified row | 04 |
| `lvVolCapMult` | $3.0$ | LV local-vol cap multiple | 04 |
| `leftWingSlopeMult` | $1.5$ | LV left-wing extrapolation slope multiple | 04 |
| `timeScheme` | `implicit` | LV PDE time scheme (`rannacher` opt-in) | 04 |
| `lvSolver` | `gn` | LV solver: matrix-free GN / scipy trf | 04 |
| `lvFastKernel` | on | Numba vectorized-Thomas Dupire march | 04 |
| `lvEarlyStop` | on | LV cold-fit early stop at the RMS stall | 04 |
| `localVolEnabled` | on | LV calibration + workspace master switch | 04 |
| `dynamicsRegime` | `sticky_strike` | spot–vol regime seed | 12 |
| `ssr` | $2.0$ | SSR value of the `custom` regime (inert otherwise) | 12 |
| `priorPersistenceMode` | `hybrid` | prior mode selector | 13 |
| `priorOperatorSet` | ATM, RR25, BF25, VarSwap | operators to persist | 13 |
| `priorOperatorStrengthPct` | $50\%$ | operator prior budget | 13 |
| `priorOperatorRequiredPrecision` | $1.0$ | operator activation gate | 13 |
| `priorOperatorGapExponent` | $1.0$ | gate exponent $\gamma$ | 13 |
| `priorOperatorBandwidth` | $0.06$ | operator leg KDE bandwidth | 13 |
| `priorOperatorCovarianceMode` | `diagonal` | operator covariance route (`full` = Jacobian-propagated) | 13 |
| `priorDataOnlyPrepass` | off | two-pass activation (measure precision data-only, then refit) | 13 |
| `priorFactorSet` | ATM, skew, curvature, VarSwap | smile factors to persist | 13 |
| `priorFactorStrengthPct` | $50\%$ | factor prior budget | 13 |
| `priorTailAnchorStrengthPct` | $20\%$ | hybrid tail-anchor budget | 13 |
| `priorAnchorWeightPct` | $50\%$ | strike-gap prior budget | 13 |
| `graphKappaScale` $\kappa$ | $1.0$ | graph temporal precision | 14 |
| `graphEtaScale` $\eta$ | $1.0$ | graph directed smoothness | 14 |
| `graphLambdaScale` $\lambda$ | $0.0$ | graph OT regularization ($0=$ OT term off) | 14 |
| `graphNu` $\nu$ | $0.1$ | graph UOT source allowance | 14 |
| `graphPropagationMode` | `precision_messages` | propagation-operator seed (flipped 2026-07-27 on the intraday replay evidence; `smooth_field` = explicit rollback, `hybrid` config-only; the layered dynamic-harmonic pipeline is a per-request opt-in) | 14 |
| `idioFloor` | on | dark-node idiosyncratic credible-band floor | 14 |
| `functionalBand` | on | full 3-handle posterior covariance pushed through the slice map: smile band, var-swap and tail-mass sds (band-only) | 14 |
| `observationFilterMode` | `off` | filter off / overlay / active (MAP) | 15 |
| `filterCovarianceMode` | `jacobian` | measurement-covariance route | 15 |
| `filterProcessVolBpSqrtDay` | $30$ | ATM clock process noise (bp/$\sqrt{\text{day}}$) | 15 |
| `filterProcessSkewSqrtDay` | $0.02$ | skew clock process noise | 15 |
| `filterProcessCurvSqrtDay` | $0.05$ | curvature clock process noise | 15 |
| `filterTransportNoiseScale` | $0.10$ | process std per unit transport distance | 15 |
| `filterResidualInflation` | on | contradiction reads as measurement noise | 15 |
| `filterAdaptiveSigma` | $3$ | innovation-gated adaptive $Q$ ($0=$ off) | 15 |
| `filterMaxGain` | $1.0$ | per-handle own-gain safety cap | 15 |
| `filterResetHours` | $96$ | maximum data gap predicted across | 15 |
| `filterClock` | `calendar` | filter time base; `session` = intraday session clock (a session carries $0.60$ of a day's variance, non-trading days $0$) | 15 |
| `filterDataOnlyPrepass` | off | strictly persistence-free measurement | 15 |
| `autoCalibrate` | on (gated live server: off) | fetch$\to$fit workflow gate; off = fits wait for explicit Calibrate | — |

Per-ticker *market state* — the scheduled-event calendar driving the variance clock (Note 11), dividends, rates, forward policy, var-swap quotes and lit/dark marks — is data, not a setting: it lives in the per-ticker session state, is edited in the workspaces, and bumps only that ticker's version ("What the application is", invariant 4).

**Table 4 — Hidden internal constants (selected).**

| Constant | Default | Role | Note |
|---|---|---|---|
| `Z_MAX` / `N_POINTS` | $40$ / $8001$ | LQD quadrature grid | 01 |
| `OPT_N_POINTS` | $2001$ | LQD optimization grid | 01 |
| `EPS_AR` | $10^{-6}$ | LQD $A_R<1$ buffer | 01 |
| `_CERT_POINTS` / `CERT_G_TOL` | $801$ / $10^{-4}$ | belly-certificate grid and $g$ tolerance | 02 |
| `DEFAULT_N_K` | $1201$ | LV *validator/reprice* PDE strike nodes (the affine calibration march has its own grid) | 04 |
| `DEFAULT_DT_MAX` | $1/400$ | LV validator/reprice PDE max time step | 04 |
| `N_RANNACHER` | $4$ | LV validator/reprice Rannacher start steps | 04 |
| `VAR_FLOOR` | $10^{-6}$ | Dupire local-variance floor | 04 |
| `DEFAULT_STEPS` | $501$ | CRR scalar tree depth | 05 |
| `DEFAULT_BATCH_STEPS` | $192$ | CRR batch tree depth | 05 |
| `BATCH_BISECTIONS` | $24$ | de-Am bisection sweeps | 05 |
| `SIGMA_LO` / `SIGMA_HI` | $10^{-4}$ / $4$ | implied-vol bracket | 05 |
| `VS_HALF_WIDTH` / `VS_POINTS` | $6$ / $801$ | var-swap replication grid | 08 |
| `CAL_STRIDE` | $25$ | calendar constraint stride | 10 |
| `DAYS_PER_YEAR` | $365$ | calendar$\to$variance clock | 11 |
| `SPREAD_HALF` | $0.05$ | precision spread half-width | 13 |
| `OBS_FRESHNESS_HALFLIFE` | $3$ d | observation freshness decay | 13 |
| `TRANSPORT_SCALE` | $0.10$ | prior transport precision decay | 13 |
| `HANDLE_CONFIDENCE` | $[1,1,0.01]$ | per-handle graph confidence | 14 |
| `SOURCE_BASE` | tiered | prior provenance precision | 14 |
| `IDIO_FLOOR_LAMBDA` | $0.30$ | idio band-floor strength ($\mathrm{sd}^2 \ge \lambda\,\sigma_I^2$) | 14 |
| `IDIO_EWMA_HALFLIFE` | $5$ d | idio innovation-RMS half-life | 14 |
| `DIAGONAL_UPDATE` | on | per-handle scalar Kalman gains | 15 |
| `RESID_INFLATION_CAP` | $25$ | cap on the contradiction inflation | 15 |

**Reading the index.** A surfaced parameter is a *policy* choice — how strong a penalty, which prior mode, how to weight quotes — safe to tune. A hidden constant is tied to an algorithm's correctness (the $A_R$ buffer, the PDE floor, the tree depth) and is exposed only in the relevant note's Appendix A, where the consequences of changing it are spelled out. Together with those note-level appendices this index maps the fitter's control surface; the schema modules in `volfit/api/` remain the exhaustive, always-current record.


