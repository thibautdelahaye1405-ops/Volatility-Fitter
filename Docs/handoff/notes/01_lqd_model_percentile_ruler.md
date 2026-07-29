# From Ranks to Smiles

**Note 01 — LQD model · lecture edition ("From ranks to smiles: LQD as a monotone transport and pricing engine") · converted from 01_lqd_model_percentile_ruler.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** For one expiry, a volatility smile is the price-screen image of a probability law. This note builds that law from a single logistic draw and an increasing *rubber ruler*. The ruler says how fast successive probability ranks travel through log-return space. Its speed is positive by construction, a scalar translation makes the normalized asset a martingale, and one endpoint inequality is the exact price of having a finite forward. From there, option pricing becomes the difference of two tail ledgers. The same upper-share ledger also supplies the analytic calibration Jacobian and the natural cross-expiry convex-order test.
>
> This transport view is mathematically identical to the production LQD family, but it does not use the customary log-quantile-density formula as its narrative spine. We derive the density, the no-butterfly result, the moment strip, Lee wing slopes, exact ATM level/skew/curvature identities, calibration controls, and calendar ordering from the transport itself. The worked cases include an exact constant-speed unit check, a production SPX-like fit with 1.341 volatility-basis-point maximum error, an event distribution with two landing zones, and an analytic-versus-finite-difference Jacobian audit. The aim is a lecture that a quant can prove and a trader can use: few symbols, explicit trade tickets, and a sharp distinction between structural guarantees and numerical controls.

**Contents.** 1. One random number, one expiry — 2. The centering trade and the right-tail credit limit — 3. A call is two tail ledgers — 4. The constant-speed audit — 5. The ATM microscope — 6. The part of the smile no quote sees — 7. Put the quote screen back in — 8. How to move level without wrecking shape — 9. The root that disappears — 10. When probability chooses two landing zones — 11. Stacking expiry engines — 12. The honest contract — Appendix A. Numerical construction and exact ATM algebra — Appendix B. Production dictionary, controls, and traceability — Appendix C. Performance notes and failure modes — Appendix D. Compact reference implementation — References.

---

## 1. One random number, one expiry

Forget the volatility screen for a moment. Imagine a lottery drum containing all ranks from zero to one. We draw one rank $p$, turn it into a real-valued score, and then decide where that score lands on the log-return axis. If the landing map is increasing, ranks never cross. That innocent observation is the whole architectural idea behind LQD.

Fix an expiry $T$. Let $F_T$ be its forward price and $D_T$ its discount factor. Expectations are under the $T$-forward pricing measure, with deterministic proportional carry. Normalize:

$$
Y=\frac{S_T}{F_T},\qquad X=\log Y,\qquad
k=\log\frac{K}{F_T},\qquad \mathbb{E}[Y]=1 .
\tag{1}
$$

The undiscounted call in forward units is

$$
c(k)=\frac{C^\$(F_Te^k,T)}{D_TF_T}
    =\mathbb{E}\!\left[(Y-e^k)^+\right].
\tag{2}
$$

Actual dollars return by multiplying by $D_TF_T$. Until then, the forward is one and the strike is $e^k$.

### 1.1 The seed

Let $Z$ have the standard logistic distribution

$$
\Lambda(z)=\frac{1}{1+e^{-z}},\qquad
\rho(z)=\Lambda(z)\bigl(1-\Lambda(z)\bigr).
\tag{3}
$$

Then $P=\Lambda(Z)$ is uniform on $(0,1)$ and $Z=\log(P/(1-P))$. The score $z$ is just log odds: zero is the median, $\log 9$ is the 90th percentile, and $-\log 9$ is the 10th.

Why start here? The logistic coordinate sends both troublesome percentile endpoints to ordinary infinities. More importantly, its density has clean tails:

$$
\rho(z)\sim e^z\quad(z\to-\infty),\qquad
\rho(z)\sim e^{-z}\quad(z\to+\infty).
\tag{4}
$$

Those two exponentials will later turn the model's endpoint speeds directly into moment limits.

> **Heuristic.** Think of $Z$ as a standardized rank, not as a return. The model does not ask whether a move of one score unit is large. It chooses how much log-return distance one score unit should cover at each percentile.

### 1.2 The speedometer

Choose a smooth log-speed profile $h$ on $[0,1]$ and set

$$
v(z)=\exp\!\bigl(h(\Lambda(z))\bigr).
\tag{5}
$$

The exponential is doing serious work: $v(z)>0$ for every finite parameter vector. Integrating the speed gives an anchored ruler

$$
b(z)=\int_0^z v(t)\,\mathrm{d}t.
\tag{6}
$$

Finally translate the ruler by a scalar $m$. The model in this lecture is

**Central equation.**

$$
X=x(Z),\qquad
x(z)=m+\int_0^z
\exp\!\bigl(h(\Lambda(t))\bigr)\,\mathrm{d}t,\qquad
h\in\mathcal P_N[0,1].
\tag{7}
$$

This is the note's one central boxed equation. Everything else is a consequence, a numerical method, or a control.

The polynomial is written in shifted Legendre modes,

$$
h(p)=\sum_{n=0}^{N}d_nP_n(1-2p).
\tag{8}
$$

Legendre polynomials are useful rather than sacred: they span the desired low-degree functions, are well conditioned on $[0,1]$, and let low modes carry broad shape while high modes repair local detail. The construction remains valid with any finite basis of bounded continuous functions having finite endpoint limits. The sharper endpoint expansions used below require the polynomial, or comparable smoothness, assumption. The production dictionary is given in Appendix B, "Production dictionary, controls, and traceability".

> **Invariant.** The model's primitive object is the positive speed $v$. A wider band between two neighbouring ranks means less density there; a narrower band means more density. We do not draw volatility and hope it corresponds to probability. We decide how probability ranks travel through return space.

> **Figure 1 — The percentile ruler in one exact toy (figure not included in this pack).** Left: the logistic score turns percentiles into an unbounded coordinate. Middle: a constant-speed ruler maps that score to log return; the marked forward and 10% log-strike locate the two roots used in pricing. Right: the same law is seen by the desk as an implied-volatility smile. The ATM volatility is exactly 20.0000%, while the $k=0.10$ point is 20.5977%. One random rank has become a complete option slice. *Panel description:* the left panel plots $z=\log(p/(1-p))$ against rank $p$, the S-shaped logit map that sends the endpoints $p=0,1$ to $\mp\infty$; the middle panel plots the affine transport $x(z)=m+sz$ of the constant-speed toy ($s=0.08125025$, $m=-0.01088288$), with markers where $x(z)=0$ (the forward root, at percentile 53.3436%) and where $x(z)=0.10$ (the strike root, at percentile 0.796524); the right panel shows the resulting half-year implied-volatility smile — a gently convex curve pinned at exactly 20.0000% at the money and rising to 20.5977% at $k=0.10$. The takeaway: a single positive speed plus one centering scalar already produces a complete arbitrage-free slice.

---

## 2. The centering trade and the right-tail credit limit

The raw ruler $b$ has an arbitrary origin. Option pricing does not: in forward units the asset must have mean one. Since $Y=e^{m+b(Z)}$, the unique centering shift is

$$
m=-\log\int_{-\infty}^{\infty}e^{b(z)}\rho(z)\,\mathrm{d}z.
\tag{9}
$$

Whenever this integral is finite,

$$
\mathbb{E}[e^X]
=e^m\int_{-\infty}^{\infty}e^{b(z)}\rho(z)\,\mathrm{d}z=1.
\tag{10}
$$

The shift changes location, not shape: $x'(z)=v(z)$ before and after normalization.

### 2.1 One hard inequality

The two endpoint speeds are

$$
\lambda_-=e^{h(0)},\qquad \lambda_+=e^{h(1)}.
\tag{11}
$$

