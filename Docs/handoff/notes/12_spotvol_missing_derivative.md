# The Missing Derivative

**Note 12 — spot–vol dynamics and the skew-stickiness ratio · lecture edition ("what a surface cannot tell you: smile transport, the SSR, and the one regime that derives its own answer") · converted from 12_spotvol_missing_derivative.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** A calibration delivers $\sigma(k,T)$ at one spot; hedging needs $\partial\sigma/\partial(\text{spot})$, and no snapshot contains it — through every arbitrage-free surface passes a family of equally admissible tomorrows. This lecture develops the Vol-Fitter's spot–vol dynamics from that gap. The missing derivative is one number per unit of skew: requiring a first-order transport to preserve the smile's shape leaves exactly a re-indexing plus a level, and the single free scalar is the skew-stickiness ratio $R$ — sticky-moneyness ($R=0$), sticky-strike ($R=1$), sticky-local-vol ($R\approx2$) are points on one dial, realized by a one-line transport. The stakes are not academic: on the live long-dated SPY smile (ATM skew $-0.354$ per unit log-moneyness) the regime choice moves an OTM put's delta by 19.7 delta points — same book, same surface. The lecture's second half is the regime that *answers* instead of asks: freezing the local-volatility surface in absolute strike determines the transport exactly (the Hagan log-moneyness map, whose ATM expansion reads the old curve two units per unit move — the famous $R\approx2$ is the half-rule "implied skew is half the local skew" in motion), diverging from the linear transport by up to 111 vol bp in the wings on a 5% move; and the exact frozen-grid Dupire reprice, for which the SSR is an *output*: measured across maturities it runs from 2.09 at seven weeks to 2.00 at eighteen months on a time-homogeneous surface, hugging the theoretical short-maturity limit of $2$. Every transport is recalibration-free arithmetic; the one exception — the exact reprice — pays one Dupire solve and is chosen explicitly.

**Contents.** 1. The derivative the data does not contain · 2. One free parameter · 3. The regime that answers: frozen local volatility · 4. One transport through the whole pipeline · 5. What is genuinely original here · 6. Limitations · Appendix A. Hyperparameter atlas (with performance notes) · Appendix B. Traceability · Appendix C. Reference implementation · References

## 1. The derivative the data does not contain

A calibrated surface is a snapshot at one spot. The next tick moves spot, and the desk needs the new smile now — faster than a recalibration, and consistently with *some* view of how smiles move. The uncomfortable fact first:

**Remark 1 (Dynamics are not identified by a snapshot).** Fix today's arbitrage-free surface $\sigma_0(k,T)$. For any smooth one-parameter family $\sigma_\eta(k,T)$ of arbitrage-free surfaces with $\sigma_{\eta=0}=\sigma_0$, the hypothesis "after a log-forward move $h$ the surface is $\sigma_{\eta(h)}$" is consistent with every price quoted today. Today's quotes constrain today's marginals (Notes 01–10); the derivative along spot is extra structure the desk must *choose* — or derive from a model, which is "The regime that answers: frozen local volatility". Stochastic-volatility modelling constrains the choice (Bergomi's short-dated bounds put one-factor models between the sticky-strike and sticky-local-vol answers [Bergomi2016]) but no static surface selects a point.

The choice has a price tag. A vanilla's spot sensitivity is the Black delta *plus* vega times the missing derivative, so two desks holding the same book against the same surface but different dynamics carry different deltas. Figure 1 computes it on the live SPY smile: at a representative OTM put strike the sticky-moneyness and sticky-local-vol deltas sit 19.7 delta points apart. The regimes of this note are not a display preference; they are hedge ratios.

> **Figure 1 — The stakes (figure not included in this pack).** The stakes (live SPY smile, production Black machinery, transports finite-differenced through the production rule). Total call delta — Black delta plus the smile response — under the three canonical regimes. At the marked put strike the choice of dynamics is worth 19.7 delta points on the same book against the same surface. Exercise 1 derives the gap as $\mathrm{vega}\cdot(R-1)\,s_0$ per unit $R$. *Description:* Total call delta plotted against strike on the live long-dated SPY smile under the three canonical regimes — sticky-moneyness ($R=0$), sticky-strike ($R=1$), sticky-local-vol ($R\approx2$) — each computed by finite-differencing the production transport through the Black machinery. The three curves separate away from the money, and at a marked representative OTM put strike the sticky-moneyness and sticky-local-vol deltas differ by 19.7 delta points. Since all three tomorrows are equally consistent with today's quotes, the exhibit converts "regime choice" from a display preference into a hedge-ratio decision.

