# The LQD Model, from Distribution to Smile

**Note 01 — log-quantile-density (LQD) smile model · lecture edition ("An alternative lecture on log-quantile-density parametrization") · converted from 01_lqd_model_lecture.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** A smile is a probability distribution wearing option-market clothes. The LQD model takes that sentence literally: instead of drawing implied volatility and then asking whether the resulting curve hides a negative density, it draws an increasing quantile function and prices the smile from the resulting law. For the log-forward return $X$, the model writes the logarithm of the quantile density as a universal two-sided tail skeleton plus a short Legendre expansion. Positivity is then automatic, a single additive shift enforces the forward martingale, and the endpoint scales identify both the last finite moments and the Lee wing slopes. This lecture develops the construction from a concrete logistic slice, proves the one-expiry no-butterfly result, derives pricing, tails, exact ATM level/skew/curvature identities, calibration, the analytic price Jacobian, and soft cross-expiry control. It then follows the production calibrator through two deterministic approximation cases: a seven-parameter fit to an SPX-like SVI target with maximum quote-grid error 0.23 volatility basis points, and a thirteen-parameter fit that qualitatively recovers a two-humped event density. The emphasis throughout is on the few facts that carry the model; numerical plumbing and control tables are kept out of their way.

**Contents.** 1. The desk problem: do not manufacture negative probability — 2. A probability ruler instead of a volatility curve — 3. The logistic slice: the whole machine in one toy — 4. Why the LQD formula has exactly this shape — 5. The wings know their moments — 6. Pricing is one cumulative integral — 7. Exact ATM handles: level, digital mismatch and density — 8. A local chart in trader coordinates — 9. Calibration: fit prices, measure errors in volatility units — 10. Case file: an SPX-like smile — 11. Case file: the density wears two hats — 12. The free derivative: an envelope argument — 13. From slices to a surface: convex order, softly enforced — 14. The native log-contract route — 15. What is guaranteed, and what is merely hoped for — 16. What the implementation exploits — 17. Traceability — Appendix A. Hyperparameter atlas — Appendix B. Performance and numerical notes — Appendix C. Reference implementation — References.

---

## 1. The desk problem: do not manufacture negative probability

Imagine fitting a quiet expiry with seven liquid strikes. The quoted vols are unremarkable; the interpolated smile looks smooth; the residuals are tiny. Then someone asks for a tight butterfly between two quote nodes. The model returns a negative price. Nothing dramatic happened on the screen. The curve was simply smooth in the wrong coordinate, and its second strike derivative changed sign between observations.

That failure is easy to explain after the fact. A call curve must be decreasing and convex in strike, because its second strike derivative is a risk-neutral density. A generic interpolant in implied volatility does not know this. There are perfectly good direct-price and constrained-SVI approaches, but they must encode or police the same global condition. LQD makes a different trade: it starts from a probability law, where non-negative mass is local and cheap, then integrates to option prices.

> **Invariants protected in this note.**
> 1. Every feasible one-expiry parameter vector defines a continuous, non-negative probability density and therefore a butterfly-free call slice.
> 2. The normalized underlying has mean one. This requires one scalar shift and, for the LQD tail family, the hard condition $A_R<1$.
> 3. Tail behaviour is part of the distribution, not an extrapolation patch: the endpoint scales determine the critical moments and Lee slopes.
> 4. The trader handles — ATM volatility, log-strike skew and curvature — are analytic functionals of the constructed slice, not finite differences of an IV grid.

### 1.1 Normalize first, so carry does not clutter the mathematics

Fix an expiry date $T$. Let $F_T$ and $D_T$ be its forward and discount factor, and define

$$
Y=\frac{S_T}{F_T},\qquad X=\log Y,\qquad
k=\log\frac{K}{F_T}.
\tag{1}
$$

Under deterministic carry and the $T$-forward measure,

$$
\mathbb{E}[Y]=\mathbb{E}[e^X]=1.
\tag{2}
$$

The normalized undiscounted call is

$$
C(k)=\frac{C^\$(F_Te^k,T)}{D_TF_T}
     =\mathbb{E}\!\left[(e^X-e^k)^+\right].
\tag{3}
$$

All slice formulas below live in these units. Dollars return only at the outer API boundary.

**The two clocks.** $T$ labels an expiry date; $\tau$ denotes the year fraction used for variance annualization. In production, $\tau$ is the active variance time supplied as `prepared.tau`: it equals calendar time when the event clock of Note 11 is inactive, and otherwise includes scheduled-event dilation. Thus $w=\sigma^2\tau$ and Black vega is $\varphi(d_+)\sqrt{\tau}$. Keeping $\tau$ visible avoids the common mistake of mixing carry time with variance time.

### 1.2 The model in one equation

Let $Q(u)$ be the quantile of $X$ at percentile $u\in(0,1)$ and $q(u)=Q'(u)$ its quantile density. LQD stands for *log quantile density*: it models $\ell(u)=\log q(u)$ as

**Central equation.**

$$
\ell(u)=-\log u-\log(1-u)+(1-u)L+uR
       +\sum_{n=2}^{N}a_nP_n(1-2u).
\tag{4}
$$

Here $P_n$ is the $n$th Legendre polynomial. The shipped order $N=6$ has the seven coefficients $(L,R,a_2,\ldots,a_6)$; the API accepts $4\le N\le16$. One scope remark before the ideas: $(L,R,a)$ is how a slice is *stored* and how this lecture will reason; the optimizer is free to run in any of three equivalent coordinate systems over the same family, and the shipped one differs from the storage chart in exactly the two places where the raw coordinates invite mistakes (sections "The wings know their moments" and "What the finite grid actually computes").

There are only three ideas in equation (4).

1. Taking a logarithm makes $q=e^\ell$ positive for every finite coefficient vector. Hence $Q$ is increasing and cannot fold probability mass over itself.
2. The terms $-\log u-\log(1-u)$ impose controllable exponential tails on $X$, hence power tails on $Y=e^X$ and linear total-variance wings.
3. A short orthogonal-polynomial expansion bends the distribution between the endpoints.

One warning is worth placing beside the definition. $L$ and $R$ are convenient low-order endpoint *coordinates*; once $a_n\ne0$, they are not the log tail scales. Every Legendre mode reaches both endpoints. The actual tail handles $A_L,A_R$ will appear in section "The wings know their moments" — and this warning is exactly why the shipped optimization chart puts $(\log A_L,\log A_R)$ on the axes instead of $(L,R)$, so that bending the body cannot mechanically drag the wings.

The full pipeline is

$$
(L,R,a_2,\ldots,a_N)
\longrightarrow q
\longrightarrow Q
\longrightarrow \text{mean-one shift}
\longrightarrow C(k)
\longrightarrow \sigma_{\rm imp}(k).
$$

In production, structural density positivity is still visible in one line, distilled from `backend/volfit/models/lqd/quadrature.py` (the pack carries no source code, so the line is stated as mathematics): at percentile $u$, with $g$ the smooth part of $\ell$ defined below in equation (13), the density evaluator returns

$$
f_X(Q(u))=\frac{1}{q(u)}=u\,(1-u)\,e^{-g(u)}\;\ge 0,
$$

which is non-negative for every finite coefficient vector — positivity is carried by the exponential, not policed by a constraint.

---

## 2. A probability ruler instead of a volatility curve

The cleanest way to read a quantile model is to start with a uniform random variable. Let $U\sim{\rm Uniform}(0,1)$ and set

$$
X=Q(U).
\tag{5}
$$

If $Q$ is strictly increasing, this construction assigns exactly $u$ units of probability below $Q(u)$. Where a density exists, differentiating $F_X(Q(u))=u$ gives

$$
f_X(Q(u))Q'(u)=1,\qquad
f_X(Q(u))=\frac{1}{q(u)}.
\tag{6}
$$

A large $q$ means that a wide interval of returns is needed to accommodate a small interval of probability: the ordinary density is thin there. A small $q$ means probability percentiles are packed together: the ordinary density is high. Quantile density and ordinary density are reciprocal views of the same ruler.

### 2.1 Why positivity of the ruler kills butterflies

Let $y=e^k$ be normalized strike and $\widetilde C(y)=\mathbb{E}[(Y-y)^+]$. When $Y$ has a density,

$$
\frac{\partial \widetilde C}{\partial y}=-(1-F_Y(y)),
\qquad
\frac{\partial^2\widetilde C}{\partial y^2}=f_Y(y)\ge0.
\tag{7}
$$

