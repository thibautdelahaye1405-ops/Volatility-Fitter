# The Unnamed Martingale

**Note 10 — calendar-arbitrage prevention across expiries · lecture edition ("calendar order as an existence theorem, and who pays to restore it") · converted from 10_calendar_unnamed_martingale.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** A fitted surface makes a promise it never spells out: that *some* arbitrage-free dynamics — a martingale the fitter neither builds nor names — could produce exactly these smiles. This lecture develops calendar-arbitrage prevention from that existence statement. By Kellerer's theorem the promise is precisely checkable: butterfly-free slices increasing in convex order admit a martingale with those marginals, and convex order has four equivalent inspection coordinates — normalized calls, the laws themselves, integrated upper-quantile curves, total implied variance — so each model verifies the one it already owns (for LQD the integrated-quantile curve *is* the asset-share array every built slice carries; the parametric overlays hinge total variance against the previous displayed slice; the local-vol surface keeps the promise by construction). On a live SPY surface the promise holds with a margin of 0.9 variance bp everywhere two expiries are jointly quoted, while their drawn extrapolations disagree by up to 21 variance bp — which is why *where* the order is inspected is half the design: the confinement case file (the phantom calendar that flattened live NVDA and SPY fits, reproduced here at 151 vol bp of damage under a wide floor grid vs 0.0 under the confined one) and a measured rejection of the quantile coordinate for confinement — a $G$-space floor drags an innocent far fit by 1095 vol bp, still 228 after windowing, because $G$ integrates the whole upper tail; the production floor compares *prices at fixed strike*, 10.6 bp, indistinguishable from no floor. The other half is *who pays* when slices genuinely conflict: the historical sequential pass bulldozes the latecomer (near untouched at 4.8 bp, far conceding 547), while the shipped symmetric solver — independent fits, a vega-normalized screen, then one joint Gauss–Newton over the violating component — shares the concession (414/254 bp), cures the order to $3.2\times10^{-6}$ in total variance, and leaves clean ladders byte-identical to their independent fits.

**Contents.** 1. The promise · 2. The existence theorem · 3. Four faces, one cheap check per model · 4. Where the order may be inspected · 5. Who pays: the symmetric repair · 6. The extrapolated region: measure, lean, repair · 7. What is genuinely original here · 8. Limitations · Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation · References

## 1. The promise

Figure 1 is a live SPY surface: six expiries, each fitted independently well, drawn as one family. Where two adjacent expiries are both quoted, the later curve sits strictly above the earlier one — with a worst margin of 0.9 variance bp — and that ordering is not an aesthetic: it is the entire difference between six good smiles and one coherent *surface*. A desk that trades the surface trades between expiries: forward-starting variance, calendar spreads, rolls. Each such trade prices a claim on what happens *between* two slices, and the slices only admit a consistent in-between if they stand in the right order.

> **Figure 1 — The promise, held live (figure not included in this pack).** The promise, held live (SPY, Massive feed, 6 expiries, published production fits). Thick segments mark each slice's quoted span: on every common traded span the later expiry dominates — convex order with 0.9 variance bp to spare at the tightest pair. The faint tails are the drawn extrapolations, which disagree by up to 21 variance bp out where no quote exists — the region "Where the order may be inspected" rules out of bounds for any two-curve comparison. *Description:* Six total-variance curves from published production SPY fits, stacked by maturity, each drawn with a thick segment over its own quoted strike span and faint thin tails beyond it. On every interval where two adjacent expiries' thick segments overlap, the longer-dated curve sits strictly above the shorter-dated one, with a worst-case margin of 0.9 variance bp at the tightest pair — the live surface keeps the convex-order promise where data exists. In the faint extrapolated tails the curves interleave and disagree by up to 21 variance bp, which the note will argue is precisely the region where no two-curve comparison has jurisdiction.

This lecture is about what exactly that order buys, per model and per pair of slices; the organizing statement is an *existence theorem*. A butterfly-free slice (Notes 01–04) certifies that a valid law exists at one date. The calendar condition certifies something stronger and strictly cross-sectional: that some *martingale* — some arbitrage-free dynamics the fitter never constructs — has exactly these laws as marginals. The fitter's product is a family of still photographs; the promise is that a film exists whose frames they are. No frame is ever named, no film is ever shot, and yet the promise is falsifiable frame by frame — that is the content of Theorem 1 and Theorem 2 below.

**Assumption 1 (Units and carry).** Each expiry is normalized by its own forward: $Y_T=S_T/F_T$ (so $\mathbb{E}[Y_T]=1$ for every $T$), quotes live at fixed log-moneyness $k=\log(K/F_T)$, and rates, borrow and dividends are deterministic and absorbed into $F_T$ (Note 06). Comparisons across maturity are made at fixed $k$ — fixed *forward* moneyness, not fixed cash strike. Discrete cash dividends make the cash-strike statement fail while the normalized one survives; stochastic rates would break the equivalence between calendar spreads and the normalized comparison altogether. The event clock of Note 11 reparametrizes maturity within each slice but preserves the *ordering* of expiries (the dilated clock is monotone), so nothing below is affected; the production expiry chain is keyed by settlement instant, not calendar date.