> **Invariants protected in this note.**
> 1. Every transport is recalibration-free: a spot move refreshes the surface by arithmetic on existing objects. The one exception — the exact frozen-grid reprice — costs a single Dupire solve and is chosen explicitly.
> 2. $h=0$ is the identity in every regime.
> 3. The three sign rules of Assumption 1 are fixed once, implemented sign-for-sign, and independently test-locked.
> 4. Transports wrap *reads*; the calibrated anchor is never mutated (the graph layer of Note 14 deliberately consumes the un-transported anchor and transports its own baseline).

**Conventions and the notation ledger.** $T$ is maturity; $h=\log(F_{\mathrm{new}}/F_{\mathrm{old}})$ is the one move symbol (positive up). Subscripted $\partial$; no primes.

| Symbol | Meaning |
|---|---|
| $k,\ K,\ F,\ h$ | log-moneyness; strike; forward; move |
| $\sigma(k),\ w(k,T)$ | implied vol; total variance |
| $s_0,\ s_T$ | ATM skew $\partial_k\sigma\rvert_{0}$ (slice; at $T$) |
| $R$ | the skew-stickiness ratio (SSR) |
| $\ell_T(k,h)$ | the exact sticky-LV displacement |
| $\beta=1-\tfrac{R}{2}$ | grid barycenter weight |

*Table 1 — Every symbol in the note. One move symbol ($h$), one skew symbol family ($s$); $R$ is both the ratio and the regime dial.*

## 2. One free parameter

### 2.1 The sign discipline

Every sign error in smile transport comes from mixing two coordinate systems, so the conventions are fixed once and the code follows them sign-for-sign.

**Assumption 1 (Sign conventions).** (i) The move is $h=\log(F_{\mathrm{new}}/F_{\mathrm{old}})$: positive when the forward rises. (ii) Log-moneyness $k=\log(K/F)$ is always measured against the *prevailing* forward — so the same absolute strike has *lower* moneyness after an up-move: $k_{\mathrm{new}}=k_{\mathrm{old}}-h$. (iii) A transported *curve* is a function of new moneyness; a transported *quote* (a fixed strike) is a point whose moneyness label changes.

> **Caution.** Convention (ii) makes curves and quotes move in *opposite* directions in $k$. Under sticky-strike the vol at each fixed strike is unchanged; to express the *new curve* at new moneyness $k$, ask which old strike now sits there — the one whose old moneyness was $k+h$. The curve transport therefore reads *forward*, $\sigma_{\mathrm{new}}(k)=\sigma_{\mathrm{old}}(k+h)$ — a plus. But re-labelling an existing fixed-strike quote goes the other way: its new moneyness is $k-h$ — a minus. Both signs are correct, both are in production (the smile transport uses $k+h$; the local-vol view re-indexes stored quotes by $k-h$), and swapping either flips the skew response. Figure 2 draws both on one move; the sign-locking tests are the fence.

> **Figure 2 — The two signs, on one +4% move (figure not included in this pack).** The two signs, on one $+4\%$ move (live SPY smile, sticky-strike). A fixed strike keeps its vol but its *label* slides to $k-h$ (the quote rule, filled to open marker); the new curve at any $k$ *reads* the old curve at $k+h$ (the curve rule). Opposite directions, both correct, both in production. *Description:* The live SPY smile before and after a $+4\%$ forward move under sticky-strike, drawn in log-moneyness coordinates. A filled marker at one fixed strike slides to an open marker at moneyness $k-h$ — the same vol, re-labelled leftward by the quote rule. The new curve, meanwhile, is the old curve read at $k+h$: it appears shifted the opposite way. The panel makes the two-coordinate-system trap visible: the two correct signs point in opposite directions, and swapping either one flips the smile's apparent skew response.