This is the Breeden–Litzenberger identity. It is useful intuition, but the no-butterfly proof is even shorter.

**Proposition 1 (Structural butterfly freedom).** Suppose $\overline Q$ is strictly increasing and $M=\int_0^1e^{\overline Q(u)}\,\mathrm{d}u$ is finite. Define $Q=\overline Q-\log M$. Then equation (3) is the call curve of a positive mean-one random variable. It is decreasing and convex in normalized strike, satisfies put–call parity, and is free of butterfly arbitrage.

*Proof.* With $U$ uniform, $Y=e^{Q(U)}$ is positive and $\mathbb{E}[Y]=e^{-\log M}M=1$. A call is the expectation of the convex payoff $(Y-y)^+$. Its strike monotonicity and convexity follow either pointwise from the payoff or from equation (7); parity follows by subtracting the corresponding put payoff. No density-positivity constraint is left for the optimizer. ∎

The proposition is deliberately modest. LQD spans a finite-dimensional *subset* of continuous densities; it does not claim to represent every density. And the statement is for one expiry. Cross-expiry calendar arbitrage is a separate question (section "From slices to a surface: convex order, softly enforced"). The scalar normalization translates the log-return law and rescales $Y$, but $Q'=\overline Q'$: quantile-density shape and tail slopes are unchanged.

### 2.2 Pricing directly on percentiles

Let $u_k$ solve $Q(u_k)=k$. Only percentiles above $u_k$ finish in the money, so

$$
C(k)=\int_{u_k}^{1}\left(e^{Q(u)}-e^k\right)\mathrm{d}u,
\tag{8}
$$

$$
P(k)=\int_{0}^{u_k}\left(e^k-e^{Q(u)}\right)\mathrm{d}u.
\tag{9}
$$

Subtracting the two integrals and using $\int_0^1e^{Q(u)}\,\mathrm{d}u=1$ gives $C(k)-P(k)=1-e^k$.

---

## 3. The logistic slice: the whole machine in one toy

Before adding a single polynomial, set

$$
a_n=0,\qquad L=R=\log s,\qquad 0<s<1.
\tag{10}
$$

Then

$$
q(u)=\frac{s}{u(1-u)},\qquad
Q(u)=\mu+s\log\frac{u}{1-u}.
$$

So $X$ is logistic with scale $s$, shifted by $\mu$. The martingale integral is a beta integral:

$$
\mathbb{E}[e^X]
=e^\mu\int_0^1u^s(1-u)^{-s}\,\mathrm{d}u
=e^\mu B(1+s,1-s)
=e^\mu\frac{\pi s}{\sin(\pi s)}.
\tag{11}
$$

Consequently

$$
\mu=-\log\frac{\pi s}{\sin(\pi s)},\qquad s<1,
\tag{12}
$$

and $\operatorname{Var}(X)=\pi^2s^2/3$. The same inequality $s<1$ that makes the beta integral finite will later become the general right-tail condition $A_R<1$.

> **Figure 1 — One law, three market languages (figure not included in this pack).** A logistic LQD slice with $s=0.078$ becomes an increasing log-return quantile (A), a non-negative density (B), and a half-year implied-volatility smile (C). The red dot follows the forward strike: martingale normalization places $Q(u)=0$ at $u=0.5321$, not at the median, so a symmetric log-return shape does not imply a perfectly symmetric Black smile. *Panel description:* panel A plots the quantile $Q(u)$ against percentile $u$ — an increasing S-shaped curve steepening toward both endpoints, with the red forward marker at $u=0.5321$ where $Q$ crosses zero; panel B shows the corresponding bell-shaped logistic density of the log return, strictly positive everywhere by construction; panel C shows the Black implied-volatility smile the same law generates over a half-year, gently convex near an ATM level of 19.20% and mildly asymmetric because the forward percentile sits above one half. The takeaway is quantitative: one scalar $s=0.078$ plus the martingale shift $\mu=-0.010028$ fixes an entire admissible option slice.

The plotted half-year slice has $\mu=-0.010028$, ATM volatility 19.20%, and a martingale self-check of $\mathbb{E}[e^X]-1=$ 0.00e+00. Its two endpoint scales both equal 0.078, but the left and right Lee slopes differ: 0.0375 and 0.0406. The difference comes from the martingale moment on the right: a finite forward consumes one power of $Y$.

> **Example — why the cold start is close, but not exact.** Production initializes $s$ from the heuristic variance match $w_{\rm ATM}\approx\operatorname{Var}(X)=\pi^2s^2/3$. This is intentionally cheap; ATM implied variance is not log-return variance. In fact, as $s\downarrow0$,
> $$
> C(0)\sim s\log2,\qquad
> B(0,w)\sim\sqrt{\frac{w}{2\pi}},
> \qquad
> w_{\rm ATM}\sim2\pi(\log2)^2s^2.
> $$
> The variance-match coefficient is about 8% larger. The initializer only needs to land in the right basin; the nonlinear fit supplies the correction.

The logistic law is therefore more than a classroom special case. It is a complete admissible slice, an analytic check on normalization and tails, and the actual cold-start family used by `logistic_init`.

---

## 4. Why the LQD formula has exactly this shape

### 4.1 The logit coordinate removes both endpoint singularities

Write the smooth part of equation (4) as

$$
g(u)=(1-u)L+uR+\sum_{n=2}^{N}a_nP_n(1-2u).
\tag{13}
$$

The divergence of $q=e^g/[u(1-u)]$ is real: it creates the return tails. The logit coordinate absorbs that divergence into a finite tail slope. Set

$$
z=\log\frac{u}{1-u},\qquad
u=\Lambda(z)=\frac{1}{1+e^{-z}},\qquad
\frac{\mathrm{d}u}{\mathrm{d}z}=u(1-u).
\tag{14}
$$

The two endpoint factors cancel:

$$
\frac{\mathrm{d}Q}{\mathrm{d}z}
=\frac{\mathrm{d}Q}{\mathrm{d}u}\frac{\mathrm{d}u}{\mathrm{d}z}
=\frac{e^{g(u)}}{u(1-u)}\,u(1-u)
=e^{g(\Lambda(z))}>0.
\tag{15}
$$

This is the operative equation in code. The open percentile interval $(0,1)$ has become the real line, and the quantile is the integral of a smooth positive function:

$$
\overline Q(z)=\int_0^z e^{g(\Lambda(r))}\,\mathrm{d}r.
\tag{16}
$$

> **Heuristic.** Think of $z$ as a probability ruler with evenly spaced tail marks. The function $e^g$ is the local exchange rate between that ruler and log return. Large $e^g$ stretches return space and thins the density; small $e^g$ compresses return space and piles probability up. Positivity says the ruler may stretch or compress, but it may never run backwards.

### 4.2 Why Legendre polynomials, and why start at degree two?

With $x=1-2u$, Legendre polynomials obey

$$
\int_0^1P_m(1-2u)P_n(1-2u)\,\mathrm{d}u
=\frac{\mathbf{1}_{m=n}}{2n+1}.
\tag{17}
$$

They provide a numerically well-scaled global basis on the percentile interval. The constant and linear degrees are already carried by

$$
(1-u)L+uR
=\frac{L+R}{2}+\frac{L-R}{2}(1-2u),
\tag{18}
$$

so the explicit sum begins at $n=2$. At $N=6$ the model spans the same polynomial space as $P_0,\ldots,P_6$, while retaining two readable baseline endpoint coordinates.

The word *body mode* can mislead. Legendre polynomials are global: $P_n(1)=1$ and $P_n(-1)=(-1)^n$. A coefficient that sculpts the centre also moves one or both endpoint scales. Orthogonality improves conditioning; it does not localize the parameters. Production evaluates the basis by the three-term recursion

$$
(n+1)P_{n+1}(x)=(2n+1)xP_n(x)-nP_{n-1}(x),
\qquad P_0=1,\quad P_1=x.
\tag{19}
$$

---

## 5. The wings know their moments

### 5.1 Endpoint scales are the genuine tail handles

Because $g$ is continuous at both endpoints,

$$
A_L:=e^{g(0)}
  =\exp\!\left(L+\sum_{n=2}^{N}a_n\right),
\tag{20}
$$

$$
A_R:=e^{g(1)}
  =\exp\!\left(R+\sum_{n=2}^{N}(-1)^na_n\right).
\tag{21}
$$

Integrating $q(u)\sim A_L/u$ on the left and $q(u)\sim A_R/(1-u)$ on the right gives finite constants $B_L,B_R$ such that