Because $h$ is a polynomial and $\Lambda(z)=O(e^z)$ on the left while $1-\Lambda(z)=O(e^{-z})$ on the right,

$$
b(z)=\lambda_-z+\delta_-+O(e^z),
\qquad z\to-\infty,
\tag{12}
$$

$$
b(z)=\lambda_+z+\delta_++O(e^{-z}),
\qquad z\to+\infty,
\tag{13}
$$

for finite constants $\delta_\pm$. Combining these expressions with equation (4), the integrand in equation (9) behaves as

$$
e^{b(z)}\rho(z)\sim
\begin{cases}
C_-e^{(1+\lambda_-)z},&z\to-\infty,\\
C_+e^{-(1-\lambda_+)z},&z\to+\infty.
\end{cases}
\tag{14}
$$

The left tail always integrates because $\lambda_->0$. The right tail integrates exactly when $\lambda_+<1$.

**Proposition 1 (Finite-forward criterion).** The construction in equation (7) admits a finite martingale shift if and only if

$$
\lambda_+<1.
\tag{15}
$$

At $\lambda_+=1$ the normalizer diverges; this is a hard boundary, not a calibration preference.

*Proof.* Equation (14) makes the left integral finite for every positive $\lambda_-$. The right integral is comparable to $\int^\infty e^{-(1-\lambda_+)z}\,\mathrm{d}z$, which is finite precisely for $\lambda_+<1$. Equation (9) then gives the unique finite translation. ∎

> **Caution.** Approaching the wall is legal but expensive. As $\lambda_+\uparrow1$, far right states carry more and more of the mean. The normalizer, tail quadrature, price evaluation, and parameter sensitivities become numerically ill conditioned before the mathematical boundary is reached. Production therefore adds a soft turn ahead of the hard wall, and — in the shipped optimization coordinate, which passes $\lambda_+$ through a logistic — sends the wall itself to infinity, so no trial can reach it at all; the soft turn stays on as a price on near-infinite forwards. In the raw coordinates a numerical safety buffer rejects $\lambda_+\ge1-10^{-6}$. Neither control changes the mathematical boundary at one.

### 2.2 The density falls out of the ruler

Since $x'(z)=v(z)>0$ and $x(z)\to\pm\infty$, the map $x$ is an increasing bijection. Therefore

$$
F_X(x(z))=\Lambda(z),\qquad
f_X(x(z))=\frac{\rho(z)}{v(z)}>0.
\tag{16}
$$

For the normalized asset,

$$
f_Y(e^{x(z)})
=\frac{\rho(z)}{e^{x(z)}v(z)}>0.
\tag{17}
$$

Let $\widetilde c(y)=\mathbb{E}[(Y-y)^+]$ for a strike $y>0$. Differentiation in strike gives

$$
\widetilde c'(y)=-\mathbb{P}(Y>y),\qquad
\widetilde c''(y)=f_Y(y)\ge0.
\tag{18}
$$

So the slice is decreasing and convex in *strike*. Convexity is not asserted in log-strike $k$, where a change of variable contributes extra terms.

**Proposition 2 (One-expiry static arbitrage).** If $h$ is finite and $\lambda_+<1$, the normalized call curve has the correct boundaries, obeys put–call parity, and is strictly convex at every positive strike. In particular, every continuous butterfly spread has non-negative value.

*Proof.* The construction gives $Y>0$ and $\mathbb{E}[Y]=1$. Thus $\widetilde c(0)=1$, $\widetilde c(y)\to0$ as $y\to\infty$, and $(1-y)^+\le\widetilde c(y)\le1$. Equation (18) supplies monotonicity and convexity. Applying the same law to puts yields $\widetilde c(y)-\widetilde p(y)=1-y$. ∎

> **Figure 2 — Butterfly freedom is visible in price space (figure not included in this pack).** The left panel places the call above intrinsic value and below every secant chord required by convexity. The right panel recovers the continuous asset density and compares it with discrete butterfly estimates. In this audit the minimum recovered density over the sampled window is 0.224428, and the maximum relative discretization discrepancy on that grid is 0.0182%. *Panel description:* the left panel draws the normalized call curve $\widetilde c(y)$ against strike, sandwiched between its intrinsic floor $(1-y)^+$ and a fan of secant chords, the picture-proof of convexity; the right panel overlays the continuous density $f_Y$ from equation (17) with centred-difference butterfly quotients computed from the same call curve on a discrete strike grid. The two agree to 0.0182% at worst, and the smallest recovered density value 0.224428 stays strictly positive across the sampled window — the discrete market-facing test confirms what the transport guarantees structurally.

---

## 3. A call is two tail ledgers

The probability law is now complete, but a trader wants a price. Define the upper asset-share ledger

$$
G(z)=\int_z^\infty e^{x(t)}\rho(t)\,\mathrm{d}t.
\tag{19}
$$

It records how much of the mean-one asset is carried by states whose logistic score exceeds $z$. It starts at one, ends at zero, and satisfies

$$
G'(z)=-e^{x(z)}\rho(z).
\tag{20}
$$

For a log-strike $k$, let $z_k$ be the unique root

$$
x(z_k)=k,\qquad p_k=\Lambda(z_k).
\tag{21}
$$

Splitting the payoff gives

$$
c(k)
=\int_{z_k}^{\infty}
  \bigl(e^{x(z)}-e^k\bigr)\rho(z)\,\mathrm{d}z
=G(z_k)-e^k\bigl(1-p_k\bigr).
\tag{22}
$$

This formula has a desk interpretation:

- $G(z_k)$ is the asset delivered in exercised states;
- $e^k(1-p_k)$ is the strike bill paid in those states.

The call is the asset tail minus the cash tail. No volatility interpolation is involved.

### 3.1 A complete trade ticket

> **Example — A six-month call at $k=0.10$.** Take the constant-speed model calibrated to exactly 20.0000% ATM volatility at active variance time $\tau=0.50$. Its speed is $s=0.08125025$ and its martingale shift is $m=-0.01088288$. At $k=0.10$, the exercise percentile is $p_k=0.796524$ and the normalized strike is $e^k=1.105171$. The asset ledger is $G(z_k)=0.24722094$; the cash ledger is $e^k(1-p_k)=0.22487593$. Their difference is
> $$
> c(0.10)
> =0.24722094-0.22487593
> =0.02234501
> =2.2345\%\ \text{of forward}.
> $$
> Black inversion reports 20.5977%. The price is primary; the volatility is its market label.

The put ledger is obtained from the lower tail, but it need not be computed separately. Writing its price as $c_{\mathrm{put}}(k)$, mean-one normalization gives

$$
c(k)-c_{\mathrm{put}}(k)=1-e^k.
\tag{23}
$$

It also supplies a useful implementation test: price calls from the upper tail, recover puts by parity, and verify that a direct lower-tail calculation agrees.

### 3.2 Digital and density from the same root

The root motion cancels when differentiating the payoff integral, because the payoff is zero at the exercise boundary. Consequently

$$
c'(k)=-e^k(1-p_k),
\tag{24}
$$

and one more derivative gives

$$
c''(k)
=-e^k(1-p_k)+
e^k\frac{\rho(z_k)}{v(z_k)}.
\tag{25}
$$

The combination