### 2.2 The transport, and why it has exactly one dial

Ask for the simplest transport consistent with Assumption 1: built from the two operations a curve admits without changing its shape — a re-indexing and a level shift. The re-indexing is forced: expressing unchanged fixed-strike vols in new moneyness *is* $\sigma_{\mathrm{old}}(k+h)$ (the caution above), and any other displacement would shear the smile against its own strikes. What remains free is one scalar — the level — and parametrizing it per unit of skew-times-move gives the production transport — the note's central equation —

**Central equation.**

$$
\sigma_{\mathrm{new}}(k)
=\sigma_{\mathrm{old}}(k+h)+(R-1)\,s_0\,h .
\tag{1}
$$

**Proposition 1 (ATM response; the dial is the SSR).** *Under equation (1), to first order in $h$ the ATM vol moves by $\Delta\sigma_{\mathrm{atm}}=R\,s_0\,h$; hence*

$$
R=\frac{\mathrm{d}\sigma_{\mathrm{atm}}/\mathrm{d}\ln F}{s_0},
$$

*the skew-stickiness ratio: the fraction of the skew realized as an ATM-vol change per unit log-spot move.*

*Proof.* $\sigma_{\mathrm{new}}(0)=\sigma_{\mathrm{old}}(h)+(R-1)s_0h=\sigma_{\mathrm{old}}(0)+s_0h+(R-1)s_0h+O(h^{2})$. ∎

> **Heuristic.** Read $R$ as "how much of the skew is real." The skew says lower strikes carry higher vol. When spot drops, does the ATM vol rise to where the old lower-strike vol was ($R=1$, sticky-strike), not move at all in moneyness terms ($R=0$, sticky-moneyness — the smile rides the forward), or *overshoot* ($R\approx2$, sticky-local-vol, the empirically common short-dated regime)? Derman's classic taxonomy [Derman1999] named the regimes; $R$ interpolates them, and equation (1) realizes any value — named regime or custom number — by arithmetic.

Figure 3 runs the production transport on the live SPY slice: the fan of tomorrows after a $-5\%$ move, and the linear ATM responses of slope $R\,s_0$. The transport is one line, verified against production to $1.0\times10^{-17}$ ("Reference implementation"), where its algorithm specification is given.

> **Figure 3 — The fan of tomorrows (figure not included in this pack).** The fan of tomorrows (live SPY 2027-06 smile, production transport). A: the same surface, three regimes, one $-5\%$ move — all three tomorrows are admissible, and today's quotes cannot choose (Remark 1). B: the ATM responses are linear with slope $R\,s_0$ (Proposition 1); the $R=0$ curve's slight bend is the second-order term the transport does not model. *Description:* Panel A shows the live SPY 2027-06 smile and its three transported versions after one $-5\%$ forward move, one per canonical regime: the sticky-moneyness tomorrow rides the forward unchanged in moneyness terms, sticky-strike shifts the curve by the re-indexing alone, and sticky-local-vol adds the largest level response — a fan of equally admissible tomorrows through one surface. Panel B plots the ATM vol change against the move size for each regime: the responses are linear with slope $R\,s_0$ as Proposition 1 states, with a slight visible bend in the $R=0$ curve marking the second-order term the first-order transport ignores.

**Exercise 1.** Combine equation (1) with the quote rule of Assumption 1 to show a *fixed strike's* vol responds as $\mathrm{d}\sigma_K/\mathrm{d}\ln F=(R-1)\,s_0$ — zero under sticky-strike, by construction. Hence the total delta correction is $\mathrm{vega}\cdot(R-1)s_0$ per unit forward, and the gap between $R=0$ and $R=2$ is $2\,\mathrm{vega}\,|s_0|$. Evaluate it with the Black vega at the marked strike of Figure 1 ($T=0.92$, $\sigma\approx23\%$, $s_0=-0.354$) and confirm the 19.7-point gap.

## 3. The regime that answers: frozen local volatility