$$
Q(u)=B_L+A_L\log u+o(1)\quad(u\downarrow0),
\qquad
Q(u)=B_R-A_R\log(1-u)+o(1)\quad(u\uparrow1).
\tag{22}
$$

Thus $X$ has exponential tails. Equivalently, $Y=e^X$ has power tails. This is a modelling assumption, not a mere numerical convenience.

### 5.2 One integral gives the moment strip and the hard wall

For any real $r$,

$$
\mathbb{E}[e^{rX}]=\int_0^1e^{rQ(u)}\,\mathrm{d}u.
$$

Using equation (22), the left integrand behaves like $u^{rA_L}$ and the right like $(1-u)^{-rA_R}$. Therefore

$$
\mathbb{E}[e^{rX}]<\infty
\quad\Longleftrightarrow\quad
-\frac{1}{A_L}<r<\frac{1}{A_R}.
\tag{23}
$$

Setting $r=1$ proves the load-bearing admissibility condition

$$
A_R<1.
\tag{24}
$$

For finite coefficients this condition is necessary and sufficient for the forward moment. The left tail needs no analogous restriction because $A_L>0$ already makes $r=1$ integrable there.

> **Caution.** $A_R=1$ is not a regularization preference. At that wall the normalized underlying has infinite mean, so no finite forward exists. In the raw coordinate charts production keeps a $10^{-6}$ buffer, rejects $A_R\ge1-10^{-6}$, and adds a soft barrier centred at 0.90 to turn the optimizer back before rejection; the barrier is smooth inside the feasible region, and the switch to the infeasible penalty branch is not an algebraic continuation through the wall. In the shipped optimization chart the question does not arise: $A_R$ enters through a logistic, so the wall sits at infinite chart distance and no trial can reach it — the barrier stays on there too, no longer as a fence but as a price on economically implausible near-infinite forwards.

### 5.3 From critical moments to Lee slopes

For $Y=e^X$, define the last finite extra right moment and inverse left moment

$$
p_+=\sup\{p\ge0:\mathbb{E}[Y^{1+p}]<\infty\}
    =\frac{1}{A_R}-1,
\qquad
p_-=\sup\{p\ge0:\mathbb{E}[Y^{-p}]<\infty\}
    =\frac{1}{A_L}.
\tag{25}
$$

Lee's moment map is

$$
\psi(p)=2-4\left(\sqrt{p^2+p}-p\right),\qquad p\ge0.
\tag{26}
$$

Under the regular exponential-tail asymptotics of equation (22), the total implied variance $w(k)$ has the limiting slopes

$$
\beta_L:=\lim_{k\to-\infty}\frac{w(k)}{|k|}=\psi(p_-),
\qquad
\beta_R:=\lim_{k\to+\infty}\frac{w(k)}{k}=\psi(p_+).
\tag{27}
$$

For a trader who wants to skip the critical-moment notation, the same maps are

$$
\beta_L=
2\,\frac{\sqrt{1+A_L}-1}{\sqrt{1+A_L}+1},
\qquad
\beta_R=
2\,\frac{1-\sqrt{1-A_R}}{1+\sqrt{1-A_R}},
\quad 0<A_R<1.
\tag{28}
$$

Larger endpoint scale means a heavier return tail and a steeper variance wing. The right-hand curve reaches the model-free ceiling $2$ as the finite-forward wall is approached.

> **Figure 2 — The endpoint scales carry economic meaning (figure not included in this pack).** Panel A maps each scale to its last finite moment; the right moment collapses at $A_R=1$. Panel B maps the same scales to Lee slopes. The red points are the two tails of the SPX-like benchmark: they sit far from the wall and well below the slope ceiling. *Panel description:* panel A plots the critical-moment curves of equation (25) — $p_-=1/A_L$ on the left (a decreasing hyperbola in the endpoint scale) and $p_+=1/A_R-1$ on the right, which falls to zero as $A_R\uparrow1$, the collapse of the last finite forward-plus moment. Panel B passes the same scales through Lee's map, equation (28): both slope curves rise from zero, and the right curve saturates at the model-free ceiling $2$ as $A_R\to1$. The two red benchmark markers sit at $A_L=0.214458$ (mapping to $\beta_L=0.097073$) and $A_R=0.069023$ (mapping to $\beta_R=0.035757$) — far from the $A_R=1$ wall and far below the ceiling.

> **Example — reading the SPX-like tails.** The fitted benchmark later studied in section "Case file: an SPX-like smile" has $A_L=0.214458$ and $A_R=0.069023$. Equations (25)–(27) give $\beta_L=0.097073$ and $\beta_R=0.035757$. These are sensible extrapolation diagnostics, not strongly identified market observables: twenty-five quotes over a finite strike window cannot uniquely determine asymptotic moments.

---

## 6. Pricing is one cumulative integral

The percentile formula (8) is conceptually complete. Production re-expresses it on the logit grid because that grid is smooth, symmetric and shared by every strike.

### 6.1 Normalize once, then reuse the upper asset share

Start from the centred primitive (16). Since $\mathrm{d}u=u(1-u)\,\mathrm{d}z$, the martingale shift is

$$
\mu=-\log\!\left[
\int_{-\infty}^{\infty}
e^{\overline Q(z)}\Lambda(z)(1-\Lambda(z))\,\mathrm{d}z
\right],
\qquad
Q(z)=\mu+\overline Q(z).
\tag{29}
$$

Define the upper asset-share integral

$$
\mathcal A(z)
=\int_z^\infty e^{Q(r)}\Lambda(r)(1-\Lambda(r))\,\mathrm{d}r.
\tag{30}
$$

If $z_k$ solves $Q(z_k)=k$ and $u_k=\Lambda(z_k)$, then

$$
C(k)=\mathcal A(z_k)-e^k(1-u_k).
\tag{31}
$$

This is just equation (8) split into its asset and strike legs. One forward cumulative integral builds $Q$; one reverse cumulative integral builds $\mathcal A$; each strike then needs only a scalar inversion and interpolation.

### 6.2 From price to the quoted Black volatility

The normalized Black call in total-variance coordinates is

$$
B(k,w)=\Phi(d_+)-e^k\Phi(d_-),
\qquad
d_\pm=-\frac{k}{\sqrt w}\pm\frac{\sqrt w}{2}.
\tag{32}
$$

For an admissible call price, implied total variance solves $B(k,w(k))=C(k)$, and

$$
\sigma_{\rm imp}(k)=\sqrt{\frac{w(k)}{\tau}}.
\tag{33}
$$

LQD therefore does not interpolate in implied-volatility space. The full strike curve, including its extrapolation, is the Black image of a fitted probability distribution.

### 6.3 What the finite grid actually computes

The production grid is $z\in[-40,40]$. Optimization uses 2001 nodes; the accepted slice is rebuilt once on $8001$ nodes for reporting and downstream diagnostics. Cumulative Simpson integration constructs $Q$ and $\mathcal A$ when available, while the martingale body integral uses the trapezoidal rule. At the two truncated endpoints the leading asymptotic corrections are

$$
\int_{40}^{\infty} e^Q u(1-u)\,\mathrm{d}z
\approx\frac{e^{Q(40)-40}}{1-A_R},
\qquad
\int_{-\infty}^{-40} e^Q u(1-u)\,\mathrm{d}z
\approx\frac{e^{Q(-40)-40}}{1+A_L}.
\tag{34}
$$

For a fixed finite-order polynomial $g$, the neglected relative terms decay exponentially in the cutoff. They are tiny for ordinary fitted equity scales, but equation (34) remains an asymptotic correction, not an exact tail integral.

At each grid node the implementation stores

$$
Q_z=e^g,\qquad
\mathcal A_z=-e^Q u(1-u).
$$

These exact nodal derivatives define cubic-Hermite interpolants. Strike inversion starts from a linear seed and takes four safeguarded Newton steps. On benchmark slices this is much more accurate than a table lookup; it should not be advertised as a universal extrapolator outside the finite grid or as an algebraic proof of machine precision for arbitrary coefficients.

Two floating-point guards survive in *every* coordinate chart and are worth naming, because they are what actually rejects a wild trial once the wall is unreachable. An interior overflow budget on the unnormalized quantile rejects coefficient vectors whose exponentials would overflow before any price is formed — a clean refusal, not a fake surface. And the logistic itself rounds: past $|z|\approx36.7$, `expit(z)` is exactly one in double precision, so the cash leg of the call is evaluated in log space and $u(1-u)$ is formed as $\Lambda(z)\Lambda(-z)$ rather than $u(1-u)$ — otherwise the far wing of the price curve steps visibly.

