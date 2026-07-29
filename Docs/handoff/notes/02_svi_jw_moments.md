# The Wings and the Belly

**Note 02 — SVI as a moment-controlled smile: Lee's bound, the tails it certifies, and the interior it does not · lecture edition ("the wings and the belly") · converted from 02_svi_jw_moments.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** A volatility smile answers two questions at once. Its *wings* report the tails of the risk-neutral distribution — how much mass sits far out of the money — and Lee's moment formula caps how fast they may grow. Its *belly*, the curvature near the money, reports the shape of the centre. This note reads raw SVI through that division. SVI draws one expiry's total implied variance as a tilted hyperbola: strictly convex, linear in both wings, and unable to turn twice. We show that its two asymptotic wing slopes $\beta_L=b(1-\rho)$ and $\beta_R=b(1+\rho)$ are exactly the object Lee's bound constrains, and that the bound lands inside Durrleman's density factor as the elementary tail limit $g(\pm\infty)=(4-\beta^2)/16$: the wing slope sets the *sign* of the implied density in the tail, and staying *strictly* under Lee's $2$ is precisely the condition that the tail density come out eventually positive — the boundary $\beta=2$ itself is a trap (Proposition 2). The cheap guarantees raw SVI can give fence the floor and the wings; the belly needs a certificate. The belly is where it cannot: a Lee-clean, positive, strictly convex slice (Axel Vogt's classical counterexample — minimum variance 0.0116, larger Lee coefficient 0.174, both tails of $g$ at $\approx0.25>0$) still drives $g$ to $-0.033$ in its interior, so its Black density is negative near $k\approx0.88$. The jump-wing (SVI-JW) coordinates are the desk's way of naming this split: two *tail* handles $p,c$ and three *belly* handles $v,\psi,\widetilde v$. We prove the exact regular domain on which the five handles invert to a raw slice, and show that where they fail to identify it — the $\psi=0$ stratum — what they lose is precisely the belly curvature: infinitely many raw widths share the same tails and level. We then fit the slice the way the split suggests: an unconstrained reparametrization that fences the tails (the Lee and minimum rows) while the data term fits the belly, with a closed-form Levenberg–Marquardt Jacobian that recovers a production benchmark through a JW→raw→fit→JW round trip to $5.6\times10^{-13}$ vol bp and runs 2.40× faster than finite differences. Product status up front: production fits and stores *raw* SVI and displays model-agnostic ATM handles; five-handle JW entry, bumping and export are analytical, not shipped.

**Contents**

1. Two questions a smile answers
2. One hyperbola with straight wings
3. Lee's bound is a statement about the wings
4. The belly escapes
5. Trader coordinates that split tail from belly
6. Fitting the slice: fit the belly, fence the tails
7. Worked example: a laboratory round trip
8. One belly, one turn
9. What is genuinely original, and limitations
— Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation: the two maps · References

---

## 1. Two questions a smile answers

Stand at one expiry and look at the implied-volatility smile as a curve over log-moneyness. It is doing two jobs. Far from the money it is reporting the *tails* of the risk-neutral law — the price the market puts on rare moves — and near the money it is reporting the *belly*, the local shape around the forward. These two jobs are governed by different mathematics. The tails obey a hard theorem: Lee's moment formula ties the growth rate of implied variance in the wings to the number of finite moments of the underlying, and caps that growth. The belly obeys no such cheap law; it is where a smile can look perfectly reasonable and still be arbitrageable.

The organizing claim of this note is that raw SVI wears this division on its sleeve, and that every guarantee the Vol-Fitter cheaply enforces on an SVI slice is a *wing* guarantee. Once that is clear, three otherwise separate facts become one story: why the coded no-arbitrage screens are tail conditions, why the classical counterexample that defeats them fails in the *belly*, and why the trader coordinate system (SVI-JW) is built to separate the two. We develop the geometry first, read the tails through Lee's bound, watch the belly escape, and only then change coordinates and fit.

**Conventions and clocks.** Throughout, $k=\log(K/F_T)$ is log-moneyness against the expiry-$T$ forward $F_T$, and

$$
w(k)=\text{(Black implied total variance at }k)
$$

is the object SVI models. The normalized Black price depends only on $k$ and $w$, so $w$ is recovered from a quoted price without first choosing an annualization clock. Vol-Fitter keeps two clocks apart:

$$
I_t(k)=\sqrt{\frac{w(k)}{t}},\qquad
I_\tau(k)=\sqrt{\frac{w(k)}{\tau}}, \tag{1}
$$

where $t=t_T$ is the plain calendar year fraction and $\tau=\tau_T$ is the *active variance time* — calendar time dilated by scheduled events (Notes 00 and 11), equal to $t$ when the event clock is off. Production passes $\tau$ to the calibrator, so unless qualified $I$ means the working quantity $I_\tau$; changing the clock rescales the annualized number, never $w$. A *volatility basis point* (vol bp) is $10^{-4}$ in volatility. We write the SVI width as $s$ so that $\sigma$ is free for volatility, and reserve one differentiation convention: a prime denotes the derivative of a one-variable function ($w'$, $w''$, $I'$), a subscripted or explicit $\partial$ denotes a partial ($\partial w/\partial\rho$).

**Table 1 — Notation ledger. Nothing is reused with a second meaning; the width is $s$, never $\sigma$, and there is one time symbol per clock.**

| Symbol | Meaning | First used |
|---|---|---|
| $k$ | log-moneyness $\log(K/F_T)$ | equation (1) |
| $w(k)$ | total implied variance (price-derived) | equation (2) |
| $t,\ \tau$ | calendar year fraction; active variance time | equation (1) |
| $I(k)$ | working implied volatility $\sqrt{w/\tau}$ | equation (1) |
| $a,b,\rho,m,s$ | raw SVI parameters (width $s$) | equation (2) |
| $\beta_L,\beta_R$ | asymptotic wing slopes $b(1\mp\rho)$ of $w$ | equation (6) |
| $k_\star,\ w_\star$ | minimizing $k$; minimum total variance | equation (5) |
| $g(k)$ | Durrleman density factor | equation (7) |
| $v,\psi,p,c,\widetilde v$ | JW handles: level, ATM slope, wings, floor | equation (12) |
| $\chi$ | normalized displacement $m/\sqrt{m^2+s^2}$ | equation (16) |
| $D$ | inverse denominator (an angle gap) | equation (17) |
| $\theta$ | unconstrained calibration vector in $\mathbb{R}^5$ | equation (22) |

Raw SVI (Gatheral) postulates that the entire slice is one hyperbola.

**Central equation.**

$$
w(k)=a+b\Big\{\rho(k-m)+\sqrt{(k-m)^2+s^2}\Big\}. \tag{2}
$$

Five parameters, and — as we are about to see — exactly two of them, bundled as $\beta_L,\beta_R$, are what Lee's bound touches. The rest describe the belly.

> **Invariants protected in this note.**
> 1. Every finite $\theta\in\mathbb{R}^5$ maps to a smooth raw hyperbola with $b>0$, $|\rho|<1$, $s>0$ (section "Fitting the slice: fit the belly, fence the tails"); and under the default structural chart the floor and the cap hold by construction too — only butterfly-freedom still needs the certificate.
> 2. The two coded screens are cheap global fences: the vertex floor $\widetilde v\ge0$ (a belly condition) and the *strictly buffered* wing cap $\max(\beta_L,\beta_R)\le\beta_{\max}=1.95<2$ (the boundary $\beta=2$ itself admits negative tail density, Proposition 2). Both are finite-weight soft rows, exactly zero on a clean slice — structurally inert, not merely vanishing, under the default chart — and they bound but do not certify non-negativity of the Black density in the belly.
> 3. The raw ↔ JW change of coordinates is exact on the regular domain of Theorem 1; the singular stratum it omits is a loss of *belly* information (Remark 1).
> 4. SVI is one display overlay among several: band, calendar, var-swap, prior and extrapolation blocks share the series' product targets through model-specific residuals, and each is byte-identical to its own absence.

## 2. One hyperbola with straight wings

Everything below rests on three closed-form facts about equation (2). Write

$$
x=k-m,\qquad r=\sqrt{x^2+s^2},\qquad q=\sqrt{1-\rho^2}. \tag{3}
$$

**Proposition 1 (Geometry of one slice).** Under $b>0$, $|\rho|<1$, $s>0$, the slice $w$ is strictly convex with a single minimum:

$$
w'(k)=b\Big(\rho+\frac{x}{r}\Big),\qquad
w''(k)=\frac{b\,s^2}{r^3}>0, \tag{4}
$$

$$
k_\star=m-\frac{s\rho}{q},\qquad w_\star=a+b\,s\,q. \tag{5}
$$

Its far field is two straight rays,

$$
w(k)=\beta_L\,|k|+O(1)\ (k\to-\infty),\quad
w(k)=\beta_R\,k+O(1)\ (k\to+\infty),\quad
\beta_L=b(1-\rho),\ \beta_R=b(1+\rho). \tag{6}
$$

*Proof.* Differentiating equation (2) gives equation (4); since $b,s>0$, $w''>0$ for every finite $k$, so a stationary point is the unique global minimum. Solving $w'=0$ gives $x=-s\rho/q$, hence $r=s/q$ and equation (5). In either wing $r=|x|+o(1)$, which yields equation (6). ∎

Two consequences are worth stating plainly, because they drive the rest of the note. First, $w''>0$ *everywhere*: raw SVI is one globally convex curve with one belly and one turn of the slope, from $-\beta_L$ up to $+\beta_R$ (Figure 1A). This is the model's rigidity, and the section "One belly, one turn" returns to it. Second — the point of this section — the tails collapse to *two numbers*. As $|k|$ grows, $w(k)/|k|$ converges to $\beta_L$ on the put side and $\beta_R$ on the call side (Figure 1B); no other feature of the slice survives to infinity. Whatever the market's tails are worth, SVI records them in $\beta_L$ and $\beta_R$ alone.

> **Figure 1 — The wings are a two-number reading of the tails (figure not included in this pack).** Panel A: the total variance approaches two straight asymptotes, steeper on the put side for the equity skew $\rho<0$. Panel B: $w(k)/|k|$ collapses onto the constants $\beta_L$ and $\beta_R$ as $|k|\to\infty$ — each wing reports exactly one slope, and those two slopes are all that Lee's bound of the next section can see. — Panel A draws a put-skewed raw slice ($\rho<0$) in total variance with both asymptotic rays overlaid; the left ray is visibly steeper, and the curve merges into the rays away from the core. Panel B plots the ratio $w(k)/|k|$ against $|k|$ for both wings: two curves flattening onto horizontal levels $\beta_L$ and $\beta_R$. The panel makes graphic that the entire tail content of the model is two scalars.

> **Heuristic.** Read equation (2) as a rounded hinge. Far out, the hinge has forgotten its rounding and shows two straight rays of slope $\beta_L$ (left) and $\beta_R$ (right). Near the centre, $s$ decides how sharply one ray turns into the other, $m$ sets where the rounding sits, and $a$ raises the whole curve. The tilt $\rho$ divides a fixed total steepness $\beta_L+\beta_R=2b$ between the two sides. The wings are tails; the region where $s$ matters is the belly.

## 3. Lee's bound is a statement about the wings

Why should a wing slope be capped at all? Because it is a moment barometer. Lee's moment formula [Lee2004] says that if the underlying has $\bar p$ finite moments beyond the first, the right-wing implied variance grows no faster than $\beta_R\,k$ with a slope controlled by $\bar p$, and symmetrically on the left; in the limiting case of a distribution on the edge of losing all moments, the slope reaches $2$. Heavier tails would demand a steeper wing, and a wing steeper than $2$ is not the tail of *any* probability distribution. For a model whose wings are exactly linear, this is not an asymptotic nicety — it is a sharp, checkable inequality on two of its parameters.

The cleanest way to see the bound bite is to follow it inside the object that actually tests for arbitrage. A positive, $C^2$ total-variance slice with the right wing behaviour is free of butterfly arbitrage iff the Black density it implies is non-negative, and Durrleman [Durrleman2010] writes that density, up to a strictly positive prefactor, as

$$
g(k)=\Big(1-\frac{k\,w'(k)}{2w(k)}\Big)^2
-\frac{w'(k)^2}{4}\Big(\frac{1}{w(k)}+\frac14\Big)+\frac{w''(k)}{2}\ \ge\ 0
\quad\forall k. \tag{7}
$$

The connection to the wings is a one-line limit.

**Proposition 2 (The wing slope sets the sign of the tail density).** For a structurally valid positive raw slice,

$$
\lim_{k\to-\infty}g(k)=\frac{4-\beta_L^2}{16},\qquad
\lim_{k\to+\infty}g(k)=\frac{4-\beta_R^2}{16}. \tag{8}
$$

Hence for $\beta<2$ the tail of $g$ is eventually positive, for $\beta>2$ eventually negative — and *at* $\beta=2$ the limit vanishes and decides nothing: the sign falls to the next order. On a right wing at the boundary, $w(k)=2k+\alpha+O(k^{-1})$ (for raw SVI with $\beta_R=2$, $\alpha=a-2m$),

$$
g(k)=\frac{\alpha-2}{4k}+O(k^{-2}), \tag{9}
$$

so the boundary slice carries *negative* tail density whenever $\alpha<2$ (mirror statement on the left with $\alpha'=a+2m$). The call-price boundary $\lim_{k\to+\infty}d_+(k)=-\infty$ (equivalently, the normalized call vanishes at infinite strike) is strict as well: it holds exactly when $\beta_R<2$.

*Proof.* In either wing $w\sim\beta|k|$, $|w'|\to\beta$, and $w''\to0$ by equation (4). The first bracket of equation (7) tends to $1-\tfrac12=\tfrac12$, so its square tends to $\tfrac14$; the middle term tends to $\beta^2/16$ because $1/w\to0$; the last term vanishes. This gives equation (8). For the boundary, with $d_+(k)=-k/\sqrt{w}+\tfrac12\sqrt{w}$ and $w\sim\beta_R k$ on the right,

$$
d_+(k)=\sqrt{k}\Big(-\tfrac{1}{\sqrt{\beta_R}}+\tfrac{\sqrt{\beta_R}}{2}\Big)+o(\sqrt k),
$$

whose leading coefficient is negative exactly for $\beta_R<2$; at $\beta_R=2$ the two terms cancel and $d_+\to0$. For the boundary order, write the right wing at $\beta_R=2$ as $w(k)=2k+\alpha+O(k^{-1})$. Then $kw'/(2w)=\tfrac12-\alpha/(4k)+O(k^{-2})$, so the first bracket of equation (7) squares to $\tfrac14+\alpha/(4k)$; the middle term is $\tfrac14+1/(2k)$ up to $O(k^{-2})$ because $w'^2\to4$ and $1/w=1/(2k)+O(k^{-2})$; and $w''$ contributes $O(k^{-3})$. Subtracting gives equation (9). ∎

Figure 2 makes the mechanism visible. The map $\beta\mapsto(4-\beta^2)/16$ is a downward parabola crossing zero at Lee's cap $\beta=2$: below the cap the tail of $g$ is a positive constant, above it a negative one. Carried into a concrete slice, a wing with $\beta=1.6$ settles onto a positive plateau far out, while a wing with $\beta=2.3$ settles onto a negative one — a butterfly arbitrage that lives arbitrarily deep in the tail.

> **Figure 2 — Lee's bound, inside the density (figure not included in this pack).** Panel A: the asymptotic value of the Durrleman factor is $(4-\beta^2)/16$, which changes sign exactly at $\beta=2$; past the cap the far-tail density is negative. Panel B: two symmetric slices differing only in wing slope, followed far out — $\beta=1.6$ rises to its positive tail limit, $\beta=2.3$ falls to its negative one. The wing slope is not cosmetic; it fixes the sign of the density in the tail. — Panel A plots the downward parabola $(4-\beta^2)/16$ over $\beta$, positive left of $\beta=2$, zero at the cap, negative beyond. Panel B follows $g(k)$ for two concrete symmetric slices deep into the wing: the $\beta=1.6$ curve levels off on a positive plateau ($(4-1.6^2)/16=0.09$), while the $\beta=2.3$ curve settles onto a negative plateau ($(4-2.3^2)/16\approx-0.081$), a butterfly violation living arbitrarily far out of the money.

> **Caution — the boundary itself is a trap (committee revision R1, 2026-07-24).** Both screens are silent *at* the cap, and Proposition 2 shows the limit decides nothing there. The slice $(a,b,\rho,m,s)=(0.04,\,2,\,0,\,0,\,0.2)$ makes it concrete: minimum total variance $0.44$ (floor clean), $\beta_L=\beta_R=2$ exactly, so a cap at $2$ charges zero penalty — yet $\alpha=a-2m=0.04<2$, and by equation (9) $g(10)\approx-0.0485$: genuinely negative tail density behind two passing screens. This is why the production default cap is *strictly buffered*, $\beta_{\max}=1.95<2$: the buffer restores "$\beta\le\beta_{\max}\Rightarrow g$ eventually positive" and excludes only laws whose moment budget beyond the first is already negligible ($p^\star=(2-\beta)^2/(8\beta)<2\times10^{-4}$ at the buffered cap). Nor is the trap hypothetical: on the reference live surfaces (2026-07-18) one SPY expiry fitted under the old cap sat exactly at $b(1+|\rho|)=2.0000$; the buffered refit lands at $1.9500$ and moves no quote by more than $0.03$ vol bp, while the other eleven nodes are byte-identical. The counterexample is certification-locked (`svi_lee_boundary`).

**Proposition 3 (The coded screens, in JW units).** Under the conversion of the section "Trader coordinates that split tail from belly", the two production screens read directly on the wing handles: the floor condition $w_\star\ge0$ is $\widetilde v\ge0$, and Lee's cap $b(1+|\rho|)\le\beta_{\max}$ is

$$
\max(p,c)\,\sqrt{v\tau}\ \le\ \beta_{\max}\ (=1.95).
$$

*Proof.* The first is the definition of $\widetilde v$ (section "Trader coordinates that split tail from belly") times $\tau>0$. For the second, $\beta_L=p\sqrt{w_0}$ and $\beta_R=c\sqrt{w_0}$ with $w_0=v\tau$, so $b(1+|\rho|)=\max(\beta_L,\beta_R)=\max(p,c)\sqrt{v\tau}$. ∎

So a desk can sanity-check a smile in one glance: floor non-negative, larger wing handle strictly under the cap. Read them honestly, though: the cap is a *wing* statement, but the floor is attained at the hyperbola's vertex — $\widetilde v$ is a *belly* handle, and calling both "tail screens" (as an earlier edition of this note did) made the mathematics internally inconsistent. Neither certifies the interior.

### 3.1 The moment map, and when a moment may be shown

A note titled "moments" owes the reader the actual map. Lee's correspondence between a wing slope and the critical moment is explicit in both directions: for $0<\beta\le2$,

$$
\beta \;=\; 2-4\Big(\sqrt{(p^\star)^2+p^\star}-p^\star\Big),
\qquad
p^\star \;=\; \frac{(2-\beta)^2}{8\beta}, \tag{10}
$$

where on the right wing $1+p^\star$ is the critical moment order of $S_T$ (the mirror convention holds on the left with the negative moments). The two forms round-trip exactly; what Figure 3 adds is the *conditioning*, which is where a desk gets hurt. As $\beta\to0$ the budget $p^\star$ explodes and its sensitivity $|\mathrm{d} p^\star/\mathrm{d}\beta|\sim 1/(2\beta^2)$ with it: a flat-ish wing pins essentially *no* upper bound on the moments, and small quote-window changes move the inferred moment violently. As $\beta\to2$ the budget collapses to zero — at the buffered production cap the entire budget beyond the first moment is $p^\star=1.6\times10^{-4}$, which is why the R1 buffer costs nothing economically.

> **Figure 3 — The moment map and its conditioning (figure not included in this pack).** Panel A: Lee's budget $p^\star=(2-\beta)^2/(8\beta)$ (log scale); the dashed line is the buffered production cap $\beta_{\max}$, the dotted line the broken boundary $\beta=2$. Panel B: the sensitivity $|\mathrm{d} p^\star/\mathrm{d}\beta|$ explodes as $\beta\to0$ — a shallow wing does not identify a moment. — Panel A plots the moment budget $p^\star$ against wing slope $\beta$ on a logarithmic vertical axis: it diverges as $\beta\to0$, decays monotonically, and collapses to $1.6\times10^{-4}$ at the dashed buffered cap $\beta_{\max}=1.95$ before hitting exactly zero at the dotted broken boundary $\beta=2$. Panel B plots the absolute sensitivity of the budget to the slope, growing like $1/(2\beta^2)$ toward flat wings. Together the panels show both ends are treacherous: a shallow wing identifies no moment, and near the cap the entire remaining moment budget is economically negligible — which is why buffering the cap from 2 to 1.95 costs nothing.

One more condition is not negotiable. Lee's formula applies to a genuine arbitrage-free distribution; a tail-clean slice with $g<0$ in the belly (next section) has *no* risk-neutral law, so its wing slopes are not the moments of anything. A fitted $\beta$ is at most a *candidate* moment indicator, conditional on the slice passing the global butterfly certificate. Production policy follows: no JW or moment quantity is published today (the product caution of Remark 1's section), and any future moment surface is gated on the same belly certificate that gates marks — an uncertified slice can no more display a moment than become a mark.

**Exercise 1.** Show from equation (6) that $\beta_L+\beta_R=2b$ and $\beta_R-\beta_L=2b\rho$, so the two wing slopes carry exactly the same information as $(b,\rho)$. Deduce that Lee's cap constrains only the steeper wing, and that a put-skewed slice ($\rho<0$) can violate it on the put side while the call side is far from the bound.

## 4. The belly escapes

The word "convex" hides two different second derivatives. Raw SVI has $w''>0$ by construction (Proposition 1). A butterfly spread, however, tests the convexity of the option *price* in strike, which is the sign of $g$ in equation (7), and $g$ mixes $w$, $w'$ and $w''$. In the wings these agree — $g$'s sign is Lee's — but in the belly they need not. It is worth fixing four increasingly strong meanings of "valid" once, because the note turns on the gaps between them.

**Table 2 — Five tiers of "valid." The first is hard; the second is a *belly* condition and the third a tail condition, both soft in the raw chart and structural in the default one; the last two require conditions no single coefficient box supplies. The counterexample below sits in the gap between tiers three and four: tail-clean, butterfly-dirty.**

| Tier | Mathematical statement | Production status |
|---|---|---|
| Structural | $b>0$, $\lvert\rho\rvert<1$, $s>0$ | hard, by reparametrization (section "Fitting the slice"); the structural chart hardens the next two tiers as well |
| Positive floor | $w_\star>0$ — a vertex/belly condition | soft coded screen (structural under the default chart) |
| Wing-admissible | $\max(\beta_L,\beta_R)<2$ strictly | soft screen fenced at $\beta_{\max}=1.95$ (structural under the default chart) |
| Butterfly-clean | $g(k)\ge0$ for all $k$ (with the call boundary) | belly CERTIFICATE at publish: uncertified slices are repaired or blocked |
| Calendar-clean | $w_{T_1}(k)\le w_{T_2}(k)$ for $T_1<T_2$ | soft model-agnostic hinge (Note 10) + published-family audit; not structural |

That the cheap screens do not reach tier four is not a worry in the abstract — it is a specific, classical slice. Axel Vogt's example, reproduced as Example 3.1 by Gatheral and Jacquier [GatheralJacquier2014], is

$$
(a,b,\rho,m,s)=(-0.0410,\ 0.1331,\ 0.3060,\ 0.3586,\ 0.4153).
$$

Its minimum total variance is 0.0116 (floor clean), its larger Lee coefficient is 0.174 (far under the cap of 1.95), and by equation (8) *both* tails of $g$ sit at $\approx0.25>0$: the slice is impeccable in the wings. Yet $g$ dips to $-0.033$ near $k\approx0.88$ — in the belly, between the two clean tails — so the Black density is negative there and the slice is genuinely arbitrageable (Figure 4). Strict convexity of $w$ did not protect strike-convexity of the price.

> **Figure 4 — The honesty centrepiece (figure not included in this pack).** Panel A: Axel Vogt's slice is positive, strictly convex, with a positive minimum and a Lee slope far under the cap — both cheap screens pass. Panel B: its Durrleman factor approaches the positive tail limits $(4-\beta^2)/16$ on both sides (dotted), yet turns negative in the belly. The floor fences the vertex and the caps fence the wings; the interior escapes both — which is exactly what the belly certificate now closes at publish time. — Panel A plots the Vogt slice's total variance: strictly positive (minimum 0.0116), smooth, strictly convex, with wing coefficients no larger than 0.174 against the 1.95 cap. Panel B plots $g(k)$ with the two dotted horizontal tail limits, approximately 0.249 on the left and 0.248 on the right; the curve approaches both from inside yet swings negative in between, bottoming at $-0.033$ near $k\approx0.88$. The arbitrage lives strictly between two clean tails, in the region no cheap fence reaches.

The exact butterfly-free domain of raw SVI is known — Martini and Mingone [MartiniMingone2022] characterize it completely — but it is not one short inequality: the test involves parameter rescaling, root finding and a numerical minimization. Vol-Fitter's calibrator does not implement that certified domain inside the optimizer. It instead *bounds, measures, certifies, and repairs or rejects* in a stack of five layers, at increasing distance from the core fit:

1. **Core screens** (always in the objective): the floor and Lee rows of equation (11), finite-weight, zero on a tail-clean slice.
2. **Extrapolated-region enforcement** (opt-in, default off; Notes 09–10): tapered rows penalizing sampled $g<0$ on the slice's own envelope, a tapered calendar hinge against the previous displayed slice, and a wing-order hinge. Only this small block is finite-differenced, so the fit runs a hybrid Jacobian.
3. **Advisory diagnostics** (always on): the Quality view measures and reports the remaining extrapolated-region $g<0$ per fit — measurement, not enforcement.
4. **Publish-time wing projection** (export only; Note 09): a discrete projection of the exported wing samples that raises prices only, leaving the fitted core pinned.
5. **Belly certificate + acceptance rule** (committee revision R2, always on): a dense post-fit Durrleman-$g$ certificate over the *traded* range — the region layers 1–4 cannot reach — computed from the model's own derivatives in ~0.05 ms. An uncertified belly fails readiness and *hard-blocks* publish (HTTP 409); the published family additionally carries a calendar audit proving the wing projection introduced no crossings. An uncertified slice cannot become a mark.

The optimizer itself still roams the unconstrained chart — a trial iterate may be arbitrageable — but a slice can no longer LEAVE the system as a mark without passing the certificate: layers 1–4 bound the tails, measure the belly, and clean the published boundary; layer 5 is the gate.

**How $g$ is measured is part of the guarantee.** An earlier backtest metric evaluated $g$ by finite-differencing *reconstructed option prices*, and its numerical noise flagged 28.3% of provably-clean LQD slices as arbitrageable. Recomputed analytically from each model's own $(w,w',w'')$, the LQD rate reads 0.0%, and SVI's flagged rate fell from 20.8% to 9.2% — the survivors being genuine belly violations of the kind in Figure 4. The production rule that came out of that audit: the diagnostic is always computed on model derivatives, never by differencing prices (Note 09 gives the cross-model treatment). It is a reminder that a badly *measured* $g$ can manufacture arbitrage that isn't there, just as a tail-only screen can miss arbitrage that is.

### 4.1 The two soft screens, precisely

The optimizer adds to the data residual two rows that are exactly zero on a tail-clean slice and grow linearly past the boundary:

$$
r_{\mathrm{core}}(\theta)=W\begin{pmatrix}
\max\!\big(-(a+b\,s\,q),\ 0\big)\\[2pt]
\max\!\big(b(1+|\rho|)-\beta_{\max},\ 0\big)
\end{pmatrix},\qquad q=\sqrt{1-\rho^2}, \tag{11}
$$

with residual multiplier $W=1000$ and cap $\beta_{\max}=1.95$. The first forbids negative total variance at the belly's floor; the second is Lee's wing bound. Because both vanish on a clean fit, a tail-clean smile is byte-identical with or without them: they are a feasibility fence, not a regularizer.

> **Caution.** Read $W$ for what it is. It multiplies the *residual* rows, so the least-squares objective receives an effective $W^2$ on the squared violation; and the two rows do not even share a unit — one is a total variance, the other a dimensionless slope — so $W$ is a residual multiplier, not a "weight in vol²." It is deliberately large enough to dominate a violated constraint and invisible on a clean one. It is not a fit-quality dial: raising it cannot improve a feasible fit, and lowering it only lets the optimizer wander into the arbitrageable cone. Both fences are also adjustable rather than unconditional, though the plumbing of the adjustment is chart-dependent: under the raw rollback chart, setting the weight to zero disables the rows and raising the cap to $2$ and beyond re-opens the boundary trap of Proposition 2; under the default structural chart the rows are structurally inert (zeroing $W$ changes nothing), and `leeSlopeMax` is instead the *lift's ceiling* — raising it to $2$ re-opens the same trap through a different door, by letting the wing reach the boundary structurally. Either way they are configuration, not guarantees.

## 5. Trader coordinates that split tail from belly

Raw $(a,b,\rho,m,s)$ are excellent computational coordinates and poor market language: no single one is "the level" or "the skew," and, as Figure 5 shows, three of them move a tail and the belly at once. A desk wants to name the smile by its features: where ATM volatility sits, how steeply it leaves the money, how heavy each wing is, and where it bottoms. The jump-wing parametrization does exactly this, and — the reading this note presses — it sorts the five numbers into *two tail handles and three belly handles*.

> **Figure 5 — Why raw coordinates are poor market language (figure not included in this pack).** Only $a$ (vertical shift) and $m$ (core translation) move a single feature. Each of $b,\rho,s$ moves a wing *and* the belly together, so a trader cannot dial one market observable without disturbing others — the motivation for a second chart. — The figure perturbs one raw parameter per panel around a base slice. The $a$-panel is a pure vertical translation and the $m$-panel a pure horizontal translation of the rounded core. The $b$-panel steepens both wings while lifting the minimum; the $\rho$-panel tilts the wings in opposite directions while dragging the minimum sideways; the $s$-panel simultaneously deepens and broadens the belly. Three of five coordinates are visibly entangled across tail and belly features.

**Definition 1 (SVI-JW handles).** At variance clock $\tau$, with $w_0=w(0)$ and $w_\star=\min_k w$, the jump-wing coordinates of a slice are

$$
\underbrace{v=\frac{w_0}{\tau},\quad
\psi=\big(\sqrt{w}\big)'(0),\quad
\widetilde v=\frac{w_\star}{\tau}}_{\text{belly handles}},\qquad
\underbrace{p=\frac{\beta_L}{\sqrt{w_0}},\quad
c=\frac{\beta_R}{\sqrt{w_0}}}_{\text{tail handles}}. \tag{12}
$$

Substituting equation (2) gives the classical closed forms [GatheralJacquier2014, Sec. 3.3]:

$$
v=\frac{w_0}{\tau},\quad
\psi=\frac{b}{2\sqrt{w_0}}\Big(\rho-\frac{m}{\sqrt{m^2+s^2}}\Big),\quad
p=\frac{b(1-\rho)}{\sqrt{w_0}},\quad
c=\frac{b(1+\rho)}{\sqrt{w_0}},\quad
\widetilde v=\frac{a+b\,s\,q}{\tau}. \tag{13}
$$

The split is not cosmetic. The three belly handles are read on the implied-volatility chart, and the two tail handles are read on the total-variance chart, in different units:

$$
I(0)=\sqrt v,\quad
I'(0)=\frac{\psi}{\sqrt\tau},\quad
I(k_\star)=\sqrt{\widetilde v},\qquad
\beta_L=p\sqrt{v\tau},\quad
\beta_R=c\sqrt{v\tau}. \tag{14}
$$

Thus $v,\widetilde v$ are *variances* (the IV chart shows their square roots); $\psi$ is the ATM slope of *total volatility* $\sqrt w$, equal to $\sqrt\tau$ times the working-IV slope, *not* the plotted tangent; and $p,c$ are normalized *total-variance* wing slopes, not slopes of the IV curve. Figure 6 annotates a fitted slice in exactly these units, with the tail handles on the total-variance panel where they live.

> **Figure 6 — The five handles in their honest units (figure not included in this pack).** Panel A (IV): the three belly handles — the level $\sqrt v$, the minimum $\sqrt{\widetilde v}$, and the ATM tangent of slope $\psi/\sqrt\tau$. Panel B (total variance): the two tail handles, the asymptote slopes $p\sqrt{v\tau}$ and $c\sqrt{v\tau}$. Plotting all five on one IV axis would give the wing handles units they do not have. — Panel A shows the working-IV smile annotated with the ATM level $\sqrt v$ at $k=0$, the ATM tangent line of slope $\psi/\sqrt\tau$, and the minimum $\sqrt{\widetilde v}$ marked at $k_\star$: the three belly handles, each on the axis where a trader reads it. Panel B shows the same slice in total variance with the two asymptotic rays drawn in at slopes $p\sqrt{v\tau}$ (put) and $c\sqrt{v\tau}$ (call): the tail handles, in their native total-variance units. The two-panel layout enforces the unit discipline of Table 3.

**Table 3 — Three belly handles and two tail handles, in three related but distinct languages: annualized variance, total-volatility skew, and normalized total-variance wings. Keeping the units explicit prevents nearly every JW misreading.**

| Handle | Reads | Functional | Visible as | Common mistake |
|---|---|---|---|---|
| $v$ | belly | $w(0)/\tau$ | ATM IV is $\sqrt v$ | treating $v$ as a volatility |
| $\psi$ | belly | $(\sqrt w)'(0)$ | IV tangent is $\psi/\sqrt\tau$ | calling $\psi$ the plotted slope |
| $\widetilde v$ | belly | $w_\star/\tau$ | minimum IV is $\sqrt{\widetilde v}$ | assuming positivity from the name |
| $p$ | tail | $\beta_L/\sqrt{w_0}$ | put slope $p\sqrt{v\tau}$ | reading it on the IV axis |
| $c$ | tail | $\beta_R/\sqrt{w_0}$ | call slope $c\sqrt{v\tau}$ | reading it on the IV axis |

**Normalized indicators are not actual tails.** Look again at equation (14): $\beta_L=p\sqrt{v\tau}$ and $\beta_R=c\sqrt{v\tau}$. The handles $p,c$ are *normalized* wing indicators; the *actual* asymptotic slopes — the objects Lee's bound and the moment map, equation (10), read — carry a factor of the supposedly belly-only level $v$. So JW is a useful normalized quoting convention, *not* an orthogonal decomposition into independent tails and belly: bump the ATM level holding $(p,c)$ fixed and both actual Lee slopes move, and the inferred moments with them. Figure 7 measures the full response matrix on the running slice: the $+\Delta v$ row moves $\beta_R$ by $+0.0017$ and the right moment budget $p^\star_R$ by $-0.6032$ — with the "tail handles" untouched. Four distinct objects, four distinct behaviours: normalized indicators $(p,c)$, actual slopes $(\beta_L,\beta_R)$, moment exponents $(p^\star)$, and the trader quantities (RR/BF) that mix all of them.

> **Figure 7 — The bump-response matrix (committee revision) (figure not included in this pack).** Rows: one bump per JW handle ($+0.004$ on $v$, $+0.05$ on $\psi$, $+0.10$ on $p$ and $c$, $+0.002$ on $\widetilde v$, from the running slice). Columns: the response of ATM vol, the 25Δ risk reversal and butterfly (decimal vol), the ACTUAL wing slopes $\beta_L,\beta_R$, the right moment budget $p^\star_R$, the variance floor $w_\star$, and the var-swap vol. Colour is the sign and relative size within each column; the annotation is the raw signed change. The off-diagonal structure is the point: no handle owns its row's name — an ATM-level bump is also a tail and moment event. — The figure is a five-row, multi-column signed heatmap. Each row applies one handle bump to the running slice and re-reads every desk quantity; each cell is coloured by sign and relative magnitude within its column and annotated with the raw signed change. The most instructive row is $+\Delta v$: with $(p,c)$ held fixed it still moves the actual right wing slope $\beta_R$ by $+0.0017$ and swings the right moment budget $p^\star_R$ by $-0.6032$, while the "tail handles" themselves are untouched. The dense off-diagonal pattern shows no handle owns its column: JW is a quoting convention, not an orthogonal control panel.

### 5.1 Inverting the handles, and where the belly information is lost

Reading JW from raw is evaluation. The reverse — reconstructing a whole hyperbola from five measurements — is the interesting direction, and it is the one the shipped converter `jw_to_raw` computes (today its only repository caller is a benchmark test; see the product-status note below). The two tail handles fix the scale and tilt,

$$
b=\frac{\sqrt{w_0}}{2}(p+c),\qquad \rho=\frac{c-p}{c+p},\qquad w_0=v\tau, \tag{15}
$$

the ATM slope fixes the normalized displacement

$$
\chi:=\frac{m}{\sqrt{m^2+s^2}}=\rho-\frac{4\psi}{p+c}, \tag{16}
$$

and the belly gap $v-\widetilde v$ then sets the width. Writing

$$
D(\rho,\chi)=\frac{1-\rho\chi}{\sqrt{1-\chi^2}}-\sqrt{1-\rho^2}, \tag{17}
$$

the remaining coordinates are

$$
s=\frac{(v-\widetilde v)\,\tau}{b\,D(\rho,\chi)},\qquad
m=\frac{\chi\,s}{\sqrt{1-\chi^2}},\qquad
a=\widetilde v\tau-b\,s\sqrt{1-\rho^2}, \tag{18}
$$

because $\sqrt{m^2+s^2}=s/\sqrt{1-\chi^2}$, so subtracting $w_\star=\widetilde v\tau$ from $w_0=v\tau$ leaves $b\,s\,D$. The denominator $D$ has a clean geometric form: setting $\rho=\sin\alpha$, $\chi=\sin\gamma$,

$$
D=\frac{1-\cos(\alpha-\gamma)}{\cos\gamma}\ \ge\ 0, \tag{19}
$$

with equality iff $\chi=\rho$. This single observation gives both the domain and the singularity.

**Theorem 1 (The full smooth image of the JW map).** Fix $\tau>0$ and restrict raw SVI to $b>0$, $|\rho|<1$, $s>0$, $w_0>0$.

1. A JW point has a unique regular inverse iff

$$
v>0,\quad p>0,\ c>0,\quad -\frac p2<\psi<\frac c2,\quad \psi\ne0,\quad \widetilde v<v, \tag{20}
$$

and then equations (15)–(18) return it.

2. The image also contains the singular stratum $v>0,\ p,c>0,\ \psi=0,\ \widetilde v=v$, every point of which is represented by *infinitely many* raw slices. There are no other smooth, nondegenerate image points.

*Proof.* If $p,c>0$ then equation (15) gives $b>0$ and $\rho\in(-1,1)$; conversely a valid slice has $p,c>0$. From equation (16), using $(\rho-1)(p+c)=-2p$ and $(\rho+1)(p+c)=2c$,

$$
|\chi|<1\iff \rho-1<\tfrac{4\psi}{p+c}<\rho+1\iff -\tfrac p2<\psi<\tfrac c2,
$$

which keeps $m=\chi s/\sqrt{1-\chi^2}$ finite. By equation (19), $D>0$ exactly when $\chi\ne\rho$, i.e. $\psi\ne0$; then $s>0$ in equation (18) requires the numerator $v-\widetilde v>0$. Each failure breaks a requirement: $p+c\le0$ or one of $p,c\le0$ forces $b\le0$ or $|\rho|\ge1$; $\psi$ outside the band sends $|\chi|\ge1$; $\psi=0$ zeroes $D$; $\widetilde v\ge v$ makes $s\le0$. For the singular stratum, $\psi=0$ gives $\chi=\rho$, i.e. $k_\star=0$ by equation (5), so ATM *is* the minimum and $\widetilde v=v$. Conversely, fix $v,p,c$ on the stratum; equation (15) sets $b,\rho$, and for *any* $s>0$, $m=\rho s/\sqrt{1-\rho^2}$ with $a=v\tau-b\,s\sqrt{1-\rho^2}$ yields $k_\star=0$, $w_\star=w_0=v\tau$, and reproduces the same five handles. ∎

**Remark 1 (The blind spot is the belly).** The free width $s$ on the singular stratum is not an abstract degeneracy: it is exactly the belly curvature. On that stratum ATM sits at the minimum, and the handles pin the level $v$ and both tails $p,c$ but say nothing about how sharply the curve turns through its bottom. Figure 8B shows three raw bodies that agree on $(v,0,p,c,v)$ and differ only in how rounded the belly is. The jump-wing chart is a fine coordinate system *away* from this stratum and ill-conditioned near it: by equation (19) the denominator vanishes *quadratically*,

$$
D\sim\frac{(\chi-\rho)^2}{2(1-\rho^2)^{3/2}}=\frac{8\psi^2}{(p+c)^2(1-\rho^2)^{3/2}},
\qquad \psi\to0, \tag{21}
$$

so recovering a finite width as $\psi\to0$ forces $v-\widetilde v=O(\psi^2)$, and a naive evaluation of equation (17) subtracts two nearly equal numbers. The reference implementation of Appendix D uses an algebraically identical but cancellation-free denominator; no rearrangement can restore a curvature the handles never carried.

> **Figure 8 — The $\psi=0$ stratum is a belly blind spot (figure not included in this pack).** Panel A: the inverse denominator $D$ is an angular gap between the unit vectors $u_\rho$ and $u_\chi$; it closes exactly when $\psi=0$. Panel B: three raw slices with identical $(v,0,p,c,v)$ — same level, same asymptotic rays — differing only in belly width $s$. The handles fix the tails and lose the interior curvature. — Panel A draws the unit semicircle with the vectors $u_\rho=(\rho,\sqrt{1-\rho^2})$ and $u_\chi=(\chi,\sqrt{1-\chi^2})$; by equation (19), $D$ is proportional to one minus the cosine of the angle between them, and the gap closes exactly when $\chi=\rho$, i.e. $\psi=0$. Panel B overlays three raw slices built with the singular-family construction at three different widths $s$: identical ATM level, identical minimum (sitting at ATM), identical asymptotic rays — and three visibly different curvatures through the bottom. The information the five handles never carried is precisely that curvature.

> **Caution — product status, and the unguarded converter.** Production calibration fits and stores *raw* SVI as the selected overlay family and displays three model-agnostic numeric handles — ATM vol, skew and curvature by finite differences of the displayed curve — for every model. There is no backend `raw_to_jw`, no five-handle JW API/UI entry, no JW bumping and no JW export; those are candidate features, not shipped ones. The shipped `jw_to_raw` implements equations (15)–(18) with *zero* domain checks, and its failure modes differ by case rather than being uniformly silent: a scalar $p+c=0$ raises a division error; $\psi$ outside $(-p/2,c/2)$ takes the square root of a negative and returns NaNs; $\widetilde v\ge v$ returns $s\le0$, not a slice; a near-zero $\psi$ amplifies rounding. This is deliberate — the only caller feeds it benchmark handles well inside Theorem 1 — but it makes the regular domain a *contract*, now test-locked. Since committee revision R5 the guarded inverse SHIPS: `jw_to_raw_checked` validates the complete domain and raises a structured `JWDomainError` (reason codes for each inequality, the singular stratum rejected explicitly) using the cancellation-resistant denominator of Appendix D — any future user-facing JW workflow goes through it, and the unguarded fast path remains only for validated benchmark callers. The desk-unit conversions of the committee's challenge 11 ship alongside it (`models/svi_jw/desk.py`): ATM convention, 25/10-delta risk reversals and butterflies solved on the model smile, the actual wing slopes, the var swap — and the missing derivative, a forward-bump re-read showing exactly which desk quantities a pure $F_T$ error masquerades as (on a put skew: a phantom ATM *and* risk-reversal move). No JW UI ships; the layer is the contract any future one sits behind. The same revision added an adversarial input battery run on *both* optimizer charts — crossed quotes, duplicate strikes, one-sided boards, saturated wings — and a deterministic refusal for boards with fewer than three usable quotes: five parameters fitted to two points is not a smile, and the calibrator now says so instead of improvising one.

**A condition atlas, with real chains on it.** The singular stratum is not the only place the inverse is fragile, and — the committee's sharpest phrasing — $\psi\approx0$ is *not exotic*: ATM sitting at the smile minimum is precisely where a trader would expect the coordinates to be simplest. Figure 9 maps the conditioning of the (scaled) jw→raw Jacobian over the $(\psi,\,p+c)$ wedge: the ridge on the $\psi=0$ line is the quadratic blind spot ($D=O(\psi^2)$, so $v-\widetilde v=O(\psi^2)$ and quote noise is amplified by $1/\psi^2$); conditioning also deteriorates toward the domain boundaries $\psi\to-p/2$ or $c/2$ (where $|\chi|\to1$) and as $p+c\to0$. The overlaid points are the twelve reference-fixture nodes (SPY/NVDA/AAPL, Massive 2026-07-18) refitted through the production calibrator and read back through the analysis-side functionals, and they sharpen the committee's point twice over: the closest node comes within $|\psi|=0.059$ of the stratum (ordinary markets DO graze the blind spot), and because the normalized wing weight scales as $\beta/\sqrt{w_0}$, the short-dated nodes sit at $p+c$ of order $10$–$100$ where the chart is ill-conditioned ($10^5$–$10^7$) *everywhere*, stratum or not. Any future JW surface must carry this atlas's warnings, not just the regular-domain check.

> **Figure 9 — Condition atlas of the jw→raw inverse (figure not included in this pack).** Condition atlas of the jw→raw inverse over the symmetric wedge $|\psi|<(p+c)/4$ (log₁₀ condition number of the relative-scaled Jacobian; $v,\widetilde v,\tau$ fixed at the running slice's values). The dashed line is the singular stratum $\psi=0$; conditioning blows up quadratically into it and toward the wedge boundaries. White dots: the 12 reference-fixture nodes — real chains at real maturities, the nearest at $|\psi|=0.059$. — The figure is a heatmap of the base-10 logarithm of the condition number over the $(\psi, p+c)$ wedge. A bright ridge runs along the dashed $\psi=0$ line (the quadratic blind spot), and the colour also intensifies toward the wedge edges $\psi\to-p/2, c/2$ and toward $p+c\to0$. Twelve white dots mark the SPY/NVDA/AAPL reference-fixture nodes refitted through the production calibrator: the nearest grazes the stratum at $|\psi|=0.059$, and the short-dated nodes sit in the $p+c\sim10$–$100$ band where the condition number is $10^5$–$10^7$ regardless of $\psi$. Real markets live near the tears in this chart, not safely away from them.

**Exercise 2.** On the singular stratum, differentiate the five functionals, equation (13), with respect to $s$ at fixed $(v,\psi,p,c,\widetilde v)$ using $m=\rho s/\sqrt{1-\rho^2}$, $a=v\tau-b\,s\sqrt{1-\rho^2}$, and verify that $\partial(v,\psi,p,c,\widetilde v)/\partial s=0$. Conclude that the Jacobian of the raw→JW map drops rank there — an analytic statement of the belly blind spot.

## 6. Fitting the slice: fit the belly, fence the tails

The optimizer never handles a bounded raw vector. It receives $\theta\in\mathbb{R}^5$ and maps

$$
a=\theta_1,\quad
b=\operatorname{softplus}(\theta_2),\quad
\rho=\tanh(\theta_3),\quad
m=\theta_4,\quad
s=e^{\theta_5}, \tag{22}
$$

so that every finite $\theta$ is a structurally valid hyperbola (tier one of Table 2). This removes the box constraints entirely: the unconstrained Levenberg–Marquardt (LM) solver never wastes a step on the boundary and never proposes a nonsensical hyperbola. It guarantees no more than structure — $a$ stays free, so a trial slice can still carry negative total variance somewhere, which the residual handles by flooring $w$ at $10^{-12}$ inside the square root (a solver device; `RawSVI.implied_vol` itself has no floor). Wing feasibility is the business of the soft rows, equation (11); belly feasibility is not enforced inside the optimizer, by design — the belly certificate gates it at the door instead (section "The belly escapes").

**The structural chart (committee revision R3, the shipped default).** There is a chart that guarantees more. Parameterize the slice by the quantities the guarantees are *about* — $(\beta_L,\beta_R,k_\star,w_\star,\kappa_\star)$: the two actual wing slopes, the vertex location, the minimum total variance, and the vertex curvature $\kappa_\star=w''(k_\star)$ — with the lifts $\beta=\beta_{\max}\operatorname{logistic}(\cdot)$, $w_\star=\operatorname{softplus}(\cdot)$, $\kappa_\star=e^{(\cdot)}$. The raw recovery is exact ($b=(\beta_L+\beta_R)/2$, $\rho=(\beta_R-\beta_L)/(\beta_R+\beta_L)$, $s=b(1-\rho^2)^{3/2}/\kappa_\star$, $m=k_\star+s\rho/\sqrt{1-\rho^2}$, $a=w_\star-bs\sqrt{1-\rho^2}$), and now every finite $\theta$ has a strictly positive floor and strictly Lee-clean wings: the two penalty rows are structurally zero, the trial-$w$ clip never fires, and the unit-mixing question about $W$ dissolves. Shipped as `sviChart="structural"` (`models/svi_jw/structural.py`), with a closed-form Jacobian since 2026-07-26 — the fourth layer of the next subsection, measured $2.1$–$2.4\times$ over the finite-difference path it replaced. On the twelve reference-fixture nodes the two charts agree to $0.0000$ vol bp wherever the raw chart converged — but the raw chart *exhausted its 500-evaluation budget on five of the twelve* while the structural chart converged in 30–86 evaluations on all of them and ran ~3× faster even before its analytic Jacobian landed: the penalty kinks it removes are exactly where LM was burning its budget. The frozen-regime benchmark confirmed it at scale (~29k fits per arm, three regimes, pre-registered gate; two rounds — the first flushed out and fixed a lift-saturation bug, an LM trial underflowing $e^{\theta}$ to an exact zero and dividing by it): precision better or equal in all twelve medians, ZERO hard breaks, 594 vs 9,472 evaluation-cap exhaustions (the raw chart fails to converge on a THIRD of real fits), and among fits that actually converge a LOWER butterfly-arb incidence (0.82% vs 1.08% — the raw chart's cleaner headline was a survivorship artifact of its non-converged third). One honesty detail of the adjudication itself: the pre-registered round-two verdict was recorded as HOLD, because the original gate scored arbitrage incidence on unlike populations; the amendment — score converged against converged — was proposed and ratified the same day, and only then did round two pass all four gates. The record keeps both readings. The structural chart is the production default since 2026-07-26 (`sviChart`); the raw vector remains explicit configuration — the same evidence bar, and the same outcome, as the LQD logistic chart.

Strictness in exact arithmetic is not strictness in float64, and the analytic-Jacobian lock exposed two latent boundary leaks worth their own sentence. A logistic evaluated at a modestly large argument rounds to exactly $1.0$, parking a wing exactly *at* the cap — the fence the chart exists to keep strict; and with one wing saturated against an ordinary other, the quotient for $\rho$ rounds to $\pm1$, making $1-\rho^2$ an exact zero, the width zero, and $m$ a NaN. Production clips the logistic one ulp inside $1$ and computes $1-\rho^2$ by the exact product identity $4\beta_L\beta_R/(\beta_L+\beta_R)^2$ — a fence that silently stops being strict is precisely this note's kind of failure.

**Objective, weights, start.** The data term is a plain implied-volatility residual $r_i=\sqrt{\omega_i}\,(I(k_i)-I_i)$; bid–ask and haircut modes replace it by a vol-space band hinge with a small mid anchor. The surfaced quote-weight choices are `equal` and `tv_density` (Note 07), the same two every model gets; the low-level API also accepts arbitrary $\omega_i$ (e.g. vega², used by research scripts), which is a code capability, not a setting. The initializer is geometric and reads the belly and the wings directly: the argmin of the quoted $w$ seeds $(a,m)$, and two finite-span wing slopes seed $(b,\rho)$ through equation (6), after which equation (22) is inverted for $\theta_0$. On a liquid smile a single LM pass converges.

### 6.1 The analytic Jacobian, in four layers

The residual Jacobian is worth deriving, because it is what makes SVI the speed peer of the other models. It is three chain-rule layers on the raw chart, plus a fourth for the default one. First, the raw-parameter partials of the hyperbola, with $x,r$ from equation (3):

$$
\frac{\partial w}{\partial a}=1,\quad
\frac{\partial w}{\partial b}=\rho x+r,\quad
\frac{\partial w}{\partial\rho}=b\,x,\quad
\frac{\partial w}{\partial m}=-b\Big(\rho+\frac{x}{r}\Big),\quad
\frac{\partial w}{\partial s}=\frac{b\,s}{r}. \tag{23}
$$

Second, the data rows live in IV, so the Black chain rule for $I=\sqrt{w/\tau}$:

$$
\frac{\partial I}{\partial w}=\frac{1}{2\sqrt{w\tau}}=\frac{1}{2\tau I}, \tag{24}
$$

zeroed wherever the $w\le10^{-12}$ floor is active. Third, the reparametrization, equation (22):

$$
\frac{\mathrm{d} b}{\mathrm{d}\theta_2}=\operatorname{sigmoid}(\theta_2)=1-e^{-b},\qquad
\frac{\mathrm{d}\rho}{\mathrm{d}\theta_3}=1-\rho^2,\qquad
\frac{\mathrm{d} s}{\mathrm{d}\theta_5}=s. \tag{25}
$$

The hinge rows follow the subgradient convention "active linear part, else zero": the floor row differentiates $-(a+b\,s\,q)$, the Lee row differentiates $b(1+|\rho|)$ with the $\operatorname{sgn}(\rho)$ subgradient (zero at $\rho=0$), and each is a zero row where its violation is not strictly positive.

The fourth layer serves the default structural chart, and it is one matrix. The residual Jacobian above is assembled in raw-parameter space; the structural chart multiplies it by the closed-form $5\times5$ chain matrix $\partial(a,b,\rho,m,s)/\partial\theta$ (`structural_chain`), which mirrors the lift *exactly* — including its $\pm80$ saturation clip, whose clipped coordinate contributes a zero column because the lift is locally constant there. Nothing is re-differentiated; both charts run the same rows under the same gate, and the closed form removes the $1+P$ residual evaluations per LM step the structural chart's finite-difference path had been paying (measured $2.1$–$2.4\times$ on identical smiles). The calibrator uses the closed form whenever no var-swap or prior block is present; those blocks are not differentiated and revert the fit to finite differences — for SVI, unlike LQD, whose var-swap rows are native. Under extrapolation enforcement the fit is *hybrid*: the rows above stay analytic and only the small extrapolation block is finite-differenced.

> **Performance.** The solver is Levenberg–Marquardt, not trust-region reflective: on noisy real chains LM crosses the penalty kinks in far fewer iterations at matched tolerance (`trf` at $10^{-10}$ was measured slower on real nodes), so the analytic Jacobian is a same-convergence drop-in that swaps scipy's $1+P$ finite-difference evaluations ($P=5$) for one closed-form call. Two measurements, labelled for what they are. (i) This note's private residual/Jacobian microbenchmark on the 25-quote synthetic case (section "Worked example"), warmed median of five, single-threaded on the development machine, core rows only: 3.12 ms → 1.30 ms, a 2.40× speed-up with the two objective costs agreeing to $2.7\times10^{-33}$ (same solution within fit precision, not bit-identical). (ii) A historical real-node result: spike-regime backtest nodes, June-2026 harness, same optimizer and tolerances, 26.3 ms → 10.2 ms per fit (≈2.58×) — the finding that motivated shipping it. See Appendix B.

> **Figure 10 — Timing (figure not included in this pack).** The saving is fewer residual evaluations, not a different optimizer. Panel A is the fresh synthetic microbenchmark; Panel B the historical real-node measurement. The two have different scales and provenance and isolate the same implementation change; machine-dependent numbers and protocol live in Appendix B. — Panel A shows paired bars for the 25-quote synthetic case: 3.12 ms per fit with finite differences against 1.30 ms with the closed-form Jacobian, a 2.40× speed-up at matched objective cost (agreement $2.7\times10^{-33}$). Panel B shows the historical June-2026 spike-regime measurement on real backtest nodes: 26.3 ms before, 10.2 ms after, roughly 2.58×. Different data, different scales, same conclusion: the win is eliminating the $1+P$ perturbed evaluations per LM step.

### 6.2 The optional blocks

The optional blocks share the series' product targets through model-specific residuals, and each is byte-identical to its own absence:

- **Band fit** (Note 07): the mid residual becomes a vol-space band hinge with a small mid anchor.
- **Calendar hinge** (Note 10): the model-agnostic $\sqrt{W_{\mathrm{cal}}}\,\max(\text{floor}-w(k),0)$ against the nearer expiry — the same target LQD expresses through its quantile, written here on $w$. A finite-weight hinge drives crossings down, not provably to zero.
- **Extrapolation fences** (default off; Notes 09–10): the tapered rows of the section "The belly escapes", hybrid-Jacobian when on.
- **Var-swap target** (Note 08) and **prior persistence** (Note 13): the same targets as LQD through SVI-native residuals, so the SVI overlay now receives the prior treatment the primary model does — closing an old asymmetry in which SVI overlays got no prior at all.

## 7. Worked example: a laboratory round trip

An exact-family, noise-free recovery is not market evidence; it is the right laboratory test for a coordinate conversion and a Jacobian, since any visible miss is an implementation error. Take $\tau=0.5$ and the jump-wing handles $(v,\psi,p,c,\widetilde v)=(0.0425,-0.25,0.75,0.25,0.034)$. The *production* `jw_to_raw` builds the target raw slice $(a,b,\rho,m,s)\approx(0.010625,0.07289,-0.5,0.05831,0.10100)$; we sample 25 noise-free quotes on $[-0.35,0.30]$, refit with the production calibrator on the raw chart (named explicitly, since "default" now means structural) from the geometric start, and read the handles back — a genuine JW→raw→fit→JW loop whose forward leg is shipped code.

Report two errors, and keep them separate. The *quote* error — the report-space miss — is a maximum of $5.6\times10^{-13}$ vol bp over the 25 quotes, in 21 residual evaluations. The *latent* error — the miss in the object we actually recovered — is a maximum jump-wing round-trip deviation of $3.9\times10^{-16}$ across all five handles (Table 5 reproduces the target to display precision). The recovered wing slopes are $\beta_L=0.1093$ (put) and $\beta_R=0.0364$ (call). Both errors are at machine precision because the target *is* an SVI slice: the exercise validates the optimizer and the exact conversion, and says nothing about SVI's expressiveness on a non-SVI market. On the diagnostic grid $g$ stays above 0.343 (Figure 11C).

**Table 4 — Recovered raw coordinates.**

| Parameter | Value |
|---|---:|
| $a$ | +0.010625 |
| $b$ | +0.072887 |
| $\rho$ | −0.500000 |
| $m$ | +0.058310 |
| $s$ | +0.100995 |

**Table 5 — Recovered SVI-JW handles.**

| Handle | Value |
|---|---:|
| $v$ | +0.042500 |
| $\psi$ | −0.250000 |
| $p$ | +0.750000 |
| $c$ | +0.250000 |
| $\widetilde v$ | +0.034000 |

> **Figure 11 — The round trip through the production fit (figure not included in this pack).** The two coordinate systems round-trip through the production fit. Panel A: target and refit coincide, so the useful evidence is the residual scale (Panel B, in $10^{-13}$ vol bp) and the independent Durrleman diagnostic (Panel C). The test exercises conversion, initialization, calibration and reverse readout in one reproducible path; it deliberately says nothing about real-market fit. — Panel A superimposes the target slice built by `jw_to_raw` and the production raw-chart refit over the 25 sampled quotes on $[-0.35,0.30]$; the curves are indistinguishable. Panel B plots the per-quote residuals on a $10^{-13}$ vol bp scale, peaking at $5.6\times10^{-13}$ — machine precision reached in 21 residual evaluations. Panel C plots the independent Durrleman factor $g(k)$, staying above 0.343 on the diagnostic grid: the recovered slice is comfortably butterfly-clean where it is examined.

> **Heuristic.** On real NBBO history the published spike-regime replay measured SVI at 24.3 vol bp RMS in-sample and 26.8 out-of-sample across ≈1,576 nodes per regime — an order of magnitude worse than the laboratory number above, and the honest figure of merit. SVI is also stiffer than LQD or Local-Vol on event or double-hump shapes, for the reason the section "One belly, one turn" makes precise. (Those replay parquets are historical and not checked into this workspace; the numbers are retained for continuity with the note and deck.)

## 8. One belly, one turn

Strict convexity, $w''>0$, buys SVI one minimum and one monotone turn of the slope from $-\beta_L$ to $+\beta_R$. On a liquid equity-index chain this is exactly the right regularization: it forbids the wiggles that noise would otherwise carve into a smile. But it is also a hard expressiveness ceiling. A W-shaped total-variance target (Note 03), a double-humped event density (Note 01's double-hat), or a sharply localized short-dated kink asks the curve to turn more than once, and one hyperbola has exactly one belly. Figure 12 makes the failure quantitative: against a smooth, positive, deliberately two-minimum target, production raw SVI returns the best single-belly compromise, missing by 147.6 vol bp RMS and 351.9 vol bp at worst. Read that number for what it is (a committee correction to an earlier edition): the two-minimum target is itself *butterfly-arbitrageable* — its own Durrleman factor reads $g(0)\approx-0.059$ — so an arbitrage-aware family *should* refuse to reproduce it exactly, and the miss measures convexity rigidity against an illegal shape, not a commercial expressiveness deficit. The legal measurement follows below.

> **Figure 12 — A geometric stress test, not a market smile (figure not included in this pack).** A geometric stress test, not a market smile — and not a legal one: the two-minimum target itself violates the butterfly condition ($g(0)\approx-0.059$), so this figure demonstrates only that one convex hyperbola cannot follow a non-convex curve. The synthetic target has two minima and a central hump; SVI settles for the best single-belly compromise (A), leaving the structured residual of Panel B. For the expressiveness question asked properly — against an arbitrage-free target — see Figure 13. — Panel A shows the deliberately synthetic W-shaped target, with two local minima flanking a central hump, and the fitted raw SVI slice cutting one smooth convex compromise through it, unable to bend twice. Panel B shows the resulting signed residual: a structured oscillation tracking the target's humps, with RMS 147.6 vol bp and a worst miss of 351.9 vol bp. Because the target itself is arbitrageable at the money ($g(0)\approx-0.059$), the panel quantifies geometric rigidity only, not a commercial deficit.

**The benchmark, asked legally.** Replace the target with a genuine distribution: a martingale two-lognormal mixture (65% at $\sigma=14\%$, 35% at $\sigma=42\%$ with the component forwards summing to the martingale forward, $\tau=0.25$). Its smile is arbitrage-free *by construction* — the generator verifies $\min g=+0.389$ on a dense analytic evaluation before fitting — and its bimodal density asks for exactly the shoulder one hyperbola cannot make. Figure 13 fits the three in-house families on equal footing (equal quotes, production calibrators; the SVI leg runs the raw chart, the generator's pre-flip footing — chart choice moves convergence, not the geometric limitation this figure isolates): raw SVI misses by 118.7 vol bp RMS (held-out 115.4), while LQD fits to 19.7 (held-out 19.2) and the Multi-Core Sigmoid to 15.0 (held-out 15.2). All three FITS certify butterfly-free (min $g$ of $+0.406$ / $+0.382$ / $+0.375$): SVI's failure on this target is expressiveness, not arbitrage — its best legal compromise is simply far from a bimodal truth. An eSSVI and constrained-spline column belongs in this panel and is outstanding work (neither family is implemented in-house); the cross-model market evidence rides the benchmark-pack campaigns.

> **Figure 13 — The arbitrage-free expressiveness benchmark (committee revision) (figure not included in this pack).** Panel A: the mixture target (dots, $\min g=+0.389>0$) with the three production fits. Panel B: signed fit errors in vol bp. One hyperbola buys one belly: SVI's 118.7 bp RMS against LQD's 19.7 and MCS's 15.0 is the honest price of convexity on a bimodal law — measured against a target no arbitrage-aware model needs to refuse. — Panel A shows the two-lognormal mixture smile as dots (65% weight at $\sigma=14\%$, 35% at $\sigma=42\%$, $\tau=0.25$; verified arbitrage-free with $\min g=+0.389$) overlaid with the three production fits: LQD and the Multi-Core Sigmoid track the bimodal shoulder closely while SVI cuts one convex compromise through it. Panel B plots the signed errors in vol bp: SVI's structured miss at 118.7 bp RMS (held-out 115.4) dwarfs LQD's 19.7 (19.2) and MCS's 15.0 (15.2). All three fitted slices themselves certify butterfly-free (minimum $g$ of $+0.406$, $+0.382$, $+0.375$ respectively), isolating the gap as pure expressiveness.

Sparse identification is a second, subtler limitation, and it is where the tail/belly reading pays off once more. On a narrow or one-sided quote window the initializer's "wing slopes" are finite-span proxies read off the quoted range, not asymptotic observations, and distinct raw tuples can price the quoted strikes almost identically while implying different remote wings. The fitted *curve* can be stable even when $(a,b,\rho,m,s)$ is not. JW is easier to read, but its tail handles $p,c$ are still *extrapolated* functionals when the market has not quoted the wings. Across fits, compare prices, curves, and observed handles — not raw coefficients.

**Exercise 3.** The two-minimum target of Figure 12 is positive and smooth but not convex. Argue directly from $w''>0$ that no raw SVI slice can have two local minima, and hence that the RMS miss cannot be driven to zero by any choice of $(a,b,\rho,m,s)$ — the limitation is structural, not a matter of optimizer tuning.

## 9. What is genuinely original, and limitations

SVI, the jump-wing handles, and the arbitrage analysis are classical: raw SVI and JW are due to Gatheral, the arbitrage-free theory to Gatheral–Jacquier and Durrleman, the wing bound to Lee, and the exact butterfly domain to Martini–Mingone. The reading offered here — *wings as a moment reading of the tails, belly as the interior the cheap screens cannot reach* — is a framing, not a theorem. The implementation choices worth flagging are four: the *structural chart* (section "Fitting the slice"), which parameterizes the slice by the screened quantities themselves so the floor and cap hold at every iterate by construction — the shipped default, ratified by a pre-registered benchmark whose headline lesson was statistical (survivorship) rather than numerical; *structural validity by reparametrization*, equation (22), on the rollback chart, so even there the solver cannot leave tier one except through the two soft fences; the *exact raw↔JW conversion with a proved regular domain and an identified belly blind spot* (Theorem 1, Remark 1); and the *analytic LM Jacobians on both charts* that make SVI the speed peer of the other overlays.

Limitations, stated plainly, because a lecture that sells a model without drawing its boundary is an advertisement. Raw SVI total variance is one globally convex hyperbola with a single belly, so it cannot reproduce a W-shaped smile and can over-smooth a sharp short-dated skew (section "One belly, one turn"). It is butterfly-clean only over a cone the coded fences do not certify (section "The belly escapes"), and carries no calendar coupling on its own — that is supplied, softly, by the model-agnostic hinge of Note 10. On sparse or one-sided chains its raw parameters can be poorly identified even where the curve is stable, so comparisons should be made on curves and handles, never on $(a,b,\rho,m,s)$. And the jump-wing chart, elegant as it is, tears on the $\psi=0$ stratum, where it keeps the tails and forgets the belly.

## Appendix A. Hyperparameter atlas

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 6 — SVI and shared calibration controls.**

*Surfaced (FitSettings / OptionsSettings)*

| Knob | Default | Role |
|---|---|---|
| `model` | `lqd` | Set to `svi` to display the raw-SVI overlay. |
| `sviPenaltyWeight` $W$ | 1000 | Residual multiplier of the two tail rows, equation (11) (effective $W^2$ in the squared cost; $0$ = fences off). |
| `leeSlopeMax` $\beta_{\max}$ | 1.95 | Lee wing-slope cap on $b(1+\lvert\rho\rvert)$; buffered strictly below $2$ by default (the boundary itself admits negative tail density); values $\ge2$ are accepted but re-open the trap. |
| `sviChart` | `structural` | Optimization chart: `structural` $(\beta_L,\beta_R,k_\star,w_\star,\kappa_\star)$ makes the floor and the cap structural (benchmark-ratified default, 2026-07-26); `raw` is the historical vector, kept for comparability. |
| `weightScheme` | `equal` | Per-quote weights, `equal` / `tv_density` (Note 07); arbitrary weights exist only at the low-level API. |
| `midAnchorWeight` | $0.05$ | Mid anchor in the band-fit objective (Note 07). |
| `haircut` | $0.005$ | Absolute-vol tightening, haircut band mode only. |
| `calendarWeight` | $10^{6}$ | Calendar hinge weight (Note 10; squared objective, residual uses its root). |
| `extrapEnforce` | off | Tapered extrapolated-region fences (section "The belly escapes"); calibration-affecting, hybrid Jacobian when on. |

*Internal (reparametrization / solver)*

| Knob | Default | Role |
|---|---|---|
| $b=\operatorname{softplus}(\theta_2)$ | — | Enforces $b>0$. |
| $\rho=\tanh(\theta_3)$ | — | Enforces $\lvert\rho\rvert<1$. |
| $s=e^{\theta_5}$ | — | Enforces $s>0$. |
| LM tolerances | $10^{-15}$ | `xtol`/`ftol`/`gtol`; LM converges in few iterations, so tight tolerances are cheap. |
| trial-$w$ floor | $10^{-12}$ | Inside $\sqrt{w/\tau}$, to keep the IV residual evaluable on structurally-valid-but-negative-variance trials; not part of `RawSVI.implied_vol`. |

## Appendix B. Performance notes

1. **Levenberg–Marquardt over trust region.** On real noisy chains LM crosses the penalty kinks in fewer iterations than `trf` at matched tolerance; `trf` at $10^{-10}$ was measured slower on real nodes.
2. **Analytic Jacobian.** Closed-form Jacobian of the core residual stack (data + tail penalties + calendar) through the reparametrization, with the two scopes stated: the note's microbenchmark (25 synthetic quotes, core rows only, single-threaded development machine, warmed median of five) measured 1.30 ms vs 3.12 ms (2.40×) with objective costs agreeing to $2.7\times10^{-33}$ — same solution within fit precision, not bit-identical; the historical real-node measurement (spike-regime backtest nodes, June-2026 harness) was 26.3 ms → 10.2 ms (≈2.58×). Machine-dependent numbers belong here, not in the body. Gated to the var-swap/prior-free configuration; hybrid (analytic core + FD extrapolation rows) under `extrapEnforce`.
3. **Structural validity by construction.** The reparametrization removes box-constraint handling, so each LM step is a plain linear solve.
4. **Geometric warm start.** Reading $(a,m)$ from the belly and $(b,\rho)$ from the wing slopes lands $\theta_0$ close enough that liquid smiles converge in a single pass.
5. **Converter conditioning.** The reference inverse of Appendix D uses the cancellation-free denominator of Remark 1; it still rejects the singular stratum, because no rearrangement can select a missing belly curvature.

## Appendix C. Traceability

A word on what these anchors prove, so they are not over-read. The benchmark-fit tests exercise an already tail-clean target, so the "enforcement" rows lock that clean fits are untouched and that the penalty rows and their Jacobians are correct when active — they do not demonstrate that an adversarial fit ends feasible. The recovery test whose name says "machine precision" asserts parameter agreement at $\sim10^{-4}$ relative and curve agreement at $\sim10^{-6}$; the freshly generated example reaches machine precision, but the lock is looser than its name. A finite diagnostic grid is not a global proof.

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 7 — Claims in this note and the code/tests that lock them.**

| Claim | Object | Code anchor; *test anchors* |
|---|---|---|
| Wing slopes are $b(1\mp\rho)$; tail limit of $g$ is $(4-\beta^2)/16$ | Proposition 1, Proposition 2 | `models/svi_jw/svi.py::RawSVI.wing_slopes`; `backtest/dispatch.py::_analytic_butterfly` |
| JW→raw conversion exact on the benchmark | section "Trader coordinates that split tail from belly" | `models/svi_jw/svi.py::jw_to_raw`; *`test_lqd_pricing.py::test_jw_conversion_matches_note`* |
| Regular inverse domain; $\psi=0$ non-identification; invalid-input behaviour | Theorem 1, Remark 1 | `models/svi_jw/svi.py`; *`test_svi_domain.py::test_regular_domain_round_trips`*; *`::test_psi_zero_stratum_not_identified`*; *`::test_invalid_inputs_fail_loudly_not_plausibly`* |
| Cheap screens do not certify butterfly freedom (Axel Vogt slice) | section "The belly escapes" | `models/svi_jw/calibrate.py::_penalties`; *`test_svi_domain.py::test_core_screens_do_not_certify_butterfly_freedom`* |
| Noise-free benchmark recovery (params $\sim10^{-4}$ rel, curve $\sim10^{-6}$) | section "Worked example: a laboratory round trip" | `models/svi_jw/calibrate.py`; *`test_svi_calibrate.py::test_recovers_benchmark_parameters`*; *`::test_curve_reproduced_to_machine_precision`* (name predates the looser lock) |
| Clean fits untouched by the fences (benchmark is tail-clean) | Proposition 3 | `models/svi_jw/calibrate.py::_penalties`; *`test_svi_calibrate.py::test_respects_lee_wing_bound`*; *`::test_min_variance_non_negative`* |
| Analytic Jacobian matches FD, penalty rows active or not; row parity on both charts | subsection "The analytic Jacobian, in four layers" | `models/svi_jw/jacobian.py`; *`test_svi_jacobian.py::test_mid_fit_admissible`*; *`::test_lee_penalty_active`*; *`::test_min_variance_penalty_active`*; *`test_svi_structural_jacobian.py`* |
| Structural chart: lift, exact recovery, inert fences; benchmark verdict | section "Fitting the slice: fit the belly, fence the tails" | `models/svi_jw/structural.py`; *`test_svi_structural_chart.py`*; `backtest/FINDINGS_svi_chart.md` |
| Adversarial battery on both charts; deterministic $<3$-quote refusal | section "Fitting the slice: fit the belly, fence the tails" | `models/svi_jw/calibrate.py`; *`test_svi_adversarial.py`*; certification case `svi_adversarial_inputs` |
| Guarded inverse and desk-unit ticket | Theorem 1 | `models/svi_jw/svi.py::jw_to_raw_checked`, `models/svi_jw/desk.py`; *`test_svi_desk_and_guards.py`* |
| Calendar hinge rows correct; off is byte-identical | section "Fitting the slice: fit the belly, fence the tails" | `models/svi_jw/calibrate.py`; *`test_svi_jacobian.py::test_calendar_floor_active`*; *`test_overlay_calendar.py::test_svi_no_floor_is_byte_identical`* |
| Prior blocks reach the SVI overlay | section "Fitting the slice: fit the belly, fence the tails" | `models/svi_jw/calibrate.py`; *`test_prior_parametric.py::test_operator_prior_pulls_all_models_toward_prior_skew`* |

## Appendix D. Reference implementation: the two maps

The raw slice evaluates in one line, $w(k)=a+b(\rho(k-m)+\sqrt{(k-m)^2+s^2})$; the maps below read the handles off it and invert them. The original note prints an executable Python listing here (`figures/svi_moments_reference.py`), imported and executed by the figure generator `figures/gen_svi_moments.py`, which compares the checked inverse against production `jw_to_raw` on three regular-domain points to relative tolerance $2\times10^{-12}$ before any figure is written — so the code printed in the note is the code that produced its numbers. The inverse uses the cancellation-free denominator of Remark 1; the reverse map is exactly the functional definition, equation (13). Per the transfer policy of this pack, the listing is replaced by the following complete algorithm specification; it carries every algorithmic detail of the code.

**Algorithm D.1 (forward map, raw → JW).** Reads the five jump-wing functionals off a raw slice, splitting the smile into its two *tail* handles $p,c$ (normalized asymptotic wing slopes) and its three *belly* handles $v,\psi,\widetilde v$ (ATM level, ATM slope of total volatility, and the floor).

*Inputs:* a raw slice $(a,b,\rho,m,s)$ and a variance clock $\tau>0$.
*Outputs:* the five handles $(v,\psi,p,c,\widetilde v)$.

1. Compute the ATM total variance $w_0=w(0)=a+b\left(-\rho m+\sqrt{m^2+s^2}\right)$, the ATM core radius $r_0=\sqrt{m^2+s^2}$, and $\sqrt{w_0}$.
2. Return
$$
v=\frac{w_0}{\tau},\qquad
\psi=\frac{b\left(\rho-m/r_0\right)}{2\sqrt{w_0}},\qquad
p=\frac{b(1-\rho)}{\sqrt{w_0}},\qquad
c=\frac{b(1+\rho)}{\sqrt{w_0}},\qquad
\widetilde v=\frac{a+bs\sqrt{1-\rho^2}}{\tau}.
$$
This is exactly equation (13), with no domain checks: it is pure evaluation.

**Algorithm D.2 (domain-guarded regular inverse, JW → raw, cancellation-resistant).** The two tail handles fix the scale $b$ and tilt $\rho$; the ATM slope fixes the normalized displacement $\chi$; the belly gap $v-\widetilde v$ then sets the width $s$. The denominator $D$ vanishes quadratically as $\psi\to0$ (the belly blind spot), so it is evaluated in a form free of the catastrophic cancellation of the textbook expression.

*Inputs:* a JW point $(v,\psi,p,c,\widetilde v)$ and a clock $\tau>0$.
*Outputs:* the unique regular raw slice $(a,b,\rho,m,s)$, or a domain error.

1. **Domain guard.** Verify that $\tau>0$, $v>0$, $p>0$, $c>0$, $-p/2<\psi<c/2$, $\psi\ne0$, and $\widetilde v<v$ — the exact regular domain of equation (20), with $\psi\ne0$ and $\widetilde v<v$ together rejecting the singular stratum explicitly. If any condition fails, raise a domain error ("JW point is outside the regular inverse domain"); the guarded production converter `jw_to_raw_checked` raises a structured `JWDomainError` carrying a machine-readable reason code for each violated inequality.
2. Set $w_0=v\tau$.
3. Tails to scale and tilt: $b=\tfrac12\sqrt{w_0}\,(p+c)$, $\rho=(c-p)/(c+p)$, per equation (15).
4. ATM slope to normalized displacement: $\chi=\rho-4\psi/(p+c)$, per equation (16).
5. Compute $q_\rho=\sqrt{1-\rho^2}$ and $q_\chi=\sqrt{1-\chi^2}$.
6. **Stable denominator.** The textbook form is $D=(1-\rho\chi)/q_\chi-q_\rho$, equation (17); rearranged so no two large near-equal numbers are subtracted, compute $\delta q=\dfrac{(\chi-\rho)(\chi+\rho)}{q_\rho+q_\chi}$ (algebraically equal to $q_\rho-q_\chi$) and then
$$
D=\frac{(\rho-\chi)^2+\delta q^{\,2}}{2q_\chi},
$$
which is algebraically identical to the textbook expression and numerically stable.
7. Width from the belly gap: $s=\dfrac{w_0-\widetilde v\tau}{bD}$.
8. Displacement and level: $m=\chi s/q_\chi$, $a=\widetilde v\tau-bs\,q_\rho$, per equation (18).
9. Return $(a,b,\rho,m,s)$; production stores the width in the field named `sigma`.

*Verification contract:* the figure generator executes both algorithms against the production converter on three regular-domain points and requires agreement to relative tolerance $2\times10^{-12}$ before drawing a single figure — so the maps specified here are the maps that produced this note's numbers.

## References

- [Gatheral2004] J. Gatheral. *A parsimonious arbitrage-free implied volatility parameterization with application to the valuation of volatility derivatives.* Presentation, Global Derivatives, Madrid, 2004.
- [GatheralJacquier2014] J. Gatheral and A. Jacquier. *Arbitrage-free SVI volatility surfaces.* Quantitative Finance, 14(1):59–71, 2014.
- [Lee2004] R. W. Lee. *The moment formula for implied volatility at extreme strikes.* Mathematical Finance, 14(3):469–480, 2004.
- [Durrleman2010] V. Durrleman. *From implied to spot volatilities.* Finance and Stochastics, 14(2):157–177, 2010.
- [MartiniMingone2022] C. Martini and A. Mingone. *No arbitrage SVI.* SIAM Journal on Financial Mathematics, 13(1):227–261, 2022.