Every value of $R$ in "One free parameter" is an *assumption*. There is exactly one regime in the fitter where the transport is *derived*: hold the local-volatility surface (Note 04) fixed in absolute strike, and the new implied surface is determined — no free dial left.

### 3.1 Why two: the half-rule

> **Heuristic.** For short maturities, implied vol at strike $K$ is approximately the average of local vol along the straight path from spot to $K$ — so the *implied* skew is about *half* the local skew. Freeze the local curve and drop the spot by $h$: the ATM implied now averages the local curve around the new spot, i.e. it slides along a curve whose slope is $2s_0$. The ATM response is $2\,s_0\,h$: the famous $R\approx2$ is nothing but the half-rule read in reverse. What the market's skew shows is half of what the frozen generator carries, and the motion pays out the other half.

### 3.2 The exact map

In total-variance form the linear transport of equation (1) is $\widetilde{w}^{R}(T,k)=w_0(T,k+R\,h)$. The exact frozen-LV transport replaces the linear displacement by the Hagan log-moneyness map

$$
w^{\mathrm{LV}}(T,k)=w_0\big(T,\;\ell_T(k,h)\big),
\qquad
\ell_T(k,h)=\log\!\big(e^{h}(e^{k}+1)-1\big),
\tag{2}
$$

the exact relabeling of moneyness when the local-vol surface is held fixed in absolute strike and the forward moves by $h$ [Hagan2002]. An optional ATM re-anchor ($\sigma_{\mathrm{atm}}\to\sigma_0+R\,s_T\,h$) makes the linear SSR response exact even for large moves. Expanding for small $h$,

$$
\ell_T(k,h)=k+\big(1+e^{-k}\big)h+O(h^{2}),
\qquad \ell_T(0,h)\approx 2h :
\tag{3}
$$

at the money the new smile reads the old curve *two* units of log-moneyness per unit move — the half-rule's factor again, now as the ATM slope of an exact relabeling, so $R\approx2$ is a theorem about frozen generators, not an empirical accident. Away from the money the displacement $(1+e^{-k})h$ is strike-dependent — larger on the put wing, smaller on the call wing — which is exactly what the linear transport flattens into a single level adjustment. Figure 4 measures the price of that flattening on the live smile: up to 111 vol bp in the wings at a 5% move, shrinking quadratically as $h\to0$ (the expansion of equation (3) is test-locked).

> **Figure 4 — Exact vs linear sticky-LV (figure not included in this pack).** Exact vs linear sticky-LV (live SPY smile, production transport both paths). A: at a $-5\%$ move the Hagan map (equation (2)) and the linear $R=2$ transport agree at the money and separate in the wings — up to 111 vol bp — because the exact displacement $(1+e^{-k})h$ is strike-dependent. B: the gap at a fixed put strike vanishes quadratically with the move: the linear transport is exactly the first-order truncation of equation (3). *Description:* Panel A overlays the two sticky-local-vol tomorrows of the live SPY smile after a $-5\%$ move — the exact Hagan-map transport and the linear $R=2$ transport: they coincide at the money by construction and separate progressively into the wings, by up to 111 vol bp, because the exact per-strike displacement $(1+e^{-k})h$ grows on the put wing and shrinks on the call wing while the linear transport spends one uniform level on both. Panel B plots the gap at one fixed put strike against the move size $h$ on a log scale: the gap decays quadratically as $h\to0$, confirming the linear transport as exactly the first-order truncation of the exact map.

### 3.3 The grid relabeling, and SSR as an output

When the dynamics are driven by the extracted local-vol *grid*, the whole taxonomy compresses into one rule for the strike nodes:

$$
K_i \longmapsto K_i\,e^{(1-R/2)h}
\qquad\Longleftrightarrow\qquad
x_i \longmapsto x_i-\tfrac{R}{2}\,h
\quad(\text{log-moneyness nodes}),
\tag{4}
$$

pinned in the tests to the exact triple $(x,\ x-\tfrac12 h,\ x-h)$ for $R=0,1,2$.