> **Performance.** The arrays $(z,u,u(1-u))$ and the Legendre matrix depend only on grid size and model order. They are cached and returned read-only. Calibration reforms only $g$, its exponential and the cumulative integrals. The static-grid cache made `build_slice` about $1.7\times$ faster; the two-grid scheme spends full resolution only on the accepted parameters.

---

## 7. Exact ATM handles: level, digital mismatch and density

Traders rarely want to drag $a_4$ on a screen. They want ATM volatility, ATM skew and ATM curvature. LQD obtains these as analytic log-strike derivatives of the numerically constructed slice, without finite-differencing an implied-vol grid.

Let $u_0$ solve $Q(u_0)=0$ and define

$$
c_0=C(0),\qquad
f_0=f_X(0)=u_0(1-u_0)e^{-g(u_0)}.
\tag{35}
$$

Differentiating the call expectation with respect to log strike gives

$$
C'(0)=-(1-u_0),\qquad
C''(0)=f_0-(1-u_0).
\tag{36}
$$

The ATM Black identity is

$$
c_0=2\Phi\!\left(\frac{\sqrt{w_0}}{2}\right)-1,
$$

so its solution is explicit:

$$
w_0=4\left[
\Phi^{-1}\!\left(\frac{1+c_0}{2}\right)
\right]^2.
\tag{37}
$$

Set

$$
d_0=\frac{\sqrt{w_0}}{2},\qquad
\varphi_0=\varphi(d_0),\qquad
\delta=u_0-\Phi(d_0).
\tag{38}
$$

Implicit differentiation of $B(k,w(k))=C(k)$ and elementary simplification give

$$
w'(0)=2\sqrt{w_0}\,\frac{\delta}{\varphi_0},
\tag{39}
$$

$$
w''(0)=2\sqrt{w_0}\,\frac{f_0}{\varphi_0}-2
    +2\left(1+\frac{w_0}{4}\right)
       \left(\frac{\delta}{\varphi_0}\right)^2.
\tag{40}
$$

Converting total variance to annualized volatility yields the three handles

$$
\sigma_0=\sqrt{\frac{w_0}{\tau}},
\tag{41}
$$

$$
s_0=\left.\frac{\partial\sigma_{\rm imp}}{\partial k}\right|_{0}
   =\frac{\delta}{\varphi_0\sqrt{\tau}},
\tag{42}
$$

$$
\kappa_0=\left.\frac{\partial^2\sigma_{\rm imp}}{\partial k^2}\right|_{0}
   =\frac{1}{\sqrt{\tau}}\left[
      \frac{f_0}{\varphi_0}-\frac{1}{\sqrt{w_0}}
      +\frac{\sqrt{w_0}}{4}
       \left(\frac{\delta}{\varphi_0}\right)^2
     \right].
\tag{43}
$$

**Proposition 2 (What the ATM handles measure).** For any admissible numerically constructed LQD slice, the identities (41)–(43) give its exact analytic log-strike ATM derivatives. Level is determined by the ATM call, skew by the difference between the LQD and Black ATM CDF levels $u_0$ and $\Phi(d_0)$ (equivalently, the negative call-digital mismatch), and curvature primarily by the density height $f_0$, with a skew correction.

*Proof.* Equation (36) follows from $C'(k)=-e^k(1-F_X(k))$. Differentiate the identity $B(k,w(k))=C(k)$ once and twice, substitute the Black partial derivatives at $k=0$, and simplify using equation (38). Finally differentiate $\sigma_{\rm imp}=\sqrt{w/\tau}$. ∎

The qualifier *numerically constructed* matters. $u_0$, $c_0$ and $f_0$ come from the quadrature slice. The formulas are exact chain-rule identities conditional on that slice; they are not closed-form functions of the raw coefficient vector.

---

## 8. A local chart in trader coordinates

Let $\theta=(L,R,a_2,\ldots,a_N)\in\mathbb{R}^d$ — the storage coordinates; the handle analysis below is insensitive to which of the three optimization charts carries the fit — and collect the internal chart handles as

$$
H(\theta)=(w_0,s_0,\kappa_0).
\tag{44}
$$

The graph-facing carrier used by Note 14 replaces $w_0$ with $\sigma_0=\sqrt{w_0/\tau}$; the distinction is small in notation and important in units.

**Assumption 1 (Regular handle point).** At the reference slice $\theta^*$, the Jacobian $J=\partial H/\partial\theta\in\mathbb{R}^{3\times d}$ has full row rank three and is not numerically ill-conditioned in the chosen Euclidean coefficient metric — the default, and an admitted convention; a Gauss–Newton metric that prices a move by its effect on the fitted quotes is also available.

Under Assumption 1, let $J^\dagger=J^{\mathsf{T}}(JJ^{\mathsf{T}})^{-1}$ be the least-norm right inverse and let the columns of $V$ form an orthonormal basis of $\ker J$. A local displacement can be written

$$
\theta=\theta^*+J^\dagger\alpha+V\xi.
\tag{45}
$$

To first order, $\alpha\in\mathbb{R}^3$ moves the three trader handles one-for-one, while the shape coordinate $\xi\in\mathbb{R}^{d-3}$ leaves them unchanged: $JJ^\dagger=I_3$ and $JV=0$. In code, an SVD/QR construction is what production uses near weak rank, because it exposes the small singular values rather than hiding them in $(JJ^{\mathsf{T}})^{-1}$ — the handle Gram's condition number is computed and carried on the chart. The kernel, finally, is not left anonymous: alongside session-local shape sliders, production names persistent *package* directions inside $\ker J$ — 25- and 10-delta risk reversals and butterflies and the var swap — solved with an explicit cross-talk matrix and a kernel-restricted condition print, so the "shape" a desk moves is the market's own vocabulary.

For a finite move, first-order orthogonality is not enough. Production holds $\xi$ fixed and solves the three-dimensional nonlinear equation

$$
H(\theta^*+J^\dagger\alpha+V\xi)=H_{\rm target}
\tag{46}
$$

by Newton iteration. This keeps the chart's local shape coordinates fixed; it does *not* promise that the endpoint scales or wings remain unchanged.

> **Caution.** The chart is local and conditional on rank. A large handle request can leave the neighbourhood where $J$ is useful, drive $A_R$ toward the integrability wall, or admit no feasible retargeted slice. The chart separates tasks; it does not regularize the free shape coordinates. Ridge penalties, data and priors remain responsible for suppressing implausible oscillation.

---

## 9. Calibration: fit prices, measure errors in volatility units

### 9.1 The core objective

Suppose the prepared quote set contains $(k_i,\sigma_i,\omega_i)$ at active time $\tau$, with quote total variance $w_i=\sigma_i^2\tau$. Convert each quote once to its normalized Black call and freeze its quote vega:

$$
C_i^{\rm mkt}=B(k_i,w_i),\qquad
v_i=\varphi(d_{+,i})\sqrt{\tau}.
\tag{47}
$$

The core fit minimizes

$$
\sum_i\omega_i
\left(
\frac{C^{\rm LQD}(k_i;\theta)-C_i^{\rm mkt}}
     {v_i+\eta}
\right)^2
+\lambda\sum_{n=4}^{N}n^{2r}a_n^2.
\tag{48}
$$

The price numerator preserves the distribution-first construction at each feasible priced iterate. Dividing by quote vega makes the residual locally comparable to a volatility error; the floor $\eta=10^{-4}$ prevents far-wing quotes from receiving explosive weight. The high-order ridge leaves $a_2,a_3$ free and damps modes $n\ge4$.

The low-level function defaults to $\lambda=0$. The shipped application setting is $\lambda=10^{-6}$, and the benchmark generator passes it explicitly. This distinction matters when reproducing a fit from the library rather than the UI.

### 9.2 The soft turn before the hard wall

The residual stack always contains the softplus row

$$
b(\theta)=\log\!\left(1+
\exp\{s_b(A_R-c)\}\right),
\qquad c=0.90,\quad s_b=50.0.
\tag{49}
$$

It is evaluated with a stable `logaddexp`. In the raw coordinate charts, when a trial reaches the buffered hard wall $A_R\ge1-10^{-6}$, slice construction is skipped and the price block is replaced by a large penalty increasing with $A_R$: an infeasible trust-region trial does not produce a fake option surface; it receives a direction back toward feasibility. In the shipped logistic chart no trial can reach the wall, and the refusal that survives in every chart is the interior overflow budget of section "What the finite grid actually computes".