> **Invariants protected in this note.**
> 1. Where data lives, the fitted surface is increasing in convex order: no calendar spread against it.
> 2. Enforcement is *soft* — quotes still win a genuine conflict, and the diagnostics report what slack was used.
> 3. Calendar coupling off, or a clean ladder, is byte-identical to independent fits (under the symmetric solver this is a verified fast path, not an aspiration).
> 4. The order is inspected only where *both* slices are pinned by data, and inspected in *price* space at fixed strike — the confinement principle (Note 09), sharpened here by a measured rejection of the quantile coordinate ("Where the order may be inspected").

**Conventions and the notation ledger.** $T_1<T_2$ (or $i,j$) index expiries; $t$ is not used. Subscripted $\partial$ for derivatives; no primes. A variance bp is $10^{-4}$ of total variance; a vol bp is $10^{-4}$ of absolute volatility.

| Symbol | Meaning |
|---|---|
| $Y_T=S_T/F_T,\ k$ | normalized terminal; log-moneyness |
| $C_T(k)=\mathbb{E}[(Y_T-e^{k})^{+}]$ | normalized call |
| $\le_{\mathrm{cx}}$ | increasing convex order |
| $G_T(\alpha)=\int_\alpha^1 Q_T(u)\,\mathrm{d}u$ | integrated upper quantile |
| $Q_T,\ \Lambda,\ z,\ \alpha$ | quantile fn; logistic; logit; level |
| $w_T(k)$ | total implied variance |
| $A(z)$ | LQD asset share ($=G$, Proposition 1) |
| $W_{\mathrm{cal}}$ | hinge weight |