$$
e^{-k}\bigl(c''(k)-c'(k)\bigr)
=\frac{\rho(z_k)}{v(z_k)}
=f_X(k)
\tag{26}
$$

recovers the log-return density. In strike coordinates this is the Breeden–Litzenberger identity [breedenlitzenberger]; in the transport coordinate it is one division.

> **Heuristic.** The function $G$ will recur twice. In section "The root that disappears", its parameter derivatives give the calibration Jacobian without differentiating $z_k$. In section "Stacking expiry engines", $G$ becomes the integrated-quantile curve that orders expiries. Pricing, differentiation, and calendars are three uses of the same ledger.

---

## 4. The constant-speed audit

Before trusting a flexible model, make it solve a case that fits on one page. Set

$$
h(p)=\log s,\qquad 0<s<1.
\tag{27}
$$

Then $v(z)=s$, $b(z)=sz$, and the logistic moment-generating function gives

$$
\mathbb{E}[e^{sZ}]=\frac{\pi s}{\sin(\pi s)}.
\tag{28}
$$

The martingale shift and transport are therefore

$$
m=-\log\frac{\pi s}{\sin(\pi s)},\qquad x(z)=m+sz.
\tag{29}
$$

The condition $s<1$ is simultaneously the domain of the moment in equation (28) and the hard right-tail condition (15).

> **Example — An exact 20% ATM unit check.** Solving the one-dimensional equation
> $$
> 2\Phi\!\left(\frac{0.20\sqrt{0.50}}{2}\right)-1
> =c(0;s)
> $$
> gives $s=0.08125025$. Equation (29) then gives $m=-0.01088288$, and the forward lies at percentile 53.3436%, not at the median. The latter is not a bug: martingale centering occurs in *price*, so the log return usually has a negative location shift.
>
> | Quantity | Production value |
> |---|---|
> | Solved scale | 0.08125025 |
> | Martingale shift | -0.01088288 |
> | ATM percentile | 53.3436% |
> | $C(0.10)$ | 0.02234501 |
> | $\sigma_{\mathrm{BS}}(0.10)$ | 20.5977% |

The constant-speed law is not a flat Black smile. It is a log-logistic distribution rescaled to mean one, so its wing moments are finite only over a strip. Its purpose is more valuable than realism: every integration, root-finding, normalization, price, and implied-vol inversion path can be checked against a transparent one-parameter model.

---

## 5. The ATM microscope

At the money, three distributional facts replace a neighbourhood of finite differences. Let $z_*$ solve $x(z_*)=0$ and define

$$
p_*=\Lambda(z_*),\qquad
f_*=\frac{\rho(z_*)}{v(z_*)}=f_X(0).
\tag{30}
$$

Equations (22)–(25) give

$$
c_0=G(z_*)-(1-p_*),\qquad
c'_0=-(1-p_*),\qquad
c''_0=f_*-(1-p_*).
\tag{31}
$$

The ATM price sets level, the exercise percentile sets the digital, and the local compression of the ruler sets density.

### 5.1 Pass those facts through Black

Let $B(k,w)$ denote the normalized Black call with total variance $w$, and let $w(k)$ solve

$$
B(k,w(k))=c(k).
\tag{32}
$$

At $k=0$, put

$$
a=\Phi^{-1}\!\left(\frac{1+c_0}{2}\right),\qquad
w_0=4a^2,\qquad n=\varphi(a),\qquad
\Delta=p_*-\Phi(a).
\tag{33}
$$

Implicit differentiation produces unusually compact identities:

$$
w'_0=\frac{2\sqrt{w_0}}{n}\,\Delta,
\tag{34}
$$

$$
w''_0=\frac{2\sqrt{w_0}}{n}\,f_*
       -2+
       \left(\frac{1}{2w_0}+\frac18\right)(w'_0)^2.
\tag{35}
$$

The derivation is recorded in Appendix A, "Numerical construction and exact ATM algebra"; the interpretation belongs here. Total-variance skew is exactly a *digital mismatch*: $p_*$ is the model percentile of the forward, while $\Phi(a)$ is the corresponding percentile under the flat-Black law with the same ATM option price. Curvature adds the local-density mismatch and a necessary nonlinear skew correction.

If $\tau$ is the active variance time and $\sigma(k)=\sqrt{w(k)/\tau}$, then

$$
\sigma_0=\sqrt{\frac{w_0}{\tau}},
\tag{36}
$$

$$
\sigma'_0=\frac{\Delta}{n\sqrt{\tau}},
\tag{37}
$$

$$
\sigma''_0=\frac{1}{\sqrt{\tau}}
\left[
\frac{f_*}{n}-\frac{1}{\sqrt{w_0}}
+\frac{\sqrt{w_0}}{4}\left(\frac{\Delta}{n}\right)^2
\right].
\tag{38}
$$

These are exact identities for the continuous slice. They are semi-analytic, not elementary coefficient formulas: $z_*$ and $c_0$ still come from monotone inversion and quadrature.

**Proposition 3 (ATM information content).** Once the martingale law is built, ATM level, log-strike skew, and log-strike curvature depend only on $(c_0,p_*,f_*)$ and the variance clock $\tau$. No neighbouring implied-volatility quotes are required.

*Proof.* At ATM, $B(0,w)=2\Phi(\sqrt w/2)-1$, which gives equation (33). The Black partial $B_w(0,w)=\varphi(\sqrt w/2)/(2\sqrt w)$ together with equation (31) yields equation (34). Differentiating $B(k,w(k))=c(k)$ twice and simplifying the ATM Black partials gives equation (35). The chain rule for $\sigma=\sqrt{w/\tau}$ gives equations (36)–(38). ∎

> **Example — The digital explains skew before any regression does.** Suppose the model forward percentile $p_*$ lies below the matched-Black percentile $\Phi(a)$. Then $\Delta<0$, so equation (37) says the implied-volatility skew is negative. The statement does not rely on a three-point slope, a fitted parabola, or a small bump size. It is an exact comparison of two digitals.

---

## 6. The part of the smile no quote sees

Liquid quotes constrain the body. Extrapolation is governed by what the ruler does as ranks approach zero and one. From equations (12)–(13),

$$
\mathbb{P}(X>x)\sim K_+e^{-x/\lambda_+},\qquad
\mathbb{P}(X<x)\sim K_-e^{x/\lambda_-},
\tag{39}
$$

for positive constants $K_\pm$. Equivalently, $Y=e^X$ has power tails:

$$
\mathbb{P}(Y>y)\sim K_+y^{-1/\lambda_+},\qquad
\mathbb{P}(Y<y)\sim K_-y^{1/\lambda_-}.
\tag{40}
$$

### 6.1 Moment budget

The same endpoint comparison gives the complete moment strip

$$
\mathbb{E}[e^{rX}]<\infty
\quad\Longleftrightarrow\quad
-\frac{1}{\lambda_-}<r<\frac{1}{\lambda_+}.
\tag{41}
$$

For the asset $Y$, the critical Lee moments are

$$
\pi_+=\frac{1}{\lambda_+}-1,\qquad
\pi_-=\frac{1}{\lambda_-}.
\tag{42}
$$

The first says how many moments beyond the forward survive on the right; the second says how many inverse moments survive on the left.

Lee's moment formula [lee] uses the map

$$
\Psi(q)=2-4\left(\sqrt{q^2+q}-q\right).
\tag{43}
$$

For total implied variance, the wing limsups are

$$
\limsup_{k\to\infty}\frac{w(k)}{k}=\Psi(\pi_+),\qquad
\limsup_{k\to-\infty}\frac{w(k)}{|k|}=\Psi(\pi_-).
\tag{44}
$$

Substituting equation (42) yields direct speed-to-slope formulas:

$$
\beta_+
=\frac{2\lambda_+}
        {\bigl(1+\sqrt{1-\lambda_+}\bigr)^2},
\qquad 0<\lambda_+<1,
\tag{45}
$$

$$
\beta_-
=\frac{2\lambda_-}
        {\bigl(1+\sqrt{1+\lambda_-}\bigr)^2},
\qquad \lambda_->0.
\tag{46}
$$

For small endpoint speeds, $\beta_\pm\sim\lambda_\pm/2$. As the right speed approaches the hard wall, $\beta_+\to2$.

> **Caution.** Lee's theorem itself gives the limsup statement (44). The polynomial endpoint expansion here produces regular power tails, so regular-variation tail–wing refinements [benaimfriz] upgrade the wing rates to ordinary limits. When only Lee's moment result is being invoked, the careful word is *limsup*.

> **Figure 3 — The endpoint is an extrapolation forecast (figure not included in this pack).** Left: the speed profile settles to two endpoint values. Centre: those values are inverse moment budgets through equation (42). Right: the moment budgets map to Lee total-variance slopes. The marked production fit has $(\lambda_-,\lambda_+)=(0.157473, 0.037786)$ and $(\beta_-,\beta_+)=(0.073087, 0.019259)$. *Panel description:* the left panel plots the fitted log-speed profile $e^{h(p)}$ across percentile $p$, flattening toward its two endpoint limits $\lambda_-=0.157473$ at $p=0$ and $\lambda_+=0.037786$ at $p=1$; the centre panel converts each endpoint speed into its critical moment budget — $\pi_-=1/\lambda_-$ inverse moments on the left, $\pi_+=1/\lambda_+-1$ extra forward moments on the right, the latter collapsing to zero as $\lambda_+\to1$; the right panel passes those budgets through Lee's map, producing the total-variance wing slopes with the marked fit at $\beta_-=0.073087$ and $\beta_+=0.019259$, far below the model-free ceiling of 2. The chain speed → moment → slope is monotone in each link, which is why the endpoints deserve direct inspection.

> **Example — The right endpoint has a balance-sheet meaning.** For the SPX-like fit in section "Put the quote screen back in", the right speed is $\lambda_+=0.037786$. Hence the model retains moments $\mathbb{E}[Y^{1+q}]$ for $q<1/0.037786-1$ and predicts a right-wing Lee slope of 0.019259. Moving a high-order coefficient can leave quoted strikes nearly unchanged yet alter $h(1)$, the critical moment boundary, and the far wing. A small in-window residual is therefore not an extrapolation diagnostic.

---

## 7. Put the quote screen back in

Only now do we return to market quotes. The model provides arbitrage-safe prices; Black inversion merely expresses those prices in familiar units. For total variance $w$, the normalized Black call is

$$
B(k,w)=\Phi(d_+)-e^k\Phi(d_-),\qquad
d_\pm=-\frac{k}{\sqrt w}\pm\frac{\sqrt w}{2}.
\tag{47}
$$

At quote $i$, target price $B(k_i,w_i^{\mathrm{mkt}})$ is compared with model price $c(k_i;\theta)$. A useful core residual is

$$
r_i(\theta)=
\omega_i^{1/2}
\frac{c(k_i;\theta)-B(k_i,w_i^{\mathrm{mkt}})}
     {\mathrm{Vega}_i+\eta}.
\tag{48}
$$

Here $\eta>0$ prevents tiny far-wing vegas from acquiring absurd weight. With normalized Black vega $\mathrm{Vega}_i=\varphi(d_{+,i})\sqrt{\tau}$, $r_i$ is approximately an implied-volatility error.

### 7.1 What the objective is allowed to prefer

The residual stack adds controls, each with a distinct economic meaning:

- bid–ask bands can replace point targets with zero hinge cost inside the spread, while retaining a gentle midpoint anchor;
- a ridge on modes $n\ge4$ discourages oscillatory speed profiles that sparse quotes cannot identify;
- a one-sided soft barrier prices, rather than prevents, a near-infinite forward (in the shipped coordinate the wall is unreachable anyway);
- optional priors stabilize weakly identified tails or preserve continuity with the previous fit;
- optional calendar rows penalize adjacent-expiry order violations, read at fixed strikes over the common quote support (Theorem 2 says what they protect; the discussion following it says why the rows live in price space rather than the ledger);
- an optional log-contract row expresses a var-swap view (and rides the analytic derivative pass); optional ATM/RR/BF operator rows express desk views.

The hard martingale wall remains hard. Every other row is a weighted modelling choice and should be reported as such.

> **Performance.** Production prices in the native coordinate. It tabulates $x(z)$ and $G(z)$ once, solves all strike roots monotonically, and evaluates each call from equation (22). This is faster and numerically calmer than integrating each payoff from scratch.

### 7.2 A deterministic SPX-like approximation case

The first stress case uses a smooth skewed target sampled at 24 strikes and fits an order-9 LQD slice with the production calibrator. It is a capacity and implementation test, not a claim about a live market or a trading signal.

> **Figure 4 — A quote screen, its residual ledger, and the law underneath (figure not included in this pack).** Left: the order-9 production fit overlays the deterministic SPX-like target. Centre: all residuals remain inside a narrow volatility-basis-point band; maximum and RMS errors are 1.341 and 0.408 bp. Right: the fitted return density is compared with an ATM-matched normal, making the downside allocation of probability visible. *Panel description:* the left panel shows the fitted implied-volatility curve running through all 24 target quotes of the skewed SPX-like smile, indistinguishable from the target at plot scale; the centre panel plots the per-quote fit residuals in volatility basis points, all inside a band bounded by the maximum error 1.341 bp with RMS 0.408 bp; the right panel overlays the fitted log-return density on a normal density matched to the same ATM level — the fitted law shifts probability into the left tail, which is exactly the distributional counterpart of the negative skew $-0.177846$ on the quote screen.

> **Example — Read the fit in three coordinate systems.** The optimizer terminates in 8 function evaluations. The quote screen reports ATM volatility 21.7961%, skew $-0.177846$, and curvature 0.002673. The distribution reports endpoint speeds $(0.157473, 0.037786)$ and martingale error $-1.11\times10^{-16}$. The terminal log contract reports a log-contract-implied volatility of 22.9685%. None of these views replaces the others: quotes measure fit, endpoint speeds measure extrapolation, and the density shows where probability actually landed.

---

## 8. How to move level without wrecking shape

Raw polynomial coefficients are efficient calibration coordinates and poor conversation. A trader asks for more level with skew unchanged, not for a bump to the fourth Legendre coefficient. Let

$$
H(\theta)=
\begin{pmatrix}
w_0(\theta)\\
\sigma'_0(\theta)\\
\sigma''_0(\theta)
\end{pmatrix},
\qquad
D=\frac{\partial H}{\partial\theta}.
\tag{49}
$$

The internal production chart uses $w_0$ in its first coordinate. The screen-facing level is $\sigma_0$, and at fixed $\tau$ the two charts are locally equivalent through $w_0=\tau\sigma_0^2$. At a regular point, $D$ has row rank three. The minimum-norm first-order move that changes handles by $\delta H$ is

$$
\delta\theta_{\mathrm{primary}}
=D^{\mathsf{T}}(DD^{\mathsf{T}})^{-1}\delta H.
\tag{50}
$$

Any vector in $\ker D$ is a first-order shape move: it changes the smile while leaving ATM level, skew, and curvature fixed to first order. Two production refinements deserve a sentence each. "Minimum-norm" is minimum in *some* metric, and the Euclidean coefficient metric — the default — is an admitted convention; a Gauss–Newton metric that prices a move by its effect on the fitted quotes is also available. And the kernel is not left as anonymous coefficient directions: its persistent vocabulary is the market's own — 25- and 10-delta risk reversals and butterflies and the var swap, solved inside $\ker D$ as named package controls with an explicit cross-talk matrix and a kernel-restricted condition print.

**Assumption 1 (Regular handle point).** The parameter vector lies strictly inside $\lambda_+<1$, the ATM option has non-negligible vega, and $D$ has row rank three. Near a rank loss, the pseudoinverse is a warning signal rather than a trading control.

The linear move is local. A finite requested shift can be attempted with Newton retargeting on the exact handles (36)–(38). The current routine is not a globally feasible map: an intermediate iterate can meet the martingale wall, and the solve can fail near a singular chart. This distinction matters: a linear chart is a compass, not a teleport.

> **Figure 5 — What low polynomial modes actually move (figure not included in this pack).** Each panel is one view — log-speed, implied volatility, or return density — and overlays the same three controlled perturbations. Broad modes move level or tilt; higher curvature redistributes probability more locally. The panels explain why coefficient orthogonality is useful but does not make coefficients into trader handles. *Panel description:* the first panel shows the log-speed profile $h(p)$ under three low-mode perturbations — a constant-mode bump shifting the whole profile, a linear-mode bump tilting it, and a quadratic-mode bump bending its centre; the second panel shows the same three perturbations as implied-volatility responses, where the constant mode reads mostly as level, the linear mode mostly as skew tilt, and the quadratic mode as curvature with visible wing side-effects; the third panel shows the return-density responses, where the higher mode redistributes probability locally around the body while the broad modes translate or lean the whole law. Because every Legendre mode reaches both endpoints, each perturbation also moves the endpoint speeds — the visual argument for treating handles, not coefficients, as the trading interface.

> **Example — Primary move versus shape move.** With order $N=9$, there are ten polynomial coefficients but only three ATM handles. Under Assumption 1, the primary subspace has dimension three and the local shape nullspace has dimension seven. A calibration can therefore match the same ATM level, skew, and curvature with materially different wing or density shapes. Quotes and regularization decide which member of that seven-dimensional family is acceptable.

---

## 9. The root that disappears

Calibration speed depends on derivatives. A naive implementation bumps every coefficient, rebuilds the martingale shift, resolves every strike root, and reprices every option. The transport reveals a cleaner route.

Write the profile in any affine coefficient chart,

$$
h_\theta(p)=\sum_j\theta_j\phi_j(p).
\tag{51}
$$

The raw-ruler sensitivity is

$$
r_j(z)=\frac{\partial b(z)}{\partial\theta_j}
=\int_0^z v(t)\phi_j(\Lambda(t))\,\mathrm{d}t.
\tag{52}
$$

Differentiate the mean-one identity. Since $1=\int e^{x(z)}\rho(z)\,\mathrm{d}z$,

$$
\frac{\partial m}{\partial\theta_j}
=-\int_{-\infty}^{\infty}e^{x(t)}r_j(t)\rho(t)\,\mathrm{d}t,
\tag{53}
$$

and hence

$$
x_j(z):=\frac{\partial x(z)}{\partial\theta_j}
=r_j(z)-
\int_{-\infty}^{\infty}e^{x(t)}r_j(t)\rho(t)\,\mathrm{d}t.
\tag{54}
$$

Define the corresponding upper-share sensitivity

$$
G_j(z)=\int_z^\infty e^{x(t)}x_j(t)\rho(t)\,\mathrm{d}t.
\tag{55}
$$

**Theorem 1 (Envelope cancellation).** At fixed log-strike $k$ and an interior admissible parameter vector,

$$
\frac{\partial c(k;\theta)}{\partial\theta_j}=G_j(z_k).
\tag{56}
$$

The derivative of the implicit strike root $z_k$ is not needed.

*Proof.* Differentiate equation (22). Terms involving the moving root combine to

$$
\left[G'(z_k)+e^k\rho(z_k)\right]
\frac{\partial z_k}{\partial\theta_j}.
$$

But equation (20) and $x(z_k)=k$ imply $G'(z_k)=-e^k\rho(z_k)$. The bracket vanishes. The remaining fixed-boundary term is exactly equation (55). ∎

This is an envelope theorem in trading clothes. Moving the exercise boundary has no first-order value because the option payoff is zero at that boundary. The expensive implicit derivative disappears for an economic reason, not an algebraic accident.

> **Figure 6 — The analytic price Jacobian under audit (figure not included in this pack).** Left: the production sensitivities for 10 parameters are compared with central finite differences across strikes. Right: normalized column errors remain below $2.88\times10^{-5}$. The residual discrepancy is the expected finite-grid/interpolation error, not a missing strike-root term. *Panel description:* the left panel overlays, for each of the 10 parameters of the order-9 fit, the analytic price sensitivity $G_j(z_k)$ of equation (56) as a curve across log-strikes, together with central-finite-difference estimates at the same strikes — analytic curves and difference markers coincide at plot scale for every column. The right panel condenses the comparison into normalized per-column error magnitudes, all below $2.88\times10^{-5}$; the surviving discrepancy has the size and strike-profile of interpolation error on the finite logit grid, confirming that no strike-root derivative term is missing from the analytic route.

> **Caution.** The continuous identity is exact under dominated differentiation in an interior neighbourhood. Production tabulates and interpolates $x$ and $G$ separately, so off-grid algebra is not bitwise exact. Sensitivities also grow poorly conditioned near $\lambda_+=1$. Finite-difference audits remain a necessary test even when finite differences are no longer the main algorithm.

---

## 10. When probability chooses two landing zones

Positive density does not mean unimodal density. If the ruler moves slowly in two separated regions, probability ranks bunch into two return zones. This is useful around discrete events and dangerous when caused by overfitting.

To make that distinction visible, the second deterministic case starts from an asymmetric two-component event law. Its left component carries 56.0% weight and is centred at $-0.074804$; the right component is centred at $0.085196$. We sample 37 option quotes and fit the highest supported production order, $N=16$.

> **Figure 7 — An adversarial event case (figure not included in this pack).** Left: the order-16 production slice approximates the event-shaped implied-volatility target with maximum and RMS quote errors 2.444 and 0.999 volatility bp. Right: the recovered density visibly selects two landing zones. The fit tests whether a positive transport family can express bimodality; it does not certify that the second mode is economically real. *Panel description:* the left panel overlays the order-16 fit on the 37 event-shaped quotes — a smile with the tell-tale central structure of a binary event — with the worst quote missed by 2.444 bp and an RMS of 0.999 bp; the right panel shows the fitted log-return density resolving two separated humps, the heavier one (56.0% of the mass) centred near $-0.074804$ and the lighter one near $0.085196$. The density is positive everywhere by construction; whether its second mode is signal or overfit is exactly what the figure cannot decide.

> **Example — Positive is guaranteed; plausible is judged.** The fit has endpoint speeds $(0.015531, 0.014044)$ and martingale error $-2.22\times10^{-16}$. Its density cannot be negative, regardless of order. Yet a second mode may reflect a genuine scheduled jump, sparse quotes, a loose high-order ridge, or stale prices. Static arbitrage supplies a floor for model quality, not a complete economic opinion.

The example also explains why order is a risk control. Raising $N$ expands approximation capacity and creates more ways to hide oscillation between quotes. High order is justified when the data or prior information can identify the extra structure. Otherwise it is merely freedom with a polished residual.

---

## 11. Stacking expiry engines

Each expiry engine is butterfly-free on its own. A surface must also avoid a shorter-dated call being more expensive than a longer-dated call at the same normalized strike. The right object is not the log-return mean or variance; it is convex order for the normalized asset.

Under deterministic proportional carry and a consistent mean-one forward normalization, write for expiry $T$ the percentile map

$$
y_T(p)=
\exp\!\left(
x_T\!\left(\log\frac{p}{1-p}\right)
\right),\qquad 0<p<1,
\tag{57}
$$

and its upper integrated percentile curve

$$
\mathcal G_T(p)=\int_p^1y_T(r)\,\mathrm{d}r.
\tag{58}
$$

The substitution $r=\Lambda(z)$ reveals the promised identity

$$
\mathcal G_T(p)=G_T\!\left(\log\frac{p}{1-p}\right).
\tag{59}
$$

The price ledger is already the calendar ledger.

### 11.1 Why ordering the ledgers orders every call

At normalized strike $y$,

$$
\widetilde c_T(y)
=\sup_{0\le p\le1}
\left\{\mathcal G_T(p)-(1-p)y\right\}.
\tag{60}
$$

A maximizing percentile is associated with the exercise threshold $y_T(p)=y$. Conversely,

$$
\mathcal G_T(p)
=\inf_{y\ge0}
\left\{\widetilde c_T(y)+(1-p)y\right\}.
\tag{61}
$$

These conjugate relations prove the ordering result directly; they are the integrated-quantile form of standard convex order [hardylittlewoodpolya, shakedshanthikumar].

**Theorem 2 (Calendar order in the native ledger).** Let $Y_1$ and $Y_2$ be positive integrable variables with mean one, and for a general law let $y_i(p)$ denote its left-continuous generalized quantile. Then

$$
Y_1\le_{\mathrm{cx}}Y_2
\quad\Longleftrightarrow\quad
\mathcal G_1(p)\le\mathcal G_2(p)
\quad\text{for every }p\in[0,1].
\tag{62}
$$

Equivalently, every normalized call on $Y_1$ is no more expensive than the same-strike call on $Y_2$.

*Proof.* If the integrated percentiles are ordered, taking suprema in equation (60) orders every call. If every call is ordered, taking infima in equation (61) orders every integrated percentile. Equal means supply equality at $p=0$, and both curves vanish at $p=1$. ∎

> **Example — A calendar crossing can hide between strikes.** Suppose two adjacent expiries satisfy $\mathcal G_1(p_j)\le\mathcal G_2(p_j)$ at the quoted exercise percentiles but cross between $p_j$ and $p_{j+1}$. Quote-by-quote checks pass, yet Theorem 2 implies that some unquoted strike has a negative calendar spread. A dense logit grid makes such a crossing harder to miss; only a continuum certificate rules it out mathematically.

The theorem says what to *measure*; production learned, at measured cost, that it is not the thing to *enforce*. The integrated percentile $\mathcal G_T(p)$ sums the whole upper tail, so a hinge that compares two ledgers at any single rank drags both slices' extrapolated wings into the constraint — a fit can be pushed around by strikes nobody quoted, and on an acute short-dated pair the phantom drag from a full-grid ledger floor measured two orders of magnitude above the uncoupled fit. Nor does a denser rank grid help: the leak is in the integral, not the sampling. What removes it is *confinement* — reading the same ordering as finite-weight hinge rows on normalized call prices at fixed strikes over the two slices' common quote support (Note 10 owns the incident and its certification lock). That is what production enforces; the ledger comparison (59) survives as the wing-dense *diagnostic*, exact at every rank precisely because no optimizer is listening to it. Either way this is calendar *control*, not a structural guarantee: finite rows, finite weights, and nothing certified between expiries or across inconsistent forward measures.

One more production sentence completes the picture. The surface is no longer stitched nearest-to-farthest: every expiry is fitted independently, the finished ladder is screened interface by interface, and only a violation-connected group of slices is re-solved *jointly* — so a clean ladder is exactly its independent fits, and a correction lands where the quotes are thinnest rather than wherever the sweep happened to arrive last. The one-way sweep survives as explicit legacy configuration.

### 11.2 The native log contract

Because $P=\Lambda(Z)$ is uniform,

$$
\mathbb{E}[X]=\int_0^1x\!\left(\log\frac{p}{1-p}\right)\mathrm{d}p.
\tag{63}
$$

For a mean-one positive asset, define the terminal log-contract quantity

$$
w_{\log}=-2\mathbb{E}[X].
\tag{64}
$$

This route integrates the constructed law directly. It avoids extrapolating a finite strike grid before evaluating the familiar option-strip replication [gatheral]. The annualized display uses the active variance clock, $\sigma_{\log}=\sqrt{w_{\log}/\tau}$. The identity is exact for the terminal log contract. It equals the fair pathwise realized-variance strike under the usual continuous-path replication assumptions; jumps introduce a correction, and a terminal marginal alone cannot price realized variance.

---

## 12. The honest contract

A good model note should end its sales pitch before the reader has to. The table below separates what follows from the mathematics from what is merely encouraged by a calibration objective.

**Table 1 — What the model promises, controls, and does not claim.**

| Property | Status | Precise statement |
|---|---|---|
| Positive continuous density | Structural | $v>0$ makes $x$ increasing and equation (16) positive. |
| Mean-one normalized asset | Structural, conditional | Exact after equation (9), provided $\lambda_+<1$. |
| One-expiry butterfly freedom | Structural | Calls are convex in normalized strike, not necessarily in log-strike. |
| Tail moments and Lee rates | Structural | Endpoint speeds determine equation (41) and equations (45)–(46). |
| ATM level, skew, curvature | Exact slice identities | Equations (36)–(38); numerical quadrature and root solves are still required. |
| Calendar freedom | Soft in production | Exact if equation (62) holds for all ranks; production enforces at fixed strikes over the common quote support, with finite weights, and reports residual violations in desk units (worst strike, currency, ticks, spread fraction). |
| Display and publish | Gated above this note | A structurally clean slice can still be withheld by the surface-level butterfly certificate (Note 02); that gate is upstream of everything here. |
| Unimodality or economic plausibility | Not guaranteed | Positive density can be oscillatory or multimodal. |
| Atoms and default mass | Not represented directly | A finite smooth speed produces a continuous positive law on $(0,\infty)$. |
| Parameter identification | Not guaranteed | Sparse quotes may leave tail and high-order directions weakly identified. |
| Dynamic arbitrage under stochastic carry | Outside the slice theorem | Marginal normalized convex order is not a full dynamic market model. |

> **Invariant.** The durable mental model is short. Draw a logistic rank. Move it through a positive-speed ruler. Translate the ruler so the asset mean is one. Price a call as an upper asset share minus an upper cash bill. Read extrapolation from the two endpoint speeds. Everything else is implementation, calibration, or governance.

---

## Appendix A. Numerical construction and exact ATM algebra

### A.1 A stable finite grid

Production works on a finite logistic interval $[-z_{\max},z_{\max}]$. On a sorted grid $z_j$, it evaluates

$$
p_j=\Lambda(z_j),\qquad v_j=e^{h(p_j)},
$$

and integrates $v$ outward from the anchor $z=0$ to obtain $b_j$. The martingale integrand and upper-share integrand begin with the same array,

$$
a_j=e^{b_j}\rho(z_j).
$$

The normalizer is $M=\int a(z)\,\mathrm{d}z$, the shift is $m=-\log M$, and the normalized upper share is

$$
G(z)=\frac{\int_z^\infty a(t)\,\mathrm{d}t}{M}.
\tag{65}
$$

Computing numerator and denominator from the unshifted integrand is useful: their potentially large common scale cancels.

The omitted tails are not set to zero. From equations (12)–(13), their leading integrals are exponential and can be added analytically. For example, at a right boundary $z_R$,

$$
\int_{z_R}^\infty e^{b(z)}\rho(z)\,\mathrm{d}z
\approx
\frac{e^{b(z_R)-z_R}}{1-\lambda_+},
\tag{66}
$$

while at a left boundary $z_L<0$,

$$
\int_{-\infty}^{z_L} e^{b(z)}\rho(z)\,\mathrm{d}z
\approx
\frac{e^{b(z_L)+z_L}}{1+\lambda_-}.
\tag{67}
$$

These are the leading production corrections. They become ill conditioned near the hard wall, as they should.

### A.2 Hermite interpolation and root solves

The tabulated $x_j=m+b_j$ is strictly increasing. Production uses piecewise cubic Hermite interpolants supplied with the analytic nodal slopes $x'=v$ and $G'=-e^x\rho$. This gives fourth-order local accuracy, but it is not by itself a Fritsch–Carlson monotonicity guarantee [fritschcarlson]; production therefore runs the Fritsch–Carlson sufficient condition per slice as a cheap vectorized scan — with exact nodal derivatives the derivative-to-secant ratio is $1+O(h^2)$, far inside the sufficient region — which upgrades "increasing at the nodes" to "increasing between them." Strike inversion starts from a monotone linear-table seed and applies a small fixed number of clipped Newton updates.

The finite-grid price is then equation (22). Three routine audits catch most errors:

1. verify $G(-z_{\max})$ plus its left correction is one to tolerance;
2. compare direct lower-tail puts with calls recovered from parity;
3. refine the grid and confirm that prices, densities, and Jacobians converge together.

### A.3 ATM Black derivatives

For completeness, let $s=\sqrt w$ and $d_\pm=-k/s\pm s/2$. At fixed $w$,

$$
B_k=-e^k\Phi(d_-),\qquad
B_w=\frac{\varphi(d_+)}{2s}.
\tag{68}
$$

At $k=0$, with $a=s/2$ and $n=\varphi(a)$,

$$
B_k=\Phi(a)-1,\qquad
B_w=\frac{n}{2s},
\tag{69}
$$

$$
B_{kk}=\frac{n}{s}+\Phi(a)-1,\qquad
B_{kw}=\frac{n}{4s},
\tag{70}
$$

$$
B_{ww}=
-n\left(\frac{1}{16s}+\frac{1}{4s^3}\right).
\tag{71}
$$

Implicit differentiation gives

$$
w'_0=\frac{c'_0-B_k}{B_w},
\tag{72}
$$

$$
w''_0=
\frac{c''_0-B_{kk}-2B_{kw}w'_0-B_{ww}(w'_0)^2}{B_w}.
\tag{73}
$$

Substituting equation (31) and equations (69)–(71) simplifies to equations (34)–(35). The terms linear in $w'_0$ cancel.

### A.4 Two clocks

$T$ labels the expiry and governs discounting and forwards. The quantity $\tau$ annualizes total variance. In the base configuration they coincide as year fractions. With an event clock, $\tau$ includes the scheduled-event dilation used elsewhere in Vol-Fitter. All Black vegas and annualized handles must use the same active $\tau$ that produced the target total variances.

---

## Appendix B. Production dictionary, controls, and traceability

### B.1 How the transport becomes log quantile density

The lecture used $h$ as an ordinary polynomial. To recover the conventional name, define the return quantile at percentile $p$:

$$
Q(p)=x\!\left(\log\frac{p}{1-p}\right).
\tag{74}
$$

Since $\mathrm{d}z/\mathrm{d}p=1/[p(1-p)]$,

$$
Q'(p)=\frac{e^{h(p)}}{p(1-p)},\qquad
\log Q'(p)=h(p)-\log p-\log(1-p).
\tag{75}
$$

This is why the production model is called LQD. In this lecture it is a derived identity, not the starting metaphor.

Write the shifted-Legendre expansion as in equation (8). The production parameterization separates a linear endpoint chord:

$$
h(p)=(1-p)L+pR+\sum_{n=2}^{N}a_nP_n(1-2p).
\tag{76}
$$

The two conventions are exactly equivalent:

$$
d_0=\frac{L+R}{2},\qquad
d_1=\frac{L-R}{2},\qquad
d_n=a_n\quad(n\ge2),
\tag{77}
$$

and $L=d_0+d_1$, $R=d_0-d_1$. Note that $L$ and $R$ are chord coefficients, not by themselves the true endpoint log-speeds. Those are

$$
\log\lambda_-=L+\sum_{n=2}^{N}a_n,
\tag{78}
$$

$$
\log\lambda_+=R+\sum_{n=2}^{N}(-1)^na_n.
\tag{79}
$$

This linear map is more than a footnote: it is exactly what the shipped *optimization* chart inverts. Production offers three coordinate systems over the same family — the raw chord coefficients above, an endpoint chart that takes the true endpoint log-speeds $(\log\lambda_-,\log\lambda_+,a_2,\dots)$ themselves as coordinates so that body curvature cannot mechanically drag the wings, and the shipped default, which additionally passes $\lambda_+$ through a logistic so the martingale wall sits at infinity and the admissible set is the whole of $\mathbb{R}^d$. The fitted optimum is chart-independent to solver tolerance; what changes is which mistakes are structurally impossible.

**Table 2 — Transport notation and production objects.**

| Lecture object | Conventional symbol | Production object |
|---|---|---|
| $p=\Lambda(z)$ | percentile $u$ | `slice.u` |
| $z=\operatorname{logit} p$ | logit coordinate $z$ | `slice.z` |
| $h(p)$ | smooth part $g(u)$ | basis evaluation |
| $v(z)=e^{h(\Lambda(z))}$ | $\mathrm{d}Q/\mathrm{d}z$ | `slice.dq_dz` |
| $b(z)$ | anchored raw quantile | integration workspace |
| $m$ | martingale shift $\mu$ | `slice.mu` |
| $x(z)$ | normalized quantile on $z$ | `slice.q_z` |
| $G(z)$ | upper asset share $A(z)$ | `slice.a_z` |
| $\lambda_-$ | $A_L$ | `a_left` |
| $\lambda_+$ | $A_R$ | `a_right` |

### B.2 Control atlas

**Table 3 — Principal production controls.** Defaults belong to code and configuration; the table records semantics rather than freezing numbers.

| Control | Type | Role |
|---|---|---|
| `order` | integer, $4$–$16$ | Degree $N$ of $h$; raises both capacity and oscillation risk. |
| `z_max`, grid size | numerical | Logistic truncation and resolution for integration, inversion, and interpolation. |
| quote weights, vega floor | objective | Define the price residual metric in equation (48). |
| bid–ask mode | objective | Gives zero hinge cost inside a supplied band while retaining the gentle production midpoint anchor. |
| high-mode ridge | regularizer | Penalizes weakly identified coefficients, normally beginning at degree four. |
| optimization coordinate | chart selection | Raw chord, endpoint-speed, or logistic endpoint charts over the same family; the shipped logistic chart makes the $\lambda_+$ wall unreachable. |
| surface orchestration | solver selection | Independent fits, interface screen, joint repair of violating groups (shipped default); one-way nearest-to-farthest sweep as explicit legacy. |
| right-tail turn and weight | soft barrier | Prices $\lambda_+$ near the martingale wall at one; in the shipped chart the wall itself cannot be reached. |
| parameter prior | regularizer | Stabilizes tails, warm starts, or continuity when data are sparse. |
| ATM/RR/BF operator targets | optional views | Add quote-operator prior rows. Exact level/skew/curvature retargeting is the separate local Newton chart of section "How to move level without wrecking shape"; the handle-neutral RR/BF/var-swap *package* moves inside the kernel are a third, distinct mechanism. |
| calendar rows and weight | soft surface control | Penalize adjacent-expiry order violations at fixed strikes on the common quote support; the ledger (59) stays diagnostic. |
| log-contract target | optional view | Target equation (64) without strike-strip extrapolation. |
| optimizer tolerances | numerical | Stop rules and evaluation budgets; they do not change feasibility. |

### B.3 Fresh deterministic benchmark ledger

**Table 4 — Diagnostics regenerated with the current production implementation.**

| Diagnostic | SPX-like | Event |
|---|---|---|
| Model order | 9 | 16 |
| Quotes | 24 | 37 |
| Max error (vol bp) | 1.341 | 2.444 |
| RMS error (vol bp) | 0.408 | 0.999 |
| $A_L$ | 0.157473 | 0.015531 |
| $A_R$ | 0.037786 | 0.014044 |

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 5 — Claim-to-implementation traceability.**

| Mathematical object | Production area | Audit |
|---|---|---|
| Legendre log-speed (76) | model parameter/basis code | endpoint values and basis recurrence tests |
| Integrated transport (7) | slice builder | monotonicity and grid-refinement tests |
| Martingale shift (9) | normalization path | $\lvert\mathbb{E}[Y]-1\rvert$ and tail-correction audit |
| Upper-share price (22) | pricer | parity, intrinsic bounds, quadrature comparison |
| Density (16) | density API | normalization and discrete-butterfly comparison |
| ATM handles | handle evaluator | analytic formulas versus centred quote-grid differences |
| Moment/Lee map | diagnostics | endpoint perturbations and asymptotic identities |
| Analytic Jacobian (56) | calibration Jacobian | central finite differences; see Figure 6 |
| Calendar order: confined price rows, symmetric repair | joint residual stack | `calib/calendar.py` / `calib/symmetric.py`; ledger (59) gap reports stay diagnostic |
| Log contract (64) | log-contract view | direct law integral versus option-strip benchmark |

---

## Appendix C. Performance notes and failure modes

### C.1 Work that is shared

For one parameter vector, the expensive objects are slice objects, not quote objects:

1. evaluate $h$ and $v$ on the logistic grid;
2. integrate once for $b$, normalize once for $m$, and accumulate once for $G$;
3. solve all monotone strike roots;
4. evaluate prices and, when requested, all parameter-share ledgers $G_j$.

Basis values, integration weights, and strike-independent interpolation structures can be cached. Warm starts across neighbouring expiries and market updates often save more time than a more exotic optimizer.

### C.2 Numerical qualifications

- **Near-wall conditioning.** Tail corrections contain $1/(1-\lambda_+)$ and sensitivities can explode before feasibility fails.
- **Interpolation consistency.** Separate Hermite interpolants for $x$ and $G$ are high-order accurate but do not preserve their continuous derivative identity exactly between nodes.
- **Implied-vol inversion.** Deep intrinsic options should be inverted from time value with robust price bounds; tiny vega magnifies price noise.
- **High-order cancellation.** Large alternating coefficients can create moderate $h$ in the quote window and extreme endpoints. Inspect endpoint speeds directly.
- **Grid convergence.** A good quote residual on one grid is not a numerical certificate. Production compares against a refined reference quadrature as part of its shipped audit battery; do the same for any derived quantity.
- **Fallback derivatives.** Core price, band, ridge, barrier, calendar, and both log-contract rows admit analytic or elementary derivatives; only the prior-anchor and operator blocks fall back to finite differences.

> **Performance.** The fastest trustworthy Jacobian is not the one with the fewest floating-point operations. It is the one whose columns can be reproduced by finite differences on a refined grid, whose tail sensitivity remains reported near the wall, and whose residual blocks declare when they fall back to numerical bumps.

---

## Appendix D. Compact reference implementation

*The transfer pack carries no source code; the pedagogical listing of the original appendix is restated here as a complete algorithm specification. The original displays the transport, martingale normalization, upper-share ledger, and call formula without production caching, tail corrections, or defensive error handling.*

**Algorithm D.1 (Slice build).**
*Inputs:* a sorted logit grid $z_0<\cdots<z_{M-1}$ and a coefficient vector $d_0,\ldots,d_N$ for the shifted-Legendre log-speed profile of equation (8).
*Outputs:* the normalized transport $x(z)$ on the grid, the upper asset-share ledger $G(z)$, and the two endpoint speeds $(\lambda_-,\lambda_+)$.
*Steps:*
1. Form the percentiles $p_j=\Lambda(z_j)=1/(1+e^{-z_j})$ and the shifted argument $\xi_j=1-2p_j$; evaluate the Legendre series $h_j=\sum_{n=0}^{N}d_nP_n(\xi_j)$ and the speed $v_j=e^{h_j}$.
2. Integrate the speed from the left end of the grid by the cumulative trapezoidal rule to obtain a raw ruler, then re-anchor it at the origin by subtracting its interpolated value at $z=0$, so that $b(0)=0$ (equation (6)).
3. Form the logistic weight $\rho_j=p_j(1-p_j)$ and the unshifted share integrand $e^{b_j}\rho_j$; integrate it over the whole grid by the trapezoidal rule to obtain the normalizer mass $M$; set the martingale shift $m=-\log M$ and the normalized transport $x_j=m+b_j$ (equation (9)).
4. Form the share density $e^{x_j}\rho_j$ and accumulate it from the right end of the grid toward the left (a reverse cumulative trapezoidal integral) so that $G(z_j)=\int_{z_j}^{z_{M-1}}e^{x(t)}\rho(t)\,\mathrm{d}t$, the finite-grid version of equation (19).
5. Compute the endpoint speeds from the alternating parity of Legendre endpoint values: $\lambda_-=\exp\bigl(\sum_{n=0}^{N}d_n\bigr)$ (all $P_n(1)=1$, reached at $p=0$) and $\lambda_+=\exp\bigl(\sum_{n=0}^{N}(-1)^nd_n\bigr)$ ($P_n(-1)=(-1)^n$, reached at $p=1$). If $\lambda_+\ge1$, refuse the vector: the finite-forward condition (15) is violated.

**Algorithm D.2 (Call pricing).**
*Inputs:* the grid arrays $z$, $x$, $G$ from Algorithm D.1 and a set of log-strikes $k$.
*Output:* normalized call prices $c(k)$.
*Steps:*
1. Build a monotone piecewise-cubic (PCHIP-type) interpolant of $z$ as a function of $x$, and a second interpolant of $G$ as a function of $z$.
2. For each log-strike $k$, solve the strike root $z_k$ by evaluating the inverse interpolant at $k$, and form the exercise percentile $p_k=\Lambda(z_k)$.
3. Return the asset tail minus the cash tail, $c(k)=G(z_k)-e^k(1-p_k)$ (equation (22)).

Three details are deliberately omitted from the listing. First, truncating $z$ without the analytic tail corrections in Appendix A, "Numerical construction and exact ATM algebra", biases the mean and far-wing prices. Second, a production implementation should evaluate the admissibility condition before exponentials overflow, then use scaled or log-domain accumulation near the boundary. Third, the cash leg as written carries a floating-point wing trap the audit battery caught: past $|z|\approx36.7$, the double-precision logistic $\Lambda(z)$ rounds to exactly one, the cash term $e^{k}(1-\Lambda(z_k))$ collapses to zero, and the far right wing steps up to the bare share — production evaluates the cash leg in log space, as $\exp\bigl(k-\log(1+e^{z_k})\bigr)$, for exactly this reason, and forms $u(1-u)$ as $\Lambda(z)\Lambda(-z)$ in the same spirit.

> **Example — What to test before optimizing.** For a random interior coefficient vector: refine the grid; check $\mathbb{E}[Y]=1$; check that $x$ is increasing; compare equation (22) with direct payoff quadrature; verify parity; recover density from discrete butterflies; and compare every analytic Jacobian column with symmetric finite differences. Only after those checks should a small calibration residual be treated as evidence.

---

## References

- [breedenlitzenberger] D. T. Breeden and R. H. Litzenberger. Prices of state-contingent claims implicit in option prices. *Journal of Business*, 51(4):621–651, 1978.
- [lee] R. W. Lee. The moment formula for implied volatility at extreme strikes. *Mathematical Finance*, 14(3):469–480, 2004.
- [benaimfriz] S. Benaim and P. K. Friz. Regular variation and smile asymptotics. *Mathematical Finance*, 19(1):1–12, 2009.
- [hardylittlewoodpolya] G. H. Hardy, J. E. Littlewood, and G. Pólya. *Inequalities*. Cambridge University Press, second edition, 1952.
- [shakedshanthikumar] M. Shaked and J. G. Shanthikumar. *Stochastic Orders*. Springer, 2007.
- [haganwest] P. S. Hagan and G. West. Interpolation methods for curve construction. *Applied Mathematical Finance*, 13(2):89–129, 2006.
- [fritschcarlson] F. N. Fritsch and R. E. Carlson. Monotone piecewise cubic interpolation. *SIAM Journal on Numerical Analysis*, 17(2):238–246, 1980.
- [gatheral] J. Gatheral. *The Volatility Surface: A Practitioner's Guide*. Wiley, 2006.
- [glasserman] P. Glasserman. *Monte Carlo Methods in Financial Engineering*. Springer, 2004.