### 9.3 Initialization and warm starts

The cold start is the logistic family of section "The logistic slice: the whole machine in one toy":

$$
s_{\rm init}=\frac{\sqrt{3w_{\rm ATM}}}{\pi},\qquad
L=R=\log s_{\rm init},\qquad a_n=0.
\tag{50}
$$

As the logistic example showed, this is a scale heuristic rather than an exact ATM match. In a surface sweep, the fitted shorter expiry is usually a much better initializer for the next expiry, so the production sweep *seeds* nearest to farthest. Seeding is not solving: the surface itself is fitted expiry-by-expiry independently, then screened and jointly repaired where adjacent slices conflict (section "From slices to a surface: convex order, softly enforced") — warm-start order is a convergence heuristic, not a constraint topology. A data-only prepass can also supply the measurement stage for the persistence and filtering machinery of Notes 13 and 15.

### 9.4 The production residual stack

The core objective is only the spine. `calibrate_slice` concatenates the blocks in Table 1. Optional blocks are absent when inactive, and the Jacobian route changes with them.

**Table 1 — The production residual stack.** FD denotes scipy's two-point finite-difference Jacobian; activating a prior-anchor or operator block switches the entire solve to that route. Both var-swap rows ride the analytic sensitivity pass (section "The native log-contract route").

| Block | Activation | Scale | Jacobian |
|---|---|---|---|
| Mid or band quote data | selected fit mode | vega-normalized price | analytic |
| High-order ridge | $\lambda>0$ | coefficient residual | analytic |
| Calendar hinge | nearer fitted expiry available and control on | normalized price at fixed strike, support-confined | analytic |
| $A_R$ barrier | always | dimensionless | analytic |
| Market var-swap | active quote and toggle | volatility | analytic |
| Prior var-swap | active companion prior | volatility | analytic |
| Strike-gap prior | active prior mode | vega-normalized price | FD |
| Operator/filter prior | gated prior or active filter | handle/operator units | FD |

---

## 10. Case file: an SPX-like smile

The first test is deliberately synthetic. It asks whether seven LQD parameters can approximate a clean, familiar equity-index shape; it is not a claim about live market fit. At $\tau=0.5$, the target is the legacy raw-SVI regression fixture (the older five-parameter benchmark; the running example of the sibling editions has since moved on, but this oracle stays frozen so its locked numbers stay comparable):

$$
w_{\rm SVI}(k)
=a+b\left\{\rho(k-m)+\sqrt{(k-m)^2+\sigma_{\rm SVI}^2}\right\},
\tag{51}
$$

with

$$
(a,b,\rho,m,\sigma_{\rm SVI})
=(0.010625,\;0.07289,\;-0.5,\;0.05831,\;0.10100).
$$

Twenty-five synthetic quotes cover $k\in[-0.35,0.30]$. The production calibrator uses $N=6$, the application ridge $\lambda=10^{-6}$, equal quote weights, the logistic cold start and the standard barrier.

> **Figure 3 — SPX-like fit and residuals (figure not included in this pack).** The seven-parameter LQD slice is visually indistinguishable from the SVI target over the quote window (left), but the residual panel (right) makes the approximation claim auditable: the maximum quote-grid error is 0.23 volatility basis points. Outside the fitted window the LQD curve follows its own distributional tails, not an SVI continuation. *Panel description:* the left panel overlays the fitted LQD implied-volatility curve on the SVI target and its twenty-five quote markers over $k\in[-0.35,0.30]$ — the two curves coincide to line width, with the typical negative-skew index shape (higher vols on the downside). The right panel plots the signed fit error in volatility basis points at each of the twenty-five quotes; every bar sits inside a fraction-of-a-basis-point band, with worst absolute error 0.23 bp. Beyond both ends of the quote window the curves separate, since LQD extrapolates by its own exponential-tail law rather than by the SVI wing formula.

The fit takes 7 residual evaluations. Its exact ATM readout is

$$
\sigma_0=20.62\%,\qquad
s_0=-0.3538,\qquad
\kappa_0=1.6474.
$$

The martingale self-consistency check is $\mathbb{E}[e^X]-1=$ 0.00e+00. The endpoint and tail diagnostics are

$$
A_L=0.214458,\quad A_R=0.069023,\quad
\beta_L=0.097073,\quad \beta_R=0.035757.
$$

Raw SVI has asymptotic slopes $b(1-\rho)=0.1093$ on the left and $b(1+\rho)=0.0364$ on the right. Their closeness to the LQD diagnostics is reassuring for this constructed target, but finite-window quotes do not in general identify asymptotic slopes to two decimals.

> **Figure 4 — The same fit in distribution coordinates (figure not included in this pack).** The log-return density is non-negative because it is the reciprocal of a positive quantile density (left). The log quantile density (right) shows the endpoint rise that produces exponential return tails. Positivity is structural; the economic plausibility of the shape still comes from data and regularization. *Panel description:* the left panel plots the fitted density $f_X$ of the log return — a left-skewed unimodal curve, everywhere strictly positive, with the heavier lobe on the downside consistent with the negative skew $s_0=-0.3538$. The right panel plots $\ell(u)=\log q(u)$ against percentile $u$: a smooth bowl over the body that turns upward toward both endpoints, the divergence $-\log u-\log(1-u)$ whose coefficients $A_L=0.214458$ and $A_R=0.069023$ are precisely the tail scales read off in section 5.

**Table 2 — Fresh seven-parameter LQD fit to the SPX-like SVI target.** Because the basis is global, the coefficients should not be read individually as pure level, skew, curvature or wing knobs.

| Parameter | Value |
|---|---|
| $L$ | -1.87479110 |
| $R$ | -3.08957252 |
| $a_{2}$ | +0.38076853 |
| $a_{3}$ | -0.04700855 |
| $a_{4}$ | -0.00719617 |
| $a_{5}$ | +0.00645578 |
| $a_{6}$ | +0.00213226 |

> **Example — Case verdict: approximation capacity, not market alpha.** **Setup:** a clean six-month index-like SVI smile. **Failure to avoid:** matching the quotes while creating negative density between them. **Mechanism:** fit normalized prices inside the LQD density family. **Verdict:** 0.23 vol bp maximum error on the twenty-five input quotes, a non-negative density and a finite-forward tail far from the wall. Live bid–ask and out-of-sample comparisons belong to `backend/backtest/`, not to this synthetic case.

---

## 11. Case file: the density wears two hats

Scheduled elections, court decisions, earnings and binary regulatory events can produce a terminal law with two plausible landing zones. To isolate that geometry, take the equal mixture

$$
X\sim\frac12N(m_1,s^2)+\frac12N(m_2,s^2),
\qquad
(m_1,m_2,s)=(-0.10075573,\;0.08924427,\;0.05).
\tag{52}
$$

Here $s=5\%$ is the component standard deviation of the thirty-day *log-return*, not an annualized implied volatility. The means are chosen so

$$
\frac12e^{m_1+s^2/2}+\frac12e^{m_2+s^2/2}=1,
\tag{53}
$$

which martingale-normalizes the mixture. Its call is available in closed form:

$$
C_{\rm mix}(k)
=\frac12\sum_{j=1}^{2}\left[
e^{m_j+s^2/2}
\Phi\!\left(\frac{m_j+s^2-k}{s}\right)
-e^k\Phi\!\left(\frac{m_j-k}{s}\right)
\right].
\tag{54}
$$

We turn forty-one such calls over $k\in[-0.25,0.25]$ into implied variances and fit $N=12$ with $\lambda=10^{-7}$.

> **Figure 5 — A binary-event geometry needs more than a smooth U-shaped smile (figure not included in this pack).** The thirteen-parameter fit captures the central trough and supported wings (left) and qualitatively recovers both modes of the known target density (right). The maximum quote-grid error is 13.19 vol bp; the density comparison is possible only because this is a synthetic case with a known law. *Panel description:* the left panel overlays the fitted LQD smile on the forty-one mixture-implied quotes over $k\in[-0.25,0.25]$ — a W-like shape with a pronounced central trough between the two landing zones and elevated vols at both supported wings, which the order-12 fit tracks to within 13.19 bp at the worst quote. The right panel compares the fitted LQD density with the true two-normal mixture density: both humps, centred near $m_1=-0.10075573$ and $m_2=0.08924427$, are qualitatively recovered, with modest smoothing of the inter-modal valley.