*Table 1 — Every symbol in the note. $G$ is always the integrated quantile curve (Durrleman's $g$ never appears here); $\alpha$ is always a quantile level.*

## 2. The existence theorem

**Theorem 1 (Four faces of calendar order).** *Let $\{Y_T\}$ have unit mean, and for $T_1<T_2$ consider:* — the note's central equation —

**Central equation.**

$$
\begin{aligned}
C_{T_1}(k)\le C_{T_2}(k)\ \forall k
\;&\Longleftrightarrow\;
Y_{T_1}\le_{\mathrm{cx}} Y_{T_2}\\
\Longleftrightarrow\;
G_{T_1}(\alpha)\le G_{T_2}(\alpha)\ \forall\alpha
\;&\Longleftrightarrow\;
w_{T_1}(k)\le w_{T_2}(k)\ \forall k .
\end{aligned}
\tag{1}
$$

*All four are equivalent, with $G_{T_1}(0)=G_{T_2}(0)=1$ pinning the means.*

*Proof sketch.* (i)$\Leftrightarrow$(ii): call payoffs $(y-e^{k})^{+}$ span the convex functions of $y$ — every convex $\phi$ with matching means integrates against $\partial_{KK}$ of the call in strike, the Breeden–Litzenberger pairing — so ordering all calls at equal means is exactly convex order [Strassen1965, CarrMadan2005]; Exercise 1 walks the spanning direction. (ii)$\Leftrightarrow$(iii): the Hardy–Littlewood characterization — $\mathbb{E}\phi(Y_1)\le\mathbb{E}\phi(Y_2)$ for all convex $\phi$ iff the integrated quantile curves are ordered; $G$ is the upper-tail version. (i)$\Leftrightarrow$(iv): the normalized Black price is strictly increasing in total variance at fixed $k$, so ordering prices at every $k$ is ordering the implied $w$ at every $k$ [GatheralJacquier2014]. ∎

**Theorem 2 (Kellerer: the promise made precise).** *If each slice is butterfly-free (a valid density) and the family is increasing in convex order — a* peacock *[HPRY2011] — then there exists a martingale $\{M_T\}$ with $\mathrm{law}(M_T)=\mathrm{law}(Y_T)$ for every $T$ [Kellerer1972].*

This is why the note's title is not a metaphor. Butterfly-freedom per slice plus calendar order across slices is not merely "no static arbitrage": it is exactly the statement that the surface is consistent with *some* arbitrage-free dynamic model. The fitter checks a static, per-pair, per-strike inequality; the theorem converts the check into an existential guarantee about dynamics. Everything the rest of the note does — choosing the inspection coordinate, confining the inspection region, deciding who concedes when slices conflict — is engineering in service of equation (1); the mathematics is settled by the two theorems above.

> **Heuristic.** Convex order with equal means says the longer law is a *mean-preserving spread* of the shorter: same forward, more dispersion — exactly what a diffusion does as variance accumulates. Enforcing it between independently fitted expiries is what stops two individually good slice fits from implying a negative forward variance between them: at the money, face (iv) reads $w_{T_2}(0)-w_{T_1}(0)\ge0$, and that difference *is* the forward variance a calendar position buys (Exercise 2).

Figure 2 draws all four faces for one ordered production pair. The four panels are one fact in four coordinate systems, and the reason to keep all four alive is practical: each model of this series happens to hold exactly one of them at zero cost.

> **Figure 2 — One ordered pair, inspected in all four coordinates (figure not included in this pack).** One ordered pair, inspected in all four coordinates of equation (1) (production LQD fits). A: the calendar spread $C_{T_2}-C_{T_1}$ is non-negative at every strike (min $4.8\times10^{-4}$) — face (i). B: the far density is a mean-preserving spread of the near one — face (ii). C: the integrated-quantile gap $G_{T_2}-G_{T_1}$ is a non-negative dome, pinched to zero at both ends by the equal means — face (iii). D: total variance dominates pointwise — face (iv). Four inspections, one order. *Description:* Four panels over one ordered pair of production LQD slices. Panel A plots the normalized-call calendar spread across strike, everywhere non-negative with minimum $4.8\times10^{-4}$. Panel B overlays the two terminal densities: the far density is wider and lower-peaked than the near one at the same mean — a mean-preserving spread. Panel C plots the gap of integrated upper-quantile curves as a function of the quantile level, a non-negative dome pinched to zero at $\alpha=0$ and $\alpha=1$ because the means agree. Panel D shows the two total-variance curves with the far slice dominating pointwise. The same ordering fact appears once per coordinate system.

**Exercise 1.** Prove the spanning direction of (i)$\Rightarrow$(ii) for twice continuously differentiable $\phi$: write

$$
\phi(y)=\phi(1)+\partial_y\phi(1)(y-1)
+\int_0^{1}\partial_{KK}\phi(K)(K-y)^{+}\,\mathrm{d}K
+\int_1^{\infty}\partial_{KK}\phi(K)(y-K)^{+}\,\mathrm{d}K
$$

(the same decomposition as Note 08's spanning proposition), take expectations under both laws, and use equal means plus put–call parity to reduce every term to ordered calls.

**Exercise 2.** The worked pair of "Who pays: the symmetric repair" has ATM total variances $w_{T_1}(0)>w_{T_2}(0)$ before repair (an event-inverted term structure). Compute the implied forward variance $\big(w_{T_2}(0)-w_{T_1}(0)\big)/(T_2-T_1)$ from the free fits of Figure 5B and confirm it is negative — the forward volatility is imaginary, and a calendar position bought at these marks locks in variance at a negative price. The violation number 0.0058 (in total variance) is the same statement made uniform across strikes.

## 3. Four faces, one cheap check per model

The equivalence (1) would be idle if every check cost a grid of Black inversions. The design observation — the same one Note 08 made for the var-swap — is that each model already owns one face.

### 3.1 LQD: the curve is already on the grid

**Proposition 1 (The asset share is the integrated quantile curve).** *For an LQD slice with quantile $Q(z)$ in the logit coordinate (Note 01),*

$$
G(\alpha)=\int_\alpha^1 e^{Q(u)}\,\mathrm{d}u
=\int_{z_\alpha}^{\infty}e^{Q(z)}\,\Lambda(z)\big(1-\Lambda(z)\big)\,\mathrm{d}z
=A(z_\alpha).
$$

*Proof.* Substitute $u=\Lambda(z)$, $\mathrm{d}u=\Lambda(1-\Lambda)\,\mathrm{d}z$ and compare with Note 01's asset-share integral — the same object. ∎

So face (iii) needs no new computation: every built slice carries $A(z)$ on the shared quadrature grid, and the full-surface calendar diagnostic is an elementwise comparison of two arrays, with constraint points automatically dense in the wings (the grid is uniform in $z$, not $k$). As a *fit-time* constraint the same face *used to* enter as a soft squared hinge on a strided subgrid (≈320 of the 8001 nodes),

$$
\sqrt{W_{\mathrm{cal}}}\,
\max\!\big(A_{T_1}(z_m)-A_{T_2}(z_m),\,0\big),
\qquad W_{\mathrm{cal}}=10^{6},
\tag{2}
$$

keyed on the constraint $z$-*coordinates*, so a slice calibrated on a coarser optimization grid enforces it by Hermite evaluation, bit-for-bit equivalent to the node-indexed form on the native grid. Hold equation (2) in mind as the *historical* enforcement form — it is the one "Where the order may be inspected" convicts. Production has abandoned this face for enforcement entirely and keeps it as the free, wing-dense *diagnostic* it is perfectly suited to be; the quantile form survives only as a legacy threading option.

### 3.2 SVI and MCS: face (iv) against the displayed neighbour

The parametric overlays carry no quantile curve, so they hinge total variance directly,

$$
\sqrt{W_{\mathrm{cal}}}\,
\max\!\big(w_{\mathrm{near}}(k_m)-w_{\mathrm{far}}(k_m),\,0\big),
\tag{3}
$$

on a data-confined log-moneyness grid, reading only the previous *displayed* slice's implied variance — whatever model drew it (and symmetrically against the next slice as a ceiling, so an overlay refit cannot break the pair from above). The production plumbing is the part that took care: the floor needs the previous displayed slice, so the calendar toggle threads it in ascending maturity through *every* path that fits a slice — the single-slice overlay, the commit path, the full-surface loop and the coupled workflow (this is the sequential solver's route; under the shipped symmetric default the surface's interfaces carry the confined price rows of "The coordinate matters: why the floor lives in price space"). Wherever the floor is absent (toggle off, or the first expiry) the residual block is absent too: byte-identical, test-locked per model and per path.

### 3.3 Local volatility: the promise by construction

The LV surface needs neither hinge. A positive local variance makes the Dupire march's continuum prices increasing in maturity at fixed strike — face (iv) holds along the whole solve — so calendar-cleanliness is structural (Note 04); production carries only a discrete diagnostic (worst adjacent-expiry price decrease, tolerance $10^{-8}$) to confirm the scheme respects what the continuum promises. This mirrors Note 09's wing taxonomy: LQD structural in one dimension is LV structural in the other — a model built *from* a valid generator inherits the promise its coordinates encode.

## 4. Where the order may be inspected

Both hinges above compare *two* curves, and Note 09's confinement principle applies with full force: a two-curve constraint may be sampled only where data pins both. This section is the calendar's own case file — the incident that founded the principle — plus this edition's sharpening: confinement is not only about *where* but about *in which coordinate*.

> **Example — Case file: the phantom calendar violation.**
>
> **Setup.** A steep short-dated slice over a flatter long-dated one — an ordinary single-name skew. On the data, the far slice sits *above* the near one everywhere: genuinely calendar-consistent.
>
> **Failure mode.** Live SVI overlays on NVDA (Sep-26) and SPY (Jun-27) fitted *flat*, with huge RMS, whenever the calendar toggle was on.
>
> **Diagnosis.** The floor of equation (3) was sampled on a fixed wide grid $k\in[-1,1]$. With linear wings, the steep near slice extrapolates to far higher variance at the grid edges than the flat far slice — $w_{\mathrm{near}}>w_{\mathrm{far}}$ out where neither expiry has a single quote. A *phantom* violation, manufactured entirely by two extrapolation laws disagreeing in a no-data region; the hinge then flattened the far fit to cure a problem the data never posed (Figure 3A).
>
> **Fix.** Confinement: the floor grid is built on the traded span only (41 points; the wide 161-point grid survives only as the empty-quotes fallback), and in current production on the *intersection* of the two slices' spans.
>
> **Verdict (reproduced with the production calibrator, Figure 3).** Under the wide grid the far fit misses its own quotes by 151 vol bp; under the confined grid by 0.0 — indistinguishable from the unconstrained fit. Test-locked, including the assertion that the scenario is consistent on data and inconsistent only in extrapolation, and registered in the named certification pack as `calendar_phantom` — the founding incident keeps its own lock.

> **Figure 3 — The phantom calendar, reproduced (figure not included in this pack).** The phantom calendar, reproduced with the production calibrator. A: on the traded range (shaded) the far slice dominates — no true violation — but the steep near wing extrapolates above the flat far wing exactly where the wide floor grid (upper ticks) samples; the confined grid (lower ticks) never looks there. B: fitted under the wide-grid floor the far smile flattens away from its own quotes (151 vol bp); confined, it is indistinguishable from the unconstrained fit (0.0 vol bp). *Description:* Panel A shows the steep near slice and the flatter far slice in total variance over $k\in[-1,1]$, with the traded range shaded: inside the shading the far curve dominates cleanly, while beyond it the near slice's steep linear wings climb above the far slice's — exactly where the wide floor grid's tick marks sample and the confined grid's tick marks do not. Panel B compares the far slice's fit under the two floors: under the wide grid the hinge flattens the far smile 151 vol bp away from its own quotes; under the confined grid the fit sits on its quotes, 0.0 vol bp from the unconstrained answer.

> **Algorithm — the confined calendar floor grid.** (Replaces the reference listing; verified against production output to $1.0\times10^{-17}$ on quoted and empty inputs alike, see "Reference implementation".)
>
> *Inputs:* the array of quoted log-moneyness values for the slice pair's traded span; the grid size $n=41$. *Output:* the floor sampling grid.
>
> 1. If the quote array is empty — no data at all — return the wide fallback grid: 161 uniformly spaced points on $[-1,1]$ (the historical wide grid, retained for this degenerate case only).
> 2. Otherwise return $n=41$ uniformly spaced points spanning $[\min_i k_i,\ \max_i k_i]$: the floor is sampled on the traded span only, never in the extrapolated region.

### 4.1 The coordinate matters: why the floor lives in price space

Confinement has a subtlety the original incident did not expose: for the LQD face-(iii) constraint, *windowing is not confining*. The reason is a two-line locality computation. Perturb the near slice's quantile by $\delta Q$ supported on deep-tail levels $u>\alpha_0$ (strikes far beyond any quote). Then

$$
\delta G(\alpha)=\int_{\max(\alpha,\alpha_0)}^{1}
e^{Q(u)}\,\delta Q(u)\,\mathrm{d}u
\ \ne0\quad\text{for every }\alpha\le\alpha_0 :
$$

$G$ integrates the whole upper tail, so a disagreement between two extrapolated tails contaminates the comparison at every level below it — including levels whose strikes sit squarely inside the quoted range. A windowed $G$-floor still reads tail fiction. The normalized call at fixed strike has no such reach: $\delta C(k)$ responds only to density moved across the strike $e^{k}$, so a price-space comparison at quoted strikes is genuinely local to them.

Figure 4 measures exactly this, on the acute scenario of the shipped confinement lock: a two-day event straddle quoted on a $\pm6\%$ span under an ordinary three-month slice — comfortably ordered on their common support, wildly disagreeing in extrapolation. Fit the far slice free: 10.6 vol bp of quote error. Add the full-grid $G$-floor: 1095 bp — the phantom drag. *Window* the $G$-floor to the common support: still 228 bp, an order of magnitude above clean — the tail contamination just derived. Replace it with the production floor — normalized-call ordering $C_{T_2}(k)\ge C_{T_1}(k)$ on the common support, $\cos^{2}$-tapered at its edges — and the fit returns to 10.6 bp, indistinguishable from no floor. The confined calendar floor lives in price space because price space is the coordinate in which "where" means anything.

> **Figure 4 — Windowing is not confining (figure not included in this pack).** Windowing is not confining (production fits; the shipped confinement-lock scenario). A: an acute two-day slice (rust) quoted only on the shaded common support, under an ordinary three-month slice (teal): ordered where both are quoted, disagreeing violently in extrapolation. B: the far fit's worst quote error under four floors. The full-grid $G$-floor drags it 1095 vol bp off its own quotes; *windowing* the $G$-floor still leaves 228 bp, because $G(\alpha)$ integrates the entire upper tail ("The coordinate matters: why the floor lives in price space"); the confined price-space floor is indistinguishable from no floor at 10.6 bp. *Description:* Panel A draws the acute scenario: a two-day event straddle slice (rust) quoted only on a narrow $\pm6\%$ shaded span, sitting under an ordinary three-month slice (teal); on the common support the pair is ordered, while their extrapolated tails diverge violently. Panel B is a bar chart of the far fit's worst quote error under four floor configurations: no floor 10.6 vol bp, full-grid $G$-floor 1095 bp, windowed $G$-floor 228 bp, and the production confined price-space floor 10.6 bp. The windowed bar is the panel's lesson — an order of magnitude above clean even though the constraint was only sampled on the common support, because the $G$ coordinate integrates the whole upper tail.

**Exercise 3.** The taper margin is $\mathrm{clamp}(0.15\,|W|,\,0.05,\,0.25)$ in log-moneyness, $|W|$ the common-support width. For the live surface of Figure 1, the two shortest expiries share a traded span of about $[-0.04,0.02]$. Compute the margin, observe that it is nearly as wide as the window itself, and explain why that is the *intended* behaviour for 0DTE pairs: with almost no jointly-quoted territory, the comparison should fade to advisory rather than assert itself on six strikes.

## 5. Who pays: the symmetric repair

Everything so far decided *what* to check and *where*. One question remains, and it is the note's second original contribution: when two slices' quotes genuinely conflict — an event-inverted term structure, a stale board — *someone* must concede. Who?

The historical sequential pass had an implicit answer: expiries are fitted nearest-to-farthest, each under a floor built from the already-committed previous slice, so the *latecomer* pays — whatever the merits. On the worked pair of Figure 5 (a high-vol $T_1=0.25$ over a calmer $T_2=0.50$, free-fit violation 0.0058 in total variance) the sequential answer is stark: the near slice keeps its quotes to 4.8 vol bp while the far slice is bulldozed 547 bp above its own board. Nothing about the data justifies that asymmetry — the near quotes are exactly as implicated in the inconsistency as the far ones.

The shipped symmetric solver (the production default) replaces the convention with a declared objective. Its design is five steps: *fit independently* (every expiry, warm-seeded, no coupling); *screen* each adjacent interface with a vega-normalized call-ordering violation ($0.5$ vol bp tolerance) on the tapered common-support grid of "The coordinate matters: why the floor lives in price space"; *group* violations into connected components; *jointly refit* each violating component — and only it — by Gauss–Newton on the stacked per-slice residuals plus tapered interface hinge rows, escalating the interface weight ($\times10$, at most three times) if a violation survives; and *fast-path* everything else: a clean ladder's fits are returned untouched, byte-for-byte — invariant 3 as an implementation fact, verified live on SPY (a monotone-PAVA pre-pass was considered and deliberately dropped: the component joint solve *is* the global reconciliation, and a second mechanism would fight it).

> **Figure 5 — Who pays, measured (figure not included in this pack).** Who pays, measured (production solvers, identical quotes; an event-inverted pair with free-fit violation 0.0058). A: the sequential pass bulldozes the latecomer — near untouched at 4.8 vol bp, far conceding 547 — while the symmetric solver shares the concession (414/254 bp) and lowers the worst-case slice error. B: the symmetric repair in variance space: the free fits cross (shaded); the repaired pair meets on a common curve through the conflicted region — the surface is pushed exactly to the boundary of admissibility, zero forward variance, and no further — curing the order to $3.2\times10^{-6}$. *Description:* Panel A compares per-slice quote errors under the two solvers on identical event-inverted quotes: sequential leaves the near slice at 4.8 vol bp and pushes the far slice 547 bp off its board, while symmetric splits the concession 414/254 bp, lowering the worst-case error by roughly a factor of two. Panel B shows the mechanics in total-variance space: the two free fits cross in a shaded conflicted strike region; after the joint repair the near and far curves coincide exactly through that region — the boundary of the admissible set, zero forward variance — and separate again outside it, with the residual order violation cured to $3.2\times10^{-6}$ in total variance.

Panel B shows what "sharing" converges to: through the conflicted strikes the repaired near and far slices coincide. That is not a solver artefact but the geometry of the constraint set — the closest admissible surface to an inverted pair sits on the boundary $w_{T_1}=w_{T_2}$, i.e. exactly zero forward variance, and the joint least-squares splits the distance to it according to the quote weights rather than the accident of fitting order. Under the extrapolated-region toggle the same joint solve also carries a *tail contract* per interface — two seam price rows just beyond the span union and two wing-slope-order rows (scalar conditions on the endpoint tails, never pointwise differences of extrapolations: the phantom lesson, kept by construction).

## 6. The extrapolated region: measure, lean, repair

Confinement enforces *nothing* outside the traded span, and the region just past the last quote is not worthless — options there still carry premium, and a calendar inversion between two *stated* wing contracts (Note 09) is a real inconsistency even if no quote witnesses it. What that region deserves remains an explicitly flagged open problem (2026-07) on *doctrine*; the *machinery* has shipped in three graduated phases, certification-locked together as case `extrap_wing_contracts`. *Measure* (always on): the quality report computes, over the *time-value envelope* — strikes beyond the traded span where the model's own OTM value still exceeds a basis point of forward — the worst Durrleman $g$, the worst calendar crossing against the previous displayed slice, and the wing-slope order; all advisory, never gating readiness. *Lean* (opt-in, off by default): the overlay fits gain three residual blocks over the same envelope — a one-curve butterfly hinge, a tapered calendar hinge, and the scalar wing-slope-order condition — each budgeted in vol units at a quarter of an average quote's weight, so the block leans like a handful of extra quotes and can never outvote the board; on a clean pair it is a no-op to fit precision, and a genuine mild crossing (≈450 bp) is halved for ≈29 bp of traded-range RMS. *Repair at the boundary* (export only): published curve samples are lifted, wing by wing outward from the pinned traded edge, onto the discrete arbitrage-free cone in OTM-price space — non-increasing, convex, at or above the previous *published* expiry — expiries in ascending maturity; the repair only ever raises wing prices, a clean wing exports byte-identically, fits and in-app views are untouched, and a floor exceeding the pinned traded edge (a *core* calendar conflict, the fit's business, not the exporter's) is capped and flagged rather than silently repaired. The export manifest audits the repair via `projectionCalendarWorstBp` — the field that licenses a price-moving repair at the boundary at all. A repair moves prices, so its *authority* is confined to the wings even though the constraints it restores extend there — Note 09's refinement, applied.

## 7. What is genuinely original here

The convex-order theory is classical; the contributions are three pieces of engineering shaped by it.

1. *One face per model*: recognizing that the LQD asset share *is* the integrated-quantile curve (Proposition 1) makes the surface diagnostic a free array comparison; the overlays get face (iv) against whatever the previous display drew; LV needs nothing. The same order, checked in each model's own coordinate — at essentially zero cost everywhere.
2. *The coordinate half of confinement* ("The coordinate matters: why the floor lives in price space"): the measured demonstration that windowing the quantile-space floor does not confine it (228 vs 10.6 vol bp), with the two-line locality computation that explains why — and the shipped price-space, cos²-tapered, intersection-support floor it justified.
3. *A declared answer to "who pays"* ("Who pays: the symmetric repair"): the symmetric screen-and-repair solver — independent fits, local violation components, one joint Gauss–Newton — replacing the sequential pass's blame-the-latecomer convention with the least-squares split, while keeping clean ladders byte-identical to independent fits through a verified fast path.

## 8. Limitations

Where the guarantees stop. *The hinge is soft by design*: at weight $10^{6}$ quotes win a genuine conflict only through the joint solve's sharing rule, and a sub-tolerance crossing (under the $0.5$ vol bp screen) is deliberately left standing — the promise is kept to tolerance, not to machine precision. *The sharing rule is statistical, not economic*: the symmetric split follows quote weights, not any view about which board is stale; a desk that *knows* the near board is bad should exclude quotes, not expect the solver to adjudicate. *Kellerer is an existence theorem only*: the martingale is not unique, not constructed, and nothing here selects dynamics — pricing path-dependent claims still requires a model (Note 04, Note 12). *The assumption box is load-bearing*: stochastic rates break the equivalence between calendar spreads and the normalized comparison; discrete cash dividends already break the cash-strike form. *LV's structural cleanliness is a continuum statement* policed by a discrete diagnostic, not a proof about the scheme. And *the extrapolated region remains an open doctrine question* ("The extrapolated region: measure, lean, repair"): measured always, leaned on only opt-in, repaired only at the published boundary — the machinery itself is shipped and certification-locked.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

**Surfaced**

| Knob | Default | Role |
|---|---|---|
| `enforceCalendar` | `true` | Master toggle for calendar coupling (all calibration paths). |
| `surfaceSolver` | `symmetric` | `symmetric` (screen + joint component repair, "Who pays: the symmetric repair") or `sequential` (nearest-to-farthest with prev-display floors). |
| `calendarWeight` $W_{\mathrm{cal}}$ | $10^{6}$ | Soft-hinge strength. *Not* the graph edge-trust `calendarWeight` of Note 14, which shares the name. |
| `extrapEnforce` | `false` | Phase-2 tapered extrapolated-region hinges; under the symmetric solver also arms the per-interface tail contract ("Who pays: the symmetric repair"). |

**Hidden**

| Knob | Default | Role |
|---|---|---|
| `CAL_STRIDE` | 25 | LQD full-grid constraint subgrid stride (≈320 points on the 8001-node grid). |
| `CAL_PRICE_N` | 49 | Nodes of the confined price-space floor. |
| `TAPER_FRAC/MIN/MAX` | 0.15/0.05/0.25 | cos² taper margin as a clamped fraction of the common-support width (Exercise 3). |
| `SCREEN_TOL_VOL` | $5\times10^{-5}$ | Symmetric screen tolerance ($0.5$ vol bp, vega-normalized). |
| `IFACE_N` | 33 | Interface hinge nodes per adjacent pair. |
| `ESCALATION_FACTOR` / max | 10 / 3 | Interface-weight escalation when a violation survives a joint pass. |
| `SEAM_PAD` | 0.10 | Tail-contract seam offset beyond the span union. |
| `VAR_FLOOR_N_DATA` | 41 | Confined overlay floor-grid resolution (the confined-grid algorithm of "Where the order may be inspected"); wide fallback 161 points on $[-1,1]$, empty-quotes only. |

*Table 2 — Calendar-arbitrage hyperparameters.*

## Appendix B. Performance notes

1. The LQD full-grid diagnostic is an array subtraction on the already-built asset share — free; its fit-time Jacobian rows are $-\partial A/\partial\theta$ on active constraints, supplied by Note 01's analytic Jacobian.
2. The overlay floor is 41 evaluations of the previous slice's $w(k)$; the confined price floor is 49 call evaluations with taper weights. Confinement *reduces* work by never sampling the extrapolation region.
3. The symmetric solver's screen is a handful of vega-normalized call comparisons per interface; the joint Gauss–Newton runs only over violation-connected components (block-bidiagonal stacked Jacobian, analytic, locked against finite differences), so a clean ladder costs exactly its independent fits plus the screen — and returns them byte-for-byte (the fast path; live SPY validation measured $|\mathrm{sym}-\mathrm{seq}|=0.0$ bp on a clean ladder).
4. All fresh numbers in this edition are produced by the generator running production calibrators; the live NVDA/SPY incident and the Phase-2 lean/cost trade (≈450 bp halved at ≈29 bp) are historical, quoted from the test-locked scenarios that reproduce them.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

| Claim | Object | Code anchor · *Test anchor* |
|---|---|---|
| LQD integrated-quantile constraint; surface repair | Proposition 1, equation (2) | `volfit/calib/calendar.py`, `volfit/models/lqd/calibrate.py` · *`tests/test_surface.py::test_violating_quotes_get_repaired_when_enforced`* |
| Overlay floor reads the previous slice's $w$; crushes real violations (SVI, MCS) | equation (3) | `volfit/calib/calendar.py` · *`tests/test_overlay_calendar.py::test_variance_floor_reads_prev_total_variance`; `::test_svi_floor_crushes_calendar_violation`; `::test_sigmoid_floor_crushes_calendar_violation`* |
| Byte-identical with no floor / toggle off | invariant 3 | `volfit/models/svi_jw/calibrate.py`, `volfit/models/sigmoid/calibrate.py` · *`tests/test_overlay_calendar.py::test_svi_no_floor_is_byte_identical`; `::test_build_display_fit_no_floor_byte_identical`* |
| Phantom scenario: consistent on data, phantom in wings; confined grid fits clean, wide grid flattens | Figure 3 | `volfit/calib/calendar.py` · *`tests/test_overlay_calendar.py::test_far_above_near_inside_data_but_not_in_wings`; `::test_wide_grid_breaks_svi_but_data_grid_does_not`; certification case `calendar_phantom`* |
| Price-space confinement kills the drag; support/taper geometry | Figure 4 | `volfit/calib/calendar.py` · *`tests/test_calendar_confinement.py::test_confined_floor_kills_the_phantom_calendar_drag`; `::test_common_support_intersection_and_disjoint`; `::test_support_taper_shape`; `::test_confined_floor_is_the_near_call_curve_on_common_support`* |
| Symmetric solver: fast path; local components; symmetric split; analytic stacked Jacobian; tail contract | "Who pays: the symmetric repair" | `volfit/calib/symmetric.py`, `symmetric_stack.py` · *`tests/test_symmetric_surface.py::test_clean_ladder_is_exactly_the_independent_fits`; `::test_repair_is_local_to_the_violation_component`; `::test_real_violation_is_shared_symmetrically`; `::test_stacked_jacobian_matches_finite_differences`; `::test_tail_contract_orders_the_extrapolated_wings`; `::test_acute_phantom_ladder_does_not_trigger_the_solver`* |
| prev_display threaded ascending-$T$ everywhere (sequential path) | "Four faces, one cheap check per model" | `volfit/api/service.py`, `volfit/api/workflow.py` · *`tests/test_calibration_workflow.py::test_enforce_calendar_threads_prev_into_parametric_items`; `::test_enforce_calendar_threads_prev_overlay_for_non_lqd`* |
| Coupled surface arbitrage-free; certification | Theorem 1 | `volfit/api/workflow.py`, `backend/backtest/certification.py` · *`tests/test_calibration_workflow.py::test_enforce_calendar_surface_is_arbitrage_free`; certification case `symmetric_calendar`* |

*Table 3 — Claims in this note and the code/tests that lock them.*

## Appendix D. Reference implementation

The enforcement residuals are one line each; the confined grid is the algorithm of "Where the order may be inspected", verified against production output to $1.0\times10^{-17}$ on quoted and empty inputs alike. The hinge specifications below reproduce the residual blocks inside the calibrators exactly (the production rows are inline in each calibrator — deliberately, since each model evaluates its own face of equation (1)):

> **Algorithm — the calendar hinges as they appear (inline) in the calibrators.** (Replaces the reference listing; face (iv) for the overlays, face (iii) on the LQD grid, face (i) with taper for the confined price floor and the symmetric interfaces. The pack carries no source code.)
>
> *Inputs per residual row:* the calendar weight $W_{\mathrm{cal}}$; the floor value at the row's sample point (previous slice's total variance $w$, asset share $A$, or normalized call price $C$, per face); the current slice's corresponding value; for face (i), the cos² taper weight $t_m\in[0,1]$ at the sample point. *Output:* one non-negative residual row per sample point, appended to the calibrator's least-squares stack.
>
> 1. **SVI / MCS, face (iv).** At each node $k_m$ of the confined floor grid, the residual is $\sqrt{W_{\mathrm{cal}}}\cdot\max\big(w_{\mathrm{floor}}(k_m)-w_{\mathrm{model}}(k_m),\,0\big)$ — rows are exactly zero unless the fitted (far) slice dips below the previous displayed slice's total variance.
> 2. **LQD full grid, face (iii).** At each constraint coordinate $z_m$ of the strided subgrid, the same hinge on the asset share: $\sqrt{W_{\mathrm{cal}}}\cdot\max\big(A_{\mathrm{floor}}(z_m)-A_{\mathrm{slice}}(z_m),\,0\big)$, where the slice's asset share is evaluated at the constraint $z$-coordinates (by Hermite evaluation when the optimization grid is coarser, bit-for-bit equivalent to node indexing on the native grid).
> 3. **Confined price floor / symmetric interface, face (i), cos²-tapered.** At each node $k_m$ of the common-support price grid, $\sqrt{W_{\mathrm{cal}}}\cdot t_m\cdot\max\big(C_{\mathrm{floor}}(k_m)-C_{\mathrm{slice}}(k_m),\,0\big)$, with $t_m$ the cos² taper weight fading the constraint to zero at the support's edges over the clamped margin of Exercise 3.

## References

- [Strassen1965] V. Strassen. The existence of probability measures with given marginals. *Ann. Math. Statist.*, 36(2):423–439, 1965.
- [Kellerer1972] H. Kellerer. Markov-Komposition und eine Anwendung auf Martingale. *Math. Ann.*, 198:99–122, 1972.
- [HPRY2011] F. Hirsch, C. Profeta, B. Roynette and M. Yor. *Peacocks and Associated Martingales*. Springer, 2011.
- [CarrMadan2005] P. Carr and D. Madan. A note on sufficient conditions for no arbitrage. *Finance Research Letters*, 2(3):125–130, 2005.
- [GatheralJacquier2014] J. Gatheral and A. Jacquier. Arbitrage-free SVI volatility surfaces. *Quantitative Finance*, 14(1):59–71, 2014.