> **Heuristic.** Equation (4) is the cleanest statement in the note: a stickiness regime is a rule for *how the local-vol grid's strikes follow the spot*, and $\beta=1-R/2$ is the fraction of the move they follow — all of it ($R=0$, the grid rides the forward), half ($R=1$), none ($R=2$, the grid frozen in absolute strike). Everything else — the implied-vol shift, the ATM response, the Hagan map — is a consequence of that one rule.

For $R=2$ the frozen grid can be *repriced* through the Dupire PDE rather than transported analytically — the exact dynamics, at the cost of one PDE solve (the note's only non-arithmetic path, selected by its own regime name). Here the SSR stops being an input altogether: production reports the *realized* ratio $(\Delta\sigma_{\mathrm{atm}})/(s_0 h)$ of the reprice, and Figure 5 measures it across maturities on a time-homogeneous skewed surface: 2.09 at seven weeks, settling to 2.00 at eighteen months — hugging the theoretical limit $2$ of equation (3) from above, the small short-dated excess being the finite move and smile curvature the first-order theory ignores. The constant "$2$" in the regime table is only this curve's limit; the reprice is the truth it approximates.

> **Figure 5 — SSR as an output (figure not included in this pack).** SSR as an output (production Dupire solver; the local-vol grid held fixed in absolute strike, forward moved by $-2\%$, both surfaces repriced). The realized ratio runs from 2.09 at the shortest maturity to 2.00 at the longest, hugging the theoretical short-maturity limit 2 — measured, not assumed. *Description:* The realized skew-stickiness ratio $(\Delta\sigma_{\mathrm{atm}})/(s_0h)$ plotted against maturity, computed by holding a time-homogeneous skewed local-vol grid fixed in absolute strike, moving the forward by $-2\%$, and repricing both surfaces through the production Dupire solver. The curve starts at 2.09 at the shortest maturity and decays monotonically to 2.00 at eighteen months, approaching the theoretical short-maturity limit of 2 from above; the short-dated excess over 2 is the contribution of the finite move size and the smile curvature that the first-order expansion ignores. The exhibit's point is that in this regime the SSR is a measured output of the model, not an assumed constant.

**Exercise 2.** Derive the expansion of equation (3) from equation (2) ($\partial_h\ell_T=e^{h}(e^{k}+1)/(e^{h}(e^{k}+1)-1)$, evaluate at $h=0$). Then evaluate the displacement at $k=\pm0.3$ for $h=-5\%$ and explain the asymmetry of Figure 4A: the put wing moves $(1+e^{0.3})h\approx2.35h$ against the call wing's $1.74h$, so the linear transport — which spends one uniform level on both — errs most where the skew is steepest.

**Exercise 3.** Make the half-rule quantitative: for short maturities write implied variance as the average of local variance along the chord from spot to strike, differentiate at the money, and conclude implied skew $=\tfrac12\times$ local skew. Now freeze the local curve, move the spot, and recover $R=2$. Finally, reconcile with the measured 2.09 at $T=0.05$ in Figure 5: which two ingredients of the exact reprice does the half-rule argument drop?

## 4. One transport through the whole pipeline

Between calibrations the transport is applied at *read* time, never to the stored fit. A spot move wraps the cached anchor's displayed slice in a transported view (only its total-variance function is consulted — the wrapper is deliberately thin), re-labels the prepared quotes to $k-h$, and hands every consumer — smile, term structure, density, var-swap level, option table — the moved smile; the calibrated anchor itself is untouched (invariant 4). The local-vol workspace applies all three sign rules of Assumption 1 at once, per read: each reconstructed smile is wrapped in the curve rule, stored fixed-strike quotes are re-indexed by the quote rule, and the shared strike-node axis is relabelled by equation (4) using the longest expiry's $h$ as the representative move. The explicit scenario endpoint is the one consumer of the vol-space one-liner (the algorithm of "Reference implementation"); its sticky-grid variant routes to the Dupire reprice of Figure 5 and reports the realized ratio. A spot move bumps a per-ticker version, so only the moved name's derived grids are re-transported — one name's tick never touches the rest of the universe.

Two design decisions deserve their sentence. First, the fitted prior of Note 13 and the graph baseline of Note 14 are *themselves* transported: a prior calibrated at its own spot is moved to today's forward under the active regime before it anchors or draws, so the graph's innovation is measured against a dynamics-consistent baseline — and the regime choice measurably matters there (the stored graph backtest swept $R\in\{0,1\}$: $R=0$ over-credits the graph, $R=1$ bakes the leverage effect into the baseline). Second, the graph universe deliberately reads the *un-transported* anchor: transport is a view, and the network's state must not depend on who looked.

**Remark 2 (The honest gap, updated).** The local-vol view's *composite* transport (curve rule + quote rule + grid rule applied together) still has no dedicated unit test. Its three ingredients are each locked individually, and — new since the original note — an end-to-end integration test now drives the full composite through the API and asserts the grid relabel and fixed-strike invariance together. Unit-level coverage of the composition remains the right follow-up.

## 5. What is genuinely original here

The regimes are Derman's, the map is Hagan's, the SSR is Bergomi's; the contributions are structural.

1. *One dial, one line*: the transport of equation (1) realizes any SSR — named regime or custom number — as arithmetic on the existing curve, with the sign discipline of Assumption 1 making the two-coordinate-system trap explicit and test-fenced.
2. *The stakes made concrete*: the delta gap of Figure 1 prices the regime choice on a live smile — 19.7 delta points at one strike — turning "display preference" into "hedge ratio" with a measured number.
3. *The answering regime, graded exactly*: one parameter $R$ ties the linear shift, the Hagan map, and the frozen-grid reprice into a speed-for-exactness ladder, with the SSR of the exact rung measured as an output (Figure 5) rather than asserted as a constant — and the famous $2$ located precisely as that curve's short-maturity limit.

## 6. Limitations

Where the guarantees stop. *The transport is first-order and shape-frozen*: equation (1) moves level and label only — no convexity response, no vanna/volga term, and the $R=0$ panel of Figure 3B already shows the second-order bend it ignores. *$R$ is constant across strike and maturity* in the analytic path; the exact reprice (whose realized $R$ does vary, Figure 5) is the escape hatch, at PDE cost. *The regime is assumed, not estimated*: nothing in the product regresses realized ATM changes on skew to estimate the market's actual SSR — the dial is set by the desk (and Remark 1 is why the surface alone cannot set it). *Large moves need the re-anchor*: the linear ATM response degrades quadratically in $h$ (Figure 4B); the optional re-anchor restores it exactly at the money only. *The composite view's unit-test gap* (Remark 2) stands, integration coverage notwithstanding. And *the frozen-LV answer is only as good as frozen local vol*: empirically local vol is not invariant under spot moves — the exact reprice is the exact consequence of an approximate premise, which is why it is one regime on the dial and not the dial.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

| Knob | Default | Role |
|---|---|---|
| `dynamicsRegime` | `sticky_strike` | Named regime (`sticky_moneyness` / `sticky_strike` / `sticky_local_vol` / `sticky_local_vol_grid`) or `custom`. |
| `ssr` $R$ | 2.0 | Numeric SSR, consumed only when `dynamicsRegime` is `custom`. |
| $R$ regime map | $\{0,1,2,2\}$ | SSR of the four named regimes; the grid regime's 2 is only the short-maturity limit of its reprice (Figure 5). |
| ATM re-anchor | off | Optional exact linear SSR for large moves ($\sigma_0+R\,s_T\,h$). |

*Table 2 — Spot–vol-dynamics hyperparameters.*

**Performance.** The transport of equation (1) and the grid relabeling of equation (4) are $O(\text{grid})$ arithmetic — no optimization, no PDE — so a spot move refreshes the whole surface essentially for free. Only the exact frozen-grid reprice costs a Dupire solve, chosen explicitly by its regime name. A spot move bumps the per-ticker spot version, so only the moved name's derived grid is re-transported; the global spot version is deliberately *not* in the fit-cache key, so anchors stay warm.

## Appendix B. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

| Claim | Object | Code anchor · *Test anchor* |
|---|---|---|
| ATM moves by $R\,s_0\,h$; shape preserved | Proposition 1 | `volfit/dynamics/ssr.py` · *`tests/test_dynamics.py::test_atm_vol_moves_by_ssr_times_skew`; `::test_shape_is_preserved_up_to_level`* |
| $h=0$ is the identity in every regime | invariant 2 | `volfit/dynamics/transport.py` · *`tests/test_spot_transport.py::test_h_zero_is_identity_all_regimes`* |
| Sticky-moneyness / sticky-strike signs | equation (1) | `volfit/dynamics/transport.py` · *`tests/test_spot_transport.py::test_sticky_moneyness_leaves_smile_in_moneyness_unchanged`; `::test_sticky_strike_fixes_vol_at_fixed_strike`* |
| Hagan-map expansion; double-skew ATM response | equations (2), (3) | `volfit/dynamics/transport.py` · *`tests/test_spot_transport.py::test_ell_T_small_move_expansion`; `::test_sticky_local_vol_double_skew_atm_response`* |
| Grid rule pinned to $(x,\,x-\tfrac12 h,\,x-h)$; $\beta=1-R/2$ | equation (4) | `volfit/dynamics/transport.py` · *`tests/test_spot_transport.py::test_grid_node_rule_barycenter`; `::test_beta_of_canonical_values`* |
| ATM re-anchor hits the exact linear target; transported slice wraps only the variance function | "The regime that answers: frozen local volatility" | `volfit/dynamics/transport.py` · *`tests/test_spot_transport.py::test_atm_anchor_hits_exact_linear_ssr_target`; `::test_transported_slice_matches_function_and_vol`* |
| Frozen-grid reprice: ATM consistency and realized SSR reported | Figure 5 | `volfit/api/localvol.py` · *`tests/test_api_localvol.py::test_reprice_matches_fitted_atm`; `::test_sticky_grid_scenario_realized_ssr`* |
| Composite LV view transports without refit (integration) | Remark 2 | `volfit/api/affine_transport.py` · *`tests/test_spot_move_service.py::test_affine_lv_surface_transports_without_refit`* |
| Graph baseline transported under the active regime | "One transport through the whole pipeline" | `volfit/api/prior_transport.py` · *`tests/test_api_graph.py` ($R=0\Rightarrow$ ATM shift second order)* |

*Table 3 — Claims in this note and the code/tests that lock them.*

## Appendix C. Reference implementation

The algorithm below was executed against the production transport by this edition's generator on every run — four move/regime pairs including a custom numeric $R$ — agreeing to $1.0\times10^{-17}$ (floating-point identity). The exact-path figures consume the production total-variance transport directly (the Hagan branch for the named local-vol regime, the linear branch for numeric $R$ — the production dispatch rule); the reprice figure drives the production Dupire solver on the frozen and moved grids, never a re-implementation.

> **Algorithm — the SSR smile transport (equation (1)).** (Replaces the reference-implementation listing, distilled from the dynamics/SSR module; the pack carries no source code. Production's last argument accepts a named regime or a numeric $R$.)
>
> *Inputs:* the target log-moneyness grid $k$; the fitted vol curve $\sigma_{\mathrm{old}}(\cdot)$, evaluable at arbitrary moneyness; the ATM skew $s_0$; the spot return $r$; the SSR value $R$. *Output:* the transported curve $\sigma_{\mathrm{new}}$ evaluated on the grid.
>
> 1. **Log-forward move.** Convert the return to a log move $h=\log(1+r)$, evaluated in the numerically stable log1p form so small returns lose no precision.
> 2. **Re-index plus level.** Return $\sigma_{\mathrm{new}}(k)=\sigma_{\mathrm{old}}(k+h)+(R-1)\,s_0\,h$ at every grid node: the forced re-indexing of Assumption 1's curve rule plus the single free level of equation (1).
>
> *Production-agreement tolerance:* $1.0\times10^{-17}$ (floating-point identity) on every generator run, across four move/regime pairs including a custom numeric $R$.

## References

- [Derman1999] E. Derman. Regimes of volatility. *Risk*, April 1999.
- [Bergomi2016] L. Bergomi. *Stochastic Volatility Modeling*. CRC Press, 2016.
- [Hagan2002] P. Hagan, D. Kumar, A. Lesniewski and D. Woodward. Managing smile risk. *Wilmott Magazine*, 2002.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.