The fitted endpoint scales are $A_L=0.015341$ and $A_R=0.014979$, both thin and far from the integrability wall. Higher order is doing real work in the centre, but positivity alone does not certify that the two modes are genuine. With sparse quotes, a high-order LQD slice can create a beautifully admissible fiction.

> **Example — Case verdict: positive is not the same as plausible.** **Setup:** a known two-normal event mixture. **Failure to avoid:** forcing a low-order smile through a central trough, or using an unconstrained flexible curve that turns negative between quotes. **Mechanism:** higher Legendre order inside an always-positive quantile density. **Verdict:** both modes are qualitatively recovered, with 13.19 vol bp maximum quote-grid error. On real data, order selection, ridge strength, bid–ask information and event priors must decide whether a second hat is signal or overfit.

---

## 12. The free derivative: an envelope argument

For a seven-parameter fit, a finite-difference Jacobian rebuilds the quadrature once for the value and once per bumped coefficient. That is tolerable; at higher order and across many expiries it becomes the dominant repeated work. The continuous price formula contains a fortunate cancellation.

Let $u_k(\theta)$ be the moving percentile satisfying $Q(u_k(\theta);\theta)=k$. Differentiate equation (8) at fixed strike:

$$
\begin{aligned}
\frac{\partial C(k;\theta)}{\partial\theta}
&=\int_{u_k}^{1}
e^{Q(u;\theta)}Q_\theta(u;\theta)\,\mathrm{d}u
-\left[e^{Q(u_k;\theta)}-e^k\right]
\frac{\partial u_k}{\partial\theta} \\
&=\int_{u_k}^{1}
e^{Q(u;\theta)}Q_\theta(u;\theta)\,\mathrm{d}u.
\end{aligned}
\tag{55}
$$

The boundary term vanishes because $Q(u_k;\theta)=k$. The strike root may move violently with a parameter; its first-order effect on the payoff is still zero because the payoff itself is zero at the exercise boundary.

**Theorem 1 (Implicit-root cancellation).** For an admissible smooth LQD slice, the parameter derivative of a fixed-strike call is the explicit quantile sensitivity in equation (55). No derivative of the implicit strike root is required.

*Proof.* Apply Leibniz' rule to equation (8). The moving-boundary term is the payoff at the boundary times $u_{k,\theta}$, and the payoff is zero. ∎

In logit coordinates, production evaluates the same derivative by interpolating the parameter sensitivities of the upper asset share at the fixed $z_k$. If $\phi_j(u)=\partial g/\partial\theta_j$, then

$$
\frac{\partial\overline Q(z)}{\partial\theta_j}
=\int_0^z e^{g(\Lambda(r))}\phi_j(\Lambda(r))\,\mathrm{d}r,
\tag{56}
$$

where

$$
\phi_L=1-u,\qquad \phi_R=u,\qquad
\phi_{a_n}=P_n(1-2u).
$$

Differentiate the martingale normalization, add the resulting scalar $\mu_{\theta_j}$ to equation (56), and reverse-integrate $e^Qu(1-u)Q_{\theta_j}$ to obtain the asset-share sensitivity. The endpoint corrections also differentiate through $Q(\pm40)$ and $A_L,A_R$. Ridge, calendar and barrier rows then add elementary derivatives.

The theorem is exact for the continuous integrals. The production price and gradient use separately constructed Hermite interpolants, so an off-node comparison inherits a small discretization mismatch. The tested claim is numerical: on mid, band, calendar and var-swap residual stacks the analytic Jacobian agrees with a three-point finite difference to relative tolerance $10^{-3}$, and analytic and two-point-FD fits reach coefficient vectors within about $10^{-5}$ and costs agreeing near $10^{-11}$ relative.

> **Figure 6 — Jacobian timing (figure not included in this pack).** The envelope cancellation removes repeated quadrature builds. On the warm-cache optimizer-core benchmark, the analytic route is measured faster at every order $N=6,\ldots,12$ (each per-order ratio is annotated on its bar) and reaches the same optimum within the tested tolerances. These bars exclude the final full-grid rebuild and reporting work, so they are not end-to-end API latency. *Panel description:* paired bars per model order compare analytic-Jacobian against finite-difference calibration time on the warm-cache benchmark; from the same generator run, the measured pairs are $N=6$ ($P=7$ parameters): 15.5 ms analytic vs 24.7 ms FD ($1.59\times$); $N=8$ ($P=9$): 18.4 vs 24.9 ms ($1.35\times$); $N=10$ ($P=11$): 25.6 vs 68.8 ms ($2.68\times$); $N=12$ ($P=13$): 30.7 vs 47.6 ms ($1.55\times$), with final-cost agreement between the two routes in the $10^{-19}$–$10^{-20}$ range at every order. The analytic bar wins at every order, with the largest gap where the parameter count makes per-column rebuilds most expensive.

> **Heuristic.** Why is the speed-up not $P$-fold for $P$ parameters? Cached static arrays make each bumped build relatively cheap, the trust-region solve still performs linear algebra and value evaluations, and these clean synthetic fits converge in few iterations. The useful result is structural: higher order no longer forces one full quadrature rebuild per Jacobian column.

---

## 13. From slices to a surface: convex order, softly enforced

Butterfly freedom is a within-expiry property. For expiry dates $T_1<T_2$, absence of calendar arbitrage under deterministic carry requires

$$
C_{T_1}(k)\le C_{T_2}(k)\qquad\text{for every }k.
\tag{57}
$$

Because both normalized underlyings have mean one, this is equivalent to saying that $Y_{T_2}$ dominates $Y_{T_1}$ in convex order: the later law is more dispersed without moving its mean.

Quantiles give a native criterion. Define the integrated upper quantile

$$
G_T(\alpha)=\int_\alpha^1e^{Q_T(u)}\,\mathrm{d}u,
\qquad 0\le\alpha\le1.
\tag{58}
$$

For equal-mean positive laws,

$$
Y_{T_1}\le_{\mathrm{cx}}Y_{T_2}
\quad\Longleftrightarrow\quad
G_{T_1}(\alpha)\le G_{T_2}(\alpha)
\quad\text{for every }\alpha,
\tag{59}
$$

with equality at $\alpha=0$. In LQD, $G_T(\Lambda(z))$ is exactly the asset share $\mathcal A_T(z)$ already present on the pricing grid.

What production *enforces* is deliberately not the share comparison. The asset share integrates the entire upper tail, so a hinge that compares two shares at any rank imports both slices' extrapolated wings into the constraint — a fit can be dragged by strikes nobody quoted, and on an acute short-dated pair the phantom drag from a full-grid share floor measured two orders of magnitude above the uncoupled fit (Note 10 owns the incident and its certification lock). When calendar control is on, the order is instead read where it is identified: as tapered hinge rows on the two slices' normalized calls at fixed strikes over their common quote support, with the share comparison retained as the wing-dense *diagnostic* it is exactly suited to be.

> **Caution.** The mathematical condition (59) is a continuum condition. Production samples it, assigns a finite penalty weight, and allows the control to be switched off. It is therefore calendar *control*, not a hard guarantee. Nor is the surface a one-way construction: every expiry is fitted independently, the finished ladder is screened interface by interface, and only a violation-connected group of slices is re-solved jointly (the symmetric surface solver, the shipped default; the sequential nearest-to-farthest sweep survives as explicit legacy configuration whose defect is exactly the traversal-order bias a one-way pass builds in). Diagnostics measure the final call ordering rather than inferring it from the workflow — and report residual violations in desk units: the worst-violation strike, currency per contract, ticks, and the fraction of the local quoted spread.

Note 10 treats the model-agnostic calendar problem in detail. LQD's advantage is not a stronger theorem; it is that the natural convex-order object is already one of its cumulative pricing arrays — an advantage of *measurement*, which production learned not to confuse with an advantage of enforcement.

---

## 14. The native log-contract route

For a mean-one positive underlying, the continuous log-contract proxy to total variance is

$$
w_{\rm vs}=-2\mathbb{E}[X]
=-2\int_0^1Q(u)\,\mathrm{d}u
=-2\int_{-\infty}^{\infty}
Q(z)\Lambda(z)(1-\Lambda(z))\,\mathrm{d}z.
\tag{60}
$$

The last integral uses the grid LQD already owns. Production evaluates it by a trapezoidal rule without explicit tail corrections; its integrand decays as $z e^{-|z|}$, so the omitted $|z|>40$ contribution is negligible in ordinary double precision.

Equation (60) prices a log contract. Identifying it with a realized-variance swap assumes the usual continuous-monitoring, continuous-path convention. Jumps and discrete sampling require corrections. The residual row is as cheap as it looks: since the analytic sensitivity pass already carries the nodal quantile derivatives, the row's own gradient $\partial w_{\rm vs}/\partial\theta=-2\int(\partial Q/\partial\theta)\,\Lambda(1-\Lambda)\,\mathrm{d}z$ is one more quadrature on the same grid, so a var-swap-enabled fit keeps the analytic Jacobian route.

---

## 15. What is guaranteed, and what is merely hoped for

Table 3 is the shortest honest description of the model.

**Table 3 — The LQD contract.** Arbitrage structure and economic plausibility are different promises.

| Property | Status | Qualification |
|---|---|---|
| Non-negative continuous density | Structural | For every finite coefficient vector; numerical pricing is still finite precision. |
| One-expiry butterfly freedom | Structural after normalization | Requires a finite forward and correct normalized units. |
| Finite forward | If and only if $A_R<1$ mathematically | Raw charts use the buffer $A_R<1-10^{-6}$; the shipped logistic chart cannot reach the wall at all. |
| Exponential $X$ tails and Lee-consistent wings | Structural | A modelling choice; finite strikes weakly identify the scales. |
| ATM level, skew and curvature | Analytic slice identities | Conditional on the numerically built slice; not raw-coefficient closed forms. |
| Calendar freedom | Not structural | Support-confined price rows, finite weight, optional; residual violations reported in desk units, not assumed away. |
| Display and publish | Gated above this note | A clean slice can still be withheld by the surface-level butterfly certificate (Note 02). |
| Economically plausible density | Not guaranteed | High order can fit noise or invent modes while remaining positive. |
| Atoms at zero or elsewhere | Not represented | The law is continuous; sharp continuous features only approximate mass points. |
| Unique or stable coefficients | Not guaranteed | Sparse quotes create nearly flat parameter directions; compare prices, handles and densities instead. |
| Market superiority | Not established here | The cases are deterministic synthetic approximation tests. |

Three further limitations matter in practice.

- **Near-wall conditioning.** As $A_R\uparrow1$, the martingale tail correction and its derivatives dominate. A technically feasible slice close to the wall is fragile, and the orthogonal retarget can fail.
- **Global modes.** A local-looking smile improvement can alter both endpoint scales because every Legendre polynomial reaches the endpoints. Fitted coefficient vectors are therefore poor objects for cross-date comparison.
- **Density inference.** Option prices smooth the density twice. Even a sub-vol-bp fit does not identify narrow density features; digitals, one-touches and event probabilities deserve separate stability tests.

---

## 16. What the implementation exploits

Quantile models, density-first option pricing, Legendre expansions and Lee's moment formula are classical ingredients. The useful contribution is their combination into a production coordinate system:

1. The endpoint skeleton in equation (4) turns positivity and two-sided tail regularity into a short unconstrained expansion, with only the genuine right-moment wall left hard.
2. The ATM identities in section "Exact ATM handles: level, digital mismatch and density" translate the distribution into actual trader handles, while the local null-space chart separates handle moves from remaining first-order shape directions.
3. The envelope cancellation in Theorem 1 lets the price Jacobian reuse the same cumulative integrals as pricing rather than differentiating an implicit strike root or rebuilding the slice per parameter.

None of these statements requires claiming that a generic calculus identity is new. The engineering value lies in choosing coordinates that make the identities cheap, testable and composable with the rest of the surface system.

---

## 17. Traceability

The figures and displayed numbers are deterministic outputs of `Docs/notes/figures/gen_lqd.py` and `Docs/notes/figures/gen_lqd_lecture.py`; LaTeX does not regenerate them automatically. Fresh generator values are the evidence used in this lecture. Some legacy benchmark fixtures intentionally retain older frozen coefficients as regression tripwires, so raw coefficients in those fixtures need not equal the current table.

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 4 — Claims, production modules and tests.**

| Claim | Mathematical anchor | Code and test anchors |
|---|---|---|
| Positive density, parity, monotone and convex benchmark calls | Proposition 1 | `backend/volfit/models/lqd/quadrature.py`; `backend/tests/test_lqd_pricing.py` |
| Legendre basis, endpoint scales and Lee maps | equations (13), (20)–(28) | `backend/volfit/models/lqd/basis.py`; `backend/tests/test_lqd_basis.py` |
| Logit quadrature, tail corrections and Hermite pricing | equations (15), (29)–(34) | `backend/volfit/models/lqd/quadrature.py`; `backend/volfit/models/lqd/interp.py`; `backend/tests/test_lqd_pricing.py` |
| ATM level, skew and curvature | equations (41)–(43) | `backend/volfit/models/lqd/atm.py`; `backend/tests/test_lqd_atm.py` |
| Local orthogonal chart and exact retarget | equations (45)–(46) | `backend/volfit/models/lqd/ortho.py`; `backend/tests/test_lqd_ortho.py` |
| Core objective, barrier, residual ordering and final rebuild | equations (48)–(49) | `backend/volfit/models/lqd/calibrate.py`; `backend/tests/test_lqd_calibrate.py` |
| Analytic Jacobian and fit agreement | Theorem 1 | `backend/volfit/models/lqd/jacobian.py`; `backend/tests/test_lqd_jacobian.py` |
| Support-confined price floor and symmetric surface repair | equation (59) | `backend/volfit/calib/calendar.py`; `backend/volfit/calib/symmetric.py`; `backend/tests/test_calendar_confinement.py`; certification case `symmetric_calendar` |
| Active-time annualization and normalized quote preparation | equations (1)–(3) | `backend/volfit/api/quotes.py`; `backend/volfit/api/service.py` |
| Fresh SVI and double-hat approximation cases | sections "Case file: an SPX-like smile" and "Case file: the density wears two hats" | `Docs/notes/figures/gen_lqd.py`; `Docs/notes/figures/lqd_numbers.json`; `backend/tests/benchmarks.py` |

---

## Appendix A. Hyperparameter atlas

Table 5 lists the controls native to LQD. Shared quote, band, calendar, var-swap, prior and filtering controls are derived in Notes 07, 08, 10, 13 and 15 and indexed in Note 00 rather than duplicated here. Application defaults are distinguished from low-level function defaults where they differ.

**Table 5 — LQD-native controls and constants.**

*Surfaced in FitSettings:*

| Knob | Default | Role |
|---|---|---|
| `nOrder` $N$ | $6$ | Highest Legendre degree; $N+1$ parameters. Schema range $4\le N\le16$. |
| `lqdCoords` | `logistic` | Optimization chart: raw `lr`, endpoint-speed, or the logistic tail coordinate that puts the $A_R$ wall out of reach; the fitted optimum is chart-independent to solver tolerance. |
| `regLambda` $\lambda$ | $10^{-6}$ | Application default for the high-order ridge. The direct `calibrate_slice` function defaults to zero. |
| `regPower` $r$ | $1.0$ | Ridge power in $\lambda n^{2r}a_n^2$ for $n\ge4$. |
| `barrierCenter` $c$ | 0.90 | Centre of the $A_R$ softplus barrier; it turns the fit before the hard wall. |
| `barrierScale` $s_b$ | 50.0 | Barrier steepness. |
| `weightScheme` | `equal` | Quote weights; the alternative `tv_density` scheme is described in Note 07. |

*Hidden numerical constants:*

| Knob | Default | Role |
|---|---|---|
| `Z_MAX` | $40.0$ | Half-width of the LQD *logit integration* grid. This is unrelated to the separate quote screen at four ATM standard deviations. |
| `N_POINTS` | $8001$ | Full reporting and diagnostic grid; odd so $z=0$ is a node. |
| `OPT_N_POINTS` | 2001 | Coarse grid used during optimization; accepted parameters are rebuilt at $8001$. |
| `EPS_AR` | $10^{-6}$ | Buffer in the code bound $A_R<1-{}$`EPS_AR` (raw charts; the logistic chart needs no buffer). |
| `_VEGA_FLOOR` $\eta$ | $10^{-4}$ | Floor in vega-normalized quote residuals. |
| Hermite–Newton steps | $4$ | Fixed safeguarded iterations after the linear strike-inversion seed. |
| `xtol/ftol/gtol` | $10^{-10}$ | Trust-region termination tolerances. |
| `max_nfev` | $4000$ | Residual-evaluation cap. |

---

## Appendix B. Performance and numerical notes

1. **Cache parameter-independent arrays.** The static logit grid, logistic factors and Legendre matrix are keyed by grid size and order. This removed roughly 40% of a repeated slice build and made the benchmark build about $1.7\times$ faster.
2. **Optimize coarse, report fine.** The 2001-node grid is already accurate well below the quote-fit budget for the supplied cases. Only the accepted parameters pay for the $8001$-node rebuild. This is an empirical error budget, not a theorem for every wild coefficient vector.
3. **Store derivatives with values.** Exact nodal $Q_z$ and $\mathcal A_z$ provide cubic-Hermite pricing, smoother off-grid Greeks and the interpolation data reused by the analytic Jacobian.
4. **Differentiate the cumulative objects.** Theorem 1 eliminates the strike-root derivative. The measured optimizer-core speed-ups in Figure 6 (per-order ratios annotated on the bars) compare warm cached runs with only analytic-supported residual blocks active.
5. **Stop below economic resolution.** Trust-region tolerances of $10^{-10}$ avoid iterations spent chasing numerical changes far below a volatility basis point. Tightening them to $10^{-15}$ did not change the displayed surface in the benchmark.

### B.1 Numerical qualifications

- The Black inversion accepts prices inside strict static bounds and brackets total variance over a finite interval. A failure returns a non-finite diagnostic rather than an arbitrage-free volatility by fiat.
- `martingale_check` repeats the same trapezoid-plus-tail approximation used to compute $\mu$. It is a valuable regression self-consistency check, not an independent truncation validation.
- Stable `logaddexp` protects the softplus itself, but forming $A_R=\exp(g(1))$ can overflow for an astronomically large trial vector. The production input pipeline and trust region keep ordinary fits far from that regime.
- The low-level calibration core assumes sorted aligned strikes, positive times and variances, non-negative weights and a feasible initializer. Quote preparation enforces those conditions before the core is called.

### B.2 SVI-JW provenance of the first case

The raw-SVI tuple in section "Case file: an SPX-like smile" is the image, at $\tau=0.5$, of the SVI-JW tuple

$$
(v,\psi,p,c,\widetilde v)=(0.0425,\,-0.25,\,0.75,\,0.25,\,0.034).
$$

For completeness, with $w_0=v\tau$,

$$
b=\frac{\sqrt{w_0}}{2}(p+c),\qquad
\rho=\frac{c-p}{c+p},\qquad
\chi=\rho-\frac{4\psi}{p+c}.
\tag{61}
$$

When $p+c>0$, $|\chi|<1$ and the denominator below is nonzero,

$$
\sigma_{\rm SVI}
=\frac{w_0-\widetilde v\tau}
{b\left((1-\rho\chi)/\sqrt{1-\chi^2}-\sqrt{1-\rho^2}\right)},
\tag{62}
$$

$$
m=\frac{\chi\sigma_{\rm SVI}}{\sqrt{1-\chi^2}},\qquad
a=\widetilde v\tau-b\sigma_{\rm SVI}\sqrt{1-\rho^2}.
\tag{63}
$$

This conversion only defines the synthetic target; no SVI property is used by the LQD construction.

---

## Appendix C. Reference implementation

*The transfer pack carries no source code; the NumPy/SciPy reference listing of the original appendix is restated here as a complete algorithm specification. On the fresh $N=6$ benchmark the listed procedure reproduces the production quantile, asset share and martingale shift to approximately $10^{-8}$ on the dense grid; its linear off-grid interpolation is intentionally simpler than production's Hermite interpolation.*

**Algorithm C.1 (Legendre basis).**
*Inputs:* maximum degree $n_{\max}$, evaluation points $x$.
*Output:* the matrix of values $P_0(x),\ldots,P_{n_{\max}}(x)$.
*Steps:* initialize $P_0(x)=1$ and $P_1(x)=x$; for $n=1,\ldots,n_{\max}-1$ apply the three-term recursion of equation (19), $P_{n+1}(x)=\bigl[(2n+1)\,x\,P_n(x)-n\,P_{n-1}(x)\bigr]/(n+1)$.

**Algorithm C.2 (Slice build).**
*Inputs:* coefficient vector $\theta=(L,R,a_2,\ldots,a_N)$ and a uniform logit grid $z_0<z_1<\cdots<z_{M-1}$ on $[-Z,Z]$ with spacing $\Delta z$ and an odd number of nodes so that $z=0$ is the middle node (production: $Z=40$, $M=8001$ dense / 2001 during optimization).
*Outputs:* percentiles $u$, normalized quantile $Q$, upper asset share $\mathcal A$, and martingale shift $\mu$ on the grid.
*Steps:*
1. Form $u_j=\Lambda(z_j)=1/(1+e^{-z_j})$ and the Legendre matrix of Algorithm C.1 at $x_j=1-2u_j$.
2. Evaluate the smooth part $g_j=(1-u_j)L+u_jR+\sum_{n=2}^{N}a_nP_n(x_j)$ (equation (13)).
3. Compute the endpoint scales $A_L=\exp\!\bigl(L+\sum_{n\ge2}a_n\bigr)$ and $A_R=\exp\!\bigl(R+\sum_{n\ge2}(-1)^na_n\bigr)$ (equations (20)–(21)). If $A_R\ge1$, refuse the vector: the forward is infinite (equation (24)). In the pedagogical reference this is a hard rejection; the shipped chart makes the wall unreachable by passing $A_R$ through a logistic instead.
4. Build the centred primitive $\overline Q$ by cumulative Simpson integration of $e^{g}$ over the grid, then subtract its value at the middle node so that $\overline Q(0)=0$ (equation (16)).
5. Form the mass integrand $e^{\overline Q_j}u_j(1-u_j)$, integrate it by the trapezoidal rule over the grid, and add the two analytic endpoint corrections $e^{\overline Q(Z)-Z}/(1-A_R)$ on the right and $e^{\overline Q(-Z)-Z}/(1+A_L)$ on the left (equation (34)). Call the total $M_{\rm tot}$; set $\mu=-\log M_{\rm tot}$ and $Q_j=\overline Q_j+\mu$ (equation (29)).
6. Form the asset-share integrand $e^{Q_j}u_j(1-u_j)$ and accumulate it by cumulative Simpson integration from the right endpoint toward the left (a reverse cumulative integral), then add the right tail correction $e^{Q(Z)-Z}/(1-A_R)$ to every node so that $\mathcal A(z)$ approximates the full upper integral of equation (30).

**Algorithm C.3 (Call pricing).**
*Inputs:* a log-strike $k$ and the grid arrays $z,u,Q,\mathcal A$ from Algorithm C.2.
*Output:* the normalized call price $C(k)$.
*Steps:*
1. Solve the strike root by piecewise-linear interpolation of $z$ as a function of $Q$: $z_k$ such that $Q(z_k)=k$. (Production replaces both interpolations in this algorithm by the cubic-Hermite forms with exact nodal derivatives $Q_z=e^g$ and $\mathcal A_z=-e^Qu(1-u)$, seeded linearly and refined by four safeguarded Newton steps.)
2. Evaluate the asset leg $\mathcal A(z_k)$ by interpolation on the grid.
3. Evaluate the cash leg in log space as $\exp\bigl(k-\log(1+e^{z_k})\bigr)$, which equals $e^k(1-\Lambda(z_k))$ exactly in real arithmetic. The log-space form is required because past $z_k\approx36.7$ the double-precision logistic $\Lambda(z_k)$ rounds to exactly one, $1-\Lambda(z_k)$ collapses to zero, and the far wing of the price curve steps visibly.
4. Return $C(k)=\mathcal A(z_k)-\exp\bigl(k-\log(1+e^{z_k})\bigr)$ (equation (31)).

---

## References

1. D. Breeden and R. Litzenberger. Prices of state-contingent claims implicit in option prices. *Journal of Business*, 51(4):621–651, 1978.
2. R. W. Lee. The moment formula for implied volatility at extreme strikes. *Mathematical Finance*, 14(3):469–480, 2004.
3. J. Gatheral. *The Volatility Surface: A Practitioner's Guide*. Wiley, 2006.
4. J. Gatheral and A. Jacquier. Arbitrage-free SVI volatility surfaces. *Quantitative Finance*, 14(1):59–71, 2014.
5. V. Strassen. The existence of probability measures with given marginals. *Annals of Mathematical Statistics*, 36(2):423–439, 1965.
6. P. Carr and D. Madan. Towards a theory of volatility trading. In *Volatility*, Risk Books, 1998.



