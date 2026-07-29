# SVI-JW: One Hyperbola, Two Languages

**Note 02 — Raw geometry, trader coordinates, and honest arbitrage control · lecture edition ("one hyperbola, two languages" — alternative draft) · converted from 02_svi_jw_rewrite.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** SVI draws one expiry's price-implied total variance as a tilted hyperbola. That single picture explains both its durability and its limitations: the curve is smooth, strictly convex in log-moneyness, linear in both wings, cheap to fit, and unable to turn twice. The raw coefficients are excellent computational coordinates but poor market language. SVI-JW reads the same curve through five functionals instead: ATM variance, the ATM slope of total volatility, two normalized wing coefficients, and minimum variance. We build the raw formula from a symmetric toy, derive its geometry, define the JW handles in their natural units, and prove the full image of the coordinate map. Away from the ATM-at-the-minimum stratum the inverse is unique; on that stratum the five handles omit curvature and infinitely many raw slices share them. The inverse denominator is quadratic in the distance to this singular set, which explains its poor conditioning. We then separate four statements that are often conflated: convexity of total variance, positive/Lee-clean wings, non-negative Black density, and calendar ordering. In particular, the two production screens are not a butterfly certificate: the Axel Vogt slice has positive minimum variance and Lee coefficient 0.174, yet reaches $g=-0.033$; production therefore measures every displayed slice with an explicit density certificate rather than trusting the screens. Finally we derive the calibration maps — the historical unconstrained raw chart and the structural chart that now fits by default, whose coordinates are the certified quantities themselves — together with the analytic Jacobian, trace the optional residual blocks, and run a production JW→raw→fit→JW laboratory round trip with $5.6\times10^{-13}$ volatility-basis-point maximum error. Eight generated figures make the geometry, singularity, arbitrage gap, calibration check, speed result, and one-hyperbola rigidity visible rather than merely asserted.

**Contents**

1. One curve, two languages
2. Building the raw hyperbola
3. Reading the smile: the five JW handles
4. Changing coordinates, and where the chart tears
5. Convex total variance is not an arbitrage certificate
6. How production fits the slice
7. Laboratory case: JW to raw to fit to JW
8. Where one hyperbola stops being enough
9. The honest product and mathematical contract
10. Traceability
— Appendix A. Control atlas · Appendix B. Performance and numerical qualifications · Appendix C. Executable reference maps · References

---

## 1. One curve, two languages

A desk rarely asks for "more $b$" or "less $m$." It asks where ATM volatility is, how steeply the smile leaves ATM, how heavy the put wing is, and where the smile bottoms. An optimizer has almost the opposite preference: it wants a formula that evaluates in one pass, differentiates without numerical noise, and behaves sensibly outside the quoted strikes. Raw SVI and SVI-JW are the two languages that serve those two jobs.

The underlying object is not implied volatility itself. Fix an expiry date $T$, let $F_T$ be its forward, and write

$$
k=\log\frac{K}{F_T},\qquad w(k)=\text{Black implied total variance at }k. \tag{1}
$$

The normalized Black price depends on $k$ and $w$, so $w$ is recovered from a price without first choosing an annualization clock. Vol-Fitter keeps two clocks distinct:

$$
I_t(k)=\sqrt{\frac{w(k)}{t}},\qquad
I_\tau(k)=\sqrt{\frac{w(k)}{\tau}}. \tag{2}
$$

Here $t$ is calendar year fraction and $I_t$ is the ordinary market IV; $\tau$ is the event-weighted variance time of Note 11 and $I_\tau$ is the working IV used by the fit and display paths when that clock is enabled. At fixed price, changing the clock changes the annualized number, not $w$. When events are disabled, $\tau=t$. Unless qualified, $I$ below means the working quantity $I_\tau$.

Raw SVI postulates the following.

**Central equation.**

$$
w(k)=a+b\left\{\rho(k-m)+\sqrt{(k-m)^2+s^2}\right\}. \tag{3}
$$

The width is denoted by $s$ so that $\sigma$ remains available for implied volatility; the production dataclass calls this field `sigma`. The standard raw tuple is $(a,b,\rho,m,s)$ with

$$
b>0,\qquad |\rho|<1,\qquad s>0. \tag{4}
$$

Raw SVI was introduced by Gatheral and became a market standard because its wings are linear in $|k|$ and the formula is unusually tractable [Gatheral2004, GatheralJacquier2014].

> **Invariants protected in this note.**
> 1. Every finite optimizer vector maps to a smooth raw hyperbola satisfying equation (4); positivity and no-arbitrage require additional work.
> 2. The JW handles are exact functionals of that same $w$, not a second model. Their regular inverse is exact only on the domain proved in Theorem 1.
> 3. The coded minimum and Lee rows are configurable soft screens. They do not certify non-negative density, and the calendar rows do not certify global cross-expiry order. Non-negative density on the traded range is instead measured by a separate certificate that gates every displayed and published slice (section "Convex total variance is not an arbitrage certificate").
> 4. Production fits and stores raw SVI; by shipped default the optimizer works in the structural chart of the section "The structural chart: fitting in the screened coordinates", with the unconstrained raw chart retained as explicit rollback. JW remains an analytical and reading coordinate system: there is no runtime five-handle entry, bump, or export workflow, though the guarded converter and the desk-unit ticket that any such workflow must sit behind are shipped and test-locked (section "Changing coordinates, and where the chart tears").

The order of the note follows the mathematics rather than the software menu. We first understand the hyperbola, then learn to read it in JW coordinates, then ask when it is a legitimate option smile, and only then fit it.

## 2. Building the raw hyperbola

Start with the symmetric toy

$$
w(k)=a+b\sqrt{k^2+s^2}. \tag{5}
$$

The constant $a$ lifts the curve, $b$ sets the far-wing steepness, and $s$ rounds the corner. Replacing $k$ by $k-m$ translates the rounded core. Adding $b\rho(k-m)$ tilts the two wings in opposite directions. This gives equation (3). The construction is simple, but it already warns us that $m$ is merely the centre of the square root: after the tilt, it is not the minimum.

Put

$$
x=k-m,\qquad r=\sqrt{x^2+s^2},\qquad q=\sqrt{1-\rho^2}. \tag{6}
$$

These are the only local abbreviations needed for the raw geometry.

**Proposition 1 (Geometry of one raw slice).** Under equation (4), $w$ is strictly convex and has one minimum:

$$
w'(k)=b\left(\rho+\frac{x}{r}\right),\qquad
w''(k)=\frac{bs^2}{r^3}>0, \tag{7}
$$

$$
k_\star=m-\frac{s\rho}{q},\qquad
w_\star=a+bsq. \tag{8}
$$

Its positive left-wing coefficient and right-wing slope are

$$
\beta_L=b(1-\rho),\qquad \beta_R=b(1+\rho), \tag{9}
$$

in the sense that

$$
w(k)=\beta_L|k|+O(1)\quad(k\to-\infty),\qquad
w(k)=\beta_R k+O(1)\quad(k\to+\infty). \tag{10}
$$

The signed derivative on the left tends to $-\beta_L$; calling $\beta_L$ a "left slope" always means its positive magnitude.

*Proof.* Differentiation gives equation (7). Since $b,s>0$, the second derivative is positive for every finite $k$, so a stationary point is the unique global minimum. Solving $w'=0$ gives $x=-s\rho/q$, hence $r=s/q$ and equation (8). Finally $r=|x|+o(1)$ in either wing, which yields equation (10). ∎

> **Figure 1 — Anatomy of one raw slice (figure not included in this pack).** One hyperbola carries the entire model. The total-variance slice approaches two straight asymptotes (A), its derivative makes one smooth transition from $-\beta_L$ to $\beta_R$ (B), and its curvature is positive everywhere (C). The last fact is a geometric statement about $w$; it is not yet a statement about convexity of option prices. — Panel A plots a raw SVI total-variance slice over log-moneyness together with its two asymptotic rays: the curve hugs the left ray of slope magnitude $\beta_L$ and the right ray of slope $\beta_R$ far from the money and rounds smoothly through its single vertex near the core. Panel B plots the first derivative $w'(k)=b(\rho+x/r)$, a single monotone S-shaped transition from the plateau $-\beta_L$ at $k\to-\infty$ up to $+\beta_R$ at $k\to+\infty$, with $s$ controlling how fast the transition happens. Panel C plots the curvature $w''(k)=bs^2/r^3$, one strictly positive bump peaked at $k=m$ and decaying to zero in both wings — positive everywhere, which is the model's structural convexity of $w$, deliberately distinguished in the caption from price convexity.

The raw parameters now have a precise, limited interpretation. Increasing $a$ is a vertical translation. Increasing $m$ translates the square-root core. But $b$, $\rho$, and $s$ are coupled: $b$ changes the minimum as well as both wings, $\rho$ changes the minimum location as well as the two wing coefficients, and $s$ changes both the depth and the breadth of the core.

> **Figure 2 — Raw-parameter moves (figure not included in this pack).** Raw parameters are computational coordinates, not independent market observables. Only $a$ is a pure vertical move and only $m$ is a pure translation of the square-root core. The other perturbations visibly alter several features at once, which is the motivation for a second coordinate chart. — The figure shows one base slice perturbed one raw parameter at a time. The $a$-panel shows a rigid vertical shift and the $m$-panel a rigid horizontal translation of the rounded core. The $b$-panel shows both wings steepening *and* the minimum rising together; the $\rho$-panel shows the tilt redistributing steepness between the wings while moving the minimum's location sideways; the $s$-panel shows the core simultaneously deepening and broadening. The takeaway is that three of the five raw coordinates each move several market-visible features at once.

> **Heuristic.** Think of raw SVI as a rounded hinge. Far away, the hinge has forgotten its rounding and exposes two straight rays. Near the centre, $s$ decides how quickly one ray turns into the other. The tilt $\rho$ redistributes a fixed overall steepness between the put and call sides. This picture is more useful than memorizing five coefficient descriptions, but it still does not tell a trader the ATM level or ATM skew directly.

## 3. Reading the smile: the five JW handles

The clean way to introduce SVI-JW is to forget the raw coefficients for a moment and measure the curve itself. Let

$$
w_0=w(0)>0,\qquad w_\star=\min_k w(k). \tag{11}
$$

**Definition 1 (SVI-JW functionals).** At variance clock $\tau>0$, the jump-wing coordinates of a smooth raw slice are

$$
v=\frac{w_0}{\tau},\qquad
\psi=\left.\frac{\mathrm{d}\sqrt{w(k)}}{\mathrm{d} k}\right|_{k=0},\qquad
p=\frac{\beta_L}{\sqrt{w_0}},\qquad
c=\frac{\beta_R}{\sqrt{w_0}},\qquad
\widetilde v=\frac{w_\star}{\tau}. \tag{12}
$$

This definition separates intrinsic shape from annualization. The middle three handles $\psi,p,c$ depend only on the price-derived $w$ and are unchanged if the clock changes. Only the annualized levels $v$ and $\widetilde v$ rescale. Production uses $\tau$; an external calendar-market convention can replace it by $t$ without changing the underlying slice.

The displayed meanings follow immediately:

$$
I(0)=\sqrt v,\qquad I'(0)=\frac{\psi}{\sqrt\tau},\qquad
\beta_L=p\sqrt{v\tau},\qquad \beta_R=c\sqrt{v\tau},\qquad
I(k_\star)=\sqrt{\widetilde v}\quad\text{if }\widetilde v\ge0. \tag{13}
$$

Thus $\psi$ is the ATM slope of *total volatility* $\sqrt w$, or equivalently $\sqrt\tau$ times the working-IV slope. The wing handles are normalized total-variance coefficients, not slopes of the IV plot.

Substituting equation (3) into the functional definition gives the classical raw-to-JW formulas [GatheralJacquier2014, Sec. 3.3]:

$$
\begin{aligned}
v&=\frac{a+b\{-\rho m+\sqrt{m^2+s^2}\}}{\tau},\\
\psi&=\frac{b}{2\sqrt{w_0}}
       \left(\rho-\frac{m}{\sqrt{m^2+s^2}}\right),\\
p&=\frac{b(1-\rho)}{\sqrt{w_0}},\qquad
c=\frac{b(1+\rho)}{\sqrt{w_0}},\\
\widetilde v&=\frac{a+bs\sqrt{1-\rho^2}}{\tau}.
\end{aligned} \tag{14}
$$

**Table 1 — The five handles use three related but distinct languages: annualized variance, total-volatility skew, and normalized total-variance wings. Keeping those units explicit prevents nearly every common JW misreading.**

| Handle | Functional definition | What is visible on a chart | Common mistake |
|---|---|---|---|
| $v$ | $w(0)/\tau$ | ATM IV is $\sqrt v$ | treating $v$ as volatility |
| $\psi$ | $(\sqrt w)'(0)$ | IV tangent is $\psi/\sqrt\tau$ | calling $\psi$ the plotted slope |
| $p$ | $\beta_L/\sqrt{w_0}$ | put coefficient is $p\sqrt{v\tau}$ | reading it on the IV axis |
| $c$ | $\beta_R/\sqrt{w_0}$ | call coefficient is $c\sqrt{v\tau}$ | reading it on the IV axis |
| $\widetilde v$ | $w_\star/\tau$ | minimum IV is $\sqrt{\widetilde v}$ if non-negative | assuming positivity from the name |

> **Figure 3 — The five JW handles on two charts (figure not included in this pack).** The five JW handles live on two charts. ATM level, ATM tangent, and minimum are naturally read in working IV (A). The put and call handles belong to the asymptotic total-variance rays (B). Plotting all five on one IV panel would give the wing handles units they do not have. — Panel A shows the working-IV smile with three annotations: the ATM level $\sqrt v$ marked at $k=0$, the ATM tangent line of slope $\psi/\sqrt\tau$, and the smile minimum at height $\sqrt{\widetilde v}$ located at $k_\star$. Panel B shows the same slice in total variance with its two asymptotic rays drawn in, of slopes $p\sqrt{v\tau}$ (put side) and $c\sqrt{v\tau}$ (call side) — the natural home of the wing handles. The two panels make the unit separation of Table 1 graphic: three handles read on the IV chart, two on the total-variance chart.

The name "jump-wing" is historical trader vocabulary; the five numbers are not parameters of a jump process. The parametrization, inspired by a Tim Klassen coordinate set, was documented alongside the other SVI forms by Gatheral and Jacquier [GatheralJacquier2014]. Its value is descriptive: it turns one opaque coefficient vector into a level, a local slope, two tails, and a floor.

## 4. Changing coordinates, and where the chart tears

Reading JW from raw is just evaluation. Going the other way is more interesting because the five measurements must reconstruct a whole hyperbola. Let

$$
w_0=v\tau,\qquad
\chi=\frac{m}{\sqrt{m^2+s^2}}. \tag{15}
$$

The wings first determine the scale and tilt:

$$
b=\frac{\sqrt{w_0}}{2}(p+c),\qquad
\rho=\frac{c-p}{c+p}. \tag{16}
$$

The ATM skew then determines the normalized displacement:

$$
\chi=\rho-\frac{4\psi}{p+c}. \tag{17}
$$

For $|\chi|<1$, write

$$
D(\rho,\chi)=
\frac{1-\rho\chi}{\sqrt{1-\chi^2}}-\sqrt{1-\rho^2}. \tag{18}
$$

The remaining three raw coordinates are

$$
s=\frac{(v-\widetilde v)\tau}{bD(\rho,\chi)},\qquad
m=\frac{\chi s}{\sqrt{1-\chi^2}},\qquad
a=\widetilde v\tau-bs\sqrt{1-\rho^2}. \tag{19}
$$

The derivation is only the difference between ATM and minimum variance. Indeed, $\sqrt{m^2+s^2}=s/\sqrt{1-\chi^2}$, so subtracting $w_\star=\widetilde v\tau$ from $w_0=v\tau$ produces $bsD$.

The factor $D$ has a useful geometric form. Set $\rho=\sin\alpha$ and $\chi=\sin\gamma$, with both angles in $(-\pi/2,\pi/2)$. Then

$$
D(\rho,\chi)
=\frac{1-\cos(\alpha-\gamma)}{\cos\gamma}\ge0, \tag{20}
$$

and equality holds exactly when $\chi=\rho$. This one observation supplies the domain and the singularity.

**Theorem 1 (The full smooth, nondegenerate JW image).** Fix $\tau>0$ and restrict raw SVI to $b>0$, $|\rho|<1$, $s>0$, and $w_0>0$.

1. A JW point has a unique regular inverse if and only if

$$
v>0,\qquad p>0,\quad c>0,\qquad
-\frac p2<\psi<\frac c2,\qquad
\psi\ne0,\qquad \widetilde v<v. \tag{21}
$$

On this set, equations (16)–(19) return that inverse.

2. The image also contains the singular stratum

$$
v>0,\qquad p>0,\quad c>0,\qquad
\psi=0,\qquad \widetilde v=v. \tag{22}
$$

Every point on this stratum is represented by infinitely many raw slices. There are no other smooth, nondegenerate points in the image.

*Proof.* If $p,c>0$, equation (16) gives $b>0$ and $\rho\in(-1,1)$. Conversely, a smooth raw slice with $b>0$ and $|\rho|<1$ has $p,c>0$. From equation (17),

$$
\begin{aligned}
|\chi|<1
&\iff \rho-1<\frac{4\psi}{p+c}<\rho+1\\
&\iff -\frac p2<\psi<\frac c2,
\end{aligned}
$$

where $(\rho-1)(p+c)=-2p$ and $(\rho+1)(p+c)=2c$. This is exactly the condition for finite $m/s$.

By equation (20), $D>0$ precisely when $\chi\ne\rho$, which by equation (17) is $\psi\ne0$. The first equation in (19) then gives $s>0$ precisely when $\widetilde v<v$. All remaining coordinates are unique algebraic consequences, proving the regular statement and its converse.

If $\psi=0$, then $\chi=\rho$. On a raw slice this is equivalent to $k_\star=0$ by equation (8); hence ATM is the minimum and $\widetilde v=v$. Conversely, fix any $v,p,c$ satisfying equation (22). Equations (16) determine $b,\rho$. For *any* $s>0$, set

$$
m=\frac{\rho s}{\sqrt{1-\rho^2}},\qquad
a=v\tau-bs\sqrt{1-\rho^2}. \tag{23}
$$

Then $k_\star=0$, $w_\star=w_0=v\tau$, and all five JW functionals agree. The free width proves non-identification. The preceding necessity arguments exclude every other smooth nondegenerate case. ∎

> **Figure 4 — The inverse denominator and the singular stratum (figure not included in this pack).** The inverse denominator measures an angular separation on the unit semicircle (A). When the two unit vectors coincide, $\psi=0$ and the chart loses width information. Three visibly different raw bodies can then share the identical tuple $(v,0,p,c,v)$ (B): JW fixes ATM and both asymptotic rays but omits curvature at the common minimum. — Panel A draws the unit semicircle with the two unit vectors $u_\rho=(\rho,\sqrt{1-\rho^2})$ and $u_\chi=(\chi,\sqrt{1-\chi^2})$; the denominator $D$ of equation (20) is proportional to $1-\cos$ of the angle between them, so it closes to zero exactly when the vectors coincide, which by equation (17) is the $\psi=0$ case. Panel B overlays three raw slices constructed by the singular family of equation (23) with three different widths $s$: all three share the same ATM level, the same minimum (at ATM), and the same two asymptotic rays, yet turn through the bottom with visibly different sharpness. The lost coordinate is precisely the vertex curvature.

### 4.1 Boundaries and conditioning

The theorem distinguishes *representability* from *regular invertibility*. The most useful boundary cases are collected here.

**Table 2 — The regular domain is open for a reason. Equality cases are not one generic failure mode; they lead to distinct degeneracies.**

| JW boundary | What happens |
|---|---|
| $\psi=-p/2$ or $\psi=c/2$ | $\lvert\chi\rvert=1$; no finite smooth displacement $m/s$ |
| $\psi=0$, $\widetilde v=v$ | representable, but infinitely many raw widths |
| $\psi=0$, $\widetilde v<v$ | no finite smooth raw slice |
| $\psi\ne0$, $\widetilde v=v$ | $s=0$, the nonsmooth V-shaped boundary |
| $p=0$ or $c=0$ | $\lvert\rho\rvert=1$, a one-wing-degenerate boundary |
| $p=c=0$ | $b=0$, the constant-slice boundary |
| $v=0$ | the normalization by $\sqrt{w_0}$ is undefined |
| $\widetilde v<0$ inside the regular domain | algebraically invertible, financially unusable |

Near $\chi=\rho$, the angular gap is quadratic:

$$
D(\rho,\chi)
\sim \frac{(\chi-\rho)^2}{2(1-\rho^2)^{3/2}},
\qquad \chi\to\rho. \tag{24}
$$

Because $\chi-\rho=-4\psi/(p+c)$, the denominator is $O(\psi^2)$. Holding $v-\widetilde v>0$ fixed therefore sends $s$ to infinity as $\psi\to0$; a finite approach to the singular family requires $v-\widetilde v=O(\psi^2)$. The limiting ratio is precisely the curvature information missing from the five handles.

The form (18) also subtracts nearly equal numbers. An exactly equivalent, more stable evaluation is

$$
D(\rho,\chi)=
\frac{(\rho-\chi)^2+
\left(\sqrt{1-\rho^2}-\sqrt{1-\chi^2}\right)^2}
{2\sqrt{1-\chi^2}}, \tag{25}
$$

with the square-root difference rationalized in code. This removes avoidable cancellation but cannot restore a coordinate that the handles do not identify.

> **Caution.** The production `jw_to_raw` function implements the direct formulas without domain guards; it is the fast path for callers that already hold a regular-domain point. Inputs strictly outside the skew band typically generate NaNs, skew-band endpoints create zero denominators, and $\widetilde v\ge v$ returns a degenerate or negative width. Production therefore also ships a guarded converter, `jw_to_raw_checked`, which is this section made executable: it validates every inequality of equation (21) in the order the theorem establishes them, rejects the singular stratum (22) explicitly (no numerical rearrangement can select the missing curvature), evaluates the denominator in the cancellation-resistant form (25), and on failure raises a structured domain error whose machine-readable code names the violated inequality — six codes, one per row of the theorem's domain — instead of a case-dependent NaN. Any user-facing five-handle workflow is required to sit behind it.

The checked converter answers "is this JW point a smile?"; a desk also needs the converse reading "what does this smile quote as?". A shipped desk-unit ticket converts any fitted slice into the instruments actually traded: ATM volatility, 25- and 10-delta risk reversals and butterflies with strikes solved on the model smile via the forward Black delta, the two *actual* asymptotic wing coefficients (the moment objects of the section "Convex total variance is not an arbitrage certificate", not the normalized $p,c$), and the var-swap volatility. A companion bump row re-reads the same ticket after a relative forward error $\mathrm{d}F/F$: a wrong forward shifts every log-moneyness in unison and is easily misread as skew or wing movement, and the ticket shows exactly which desk quantities it moves. Together the two functions are the conversion layer any future JW entry workflow must pass through; both are test-locked now rather than designed later.

## 5. Convex total variance is not an arbitrage certificate

The phrase "convex smile" hides two different derivatives. Raw SVI has $w''(k)>0$ by construction. A butterfly spread, however, tests the second derivative of an *option price with respect to strike*. Those statements are not equivalent.

It helps to keep four levels separate.

**Table 3 — Four increasingly strong meanings of "valid." The first is hard; the second became hard when the default fit chart moved to structural coordinates (section "The structural chart: fitting in the screened coordinates"); the last two require conditions beyond a single coefficient box, and the third is measured by an explicit certificate at the display gate.**

| Level | Mathematical statement | Production status |
|---|---|---|
| Raw structure | $b>0$, $\lvert\rho\rvert<1$, $s>0$ | hard reparametrization for finite latent coordinates |
| Positive/Lee interior | $w_\star>0$, $\beta_L<2$, $\beta_R<2$ | hard under the default structural chart ($w_\star>0$, $\max(\beta_L,\beta_R)<1.95$); soft screens under the raw rollback chart |
| Butterfly clean | non-negative Black density and correct call boundary | measured by the display certificate; not certified by the two core rows |
| Calendar clean | $w_{T_1}(k)\le w_{T_2}(k)$ for every $k$ when $T_1<T_2$ | finite-weight rows on selected grids; not structural |

### 5.1 The exact one-slice criterion

For normalized strike $y=e^k$, let $B(k,w(k))$ be the normalized Black call and set

$$
d_\pm(k)=-\frac{k}{\sqrt{w(k)}}\pm\frac{\sqrt{w(k)}}{2}. \tag{26}
$$

**Proposition 2 (Durrleman's density factor).** Let $w\in C^2(\mathbb{R})$ be strictly positive. The strike density implied by the Black call is

$$
\frac{\partial^2 B}{\partial y^2}
=\frac{\varphi(d_-(k))}{y\sqrt{w(k)}}\,g(k), \tag{27}
$$

where

$$
g(k)=
\left(1-\frac{k w'(k)}{2w(k)}\right)^2
-\frac{w'(k)^2}{4}\left(\frac{1}{w(k)}+\frac14\right)
+\frac{w''(k)}{2}. \tag{28}
$$

Consequently density non-negativity is equivalent to $g(k)\ge0$ for every $k$. A standard no-butterfly smile additionally needs the far-call boundary

$$
\lim_{k\to+\infty}d_+(k)=-\infty, \tag{29}
$$

equivalently the normalized call tends to zero at infinite strike.

*Proof.* Twice differentiating the Black call with the chain rule gives equation (27); the prefactor is strictly positive, so its sign is the sign of $g$. The boundary is separate because a non-negative local density need not have the correct total mass or first moment. This is the standard Durrleman/Gatheral–Jacquier criterion [Durrleman2010, GatheralJacquier2014]. ∎

For raw SVI, Lee's wing bound appears directly in $g$.

**Proposition 3 (Raw-SVI tail limits).** For a structurally valid positive raw slice,

$$
\lim_{k\to-\infty}g(k)=\frac{4-\beta_L^2}{16},\qquad
\lim_{k\to+\infty}g(k)=\frac{4-\beta_R^2}{16}. \tag{30}
$$

Moreover equation (29) holds exactly when $\beta_R<2$; at $\beta_R=2$, raw SVI has $d_+(k)\to0$.

*Proof.* In either wing $w\sim\beta|k|$, $|w'|\to\beta$, and $w''\to0$. The first term of equation (28) tends to $1/4$ and the second to $\beta^2/16$, giving equation (30). On the right,

$$
d_+(k)=\sqrt{k}\left(-\frac{1}{\sqrt{\beta_R}}
+\frac{\sqrt{\beta_R}}{2}\right)+o(\sqrt{k}),
$$

whose coefficient is negative exactly for $\beta_R<2$. When $\beta_R=2$, the leading terms cancel and the raw linear asymptotic gives the stated zero limit. ∎

The strict inequalities are the clean theoretical interior. The production hinges use the weak closure because numerical penalties need a boundary. Similarly, the theoretical positive-smile condition is $w_\star>0$. A smooth nondegenerate raw slice touching zero at one finite strike is not a harmless edge case; it lies outside the butterfly-free raw-SVI domain [MartiniMingone2022]. The coded condition $w_\star\ge0$ is a screen, not a theorem.

### 5.2 What the two coded screens look like in JW coordinates

**Proposition 4 (Core screens in JW units).** The minimum and Lee quantities satisfy

$$
w_\star=\widetilde v\tau,\qquad
\max(\beta_L,\beta_R)=\max(p,c)\sqrt{v\tau}. \tag{31}
$$

Thus the production weak screens are $\widetilde v\ge0$ and $\max(p,c)\sqrt{v\tau}\le\beta_{\max}$, with default $\beta_{\max}=1.95$.

*Proof.* The first identity is the definition of $\widetilde v$. The second follows from $p=\beta_L/\sqrt{w_0}$, $c=\beta_R/\sqrt{w_0}$, and $w_0=v\tau$. ∎

The default cap deserves one more sentence, because its value is a lesson in hinge design. Proposition 3 shows that the boundary ray $\beta_R=2$ is itself broken: the far-call boundary condition fails there and the tail limit of $g$ is zero. A hinge whose cap sits exactly at $2$ charges nothing precisely on that broken boundary, so an optimizer pressed by the data can park a wing at $2.0000$ and pay no penalty — which a live SPY expiry was later found doing. The shipped cap is therefore buffered strictly inside Lee's bound, at $\beta_{\max}=1.95$; refitting the incident slice under the buffer moved the displayed smile by well under a tenth of a volatility basis point, and the boundary trap is locked as a named certification case.

The screens are necessary ingredients, not sufficient ones. The sharpest way to see the gap is a slice that passes both.

> **Example — Case file: the slice that looks innocent.** Axel Vogt's counterexample, reproduced as Example 3.1 by Gatheral and Jacquier [GatheralJacquier2014], has
>
> $$
> a=-0.0410,\quad b=0.1331,\quad \rho=0.3060,\quad
> m=0.3586,\quad s=0.4153.
> $$
>
> Its minimum total variance is 0.0116, and its larger Lee coefficient is only 0.174. Both production core screens pass comfortably. Nevertheless $g$ reaches $-0.033$ near $k=0.88$, so the Black density is negative there. Strict convexity of $w$ has not protected strike convexity of the call price.
>
> The story now has a production ending. A slice like this no longer reaches a user unflagged: the display certificate below samples $g$ densely on the traded range and fails it, readiness reports the failure, the publish gate refuses the surface, and with automatic repair enabled the fitter re-solves once with a belly hinge and keeps the result only if it certifies. The screens still pass — that is the permanent lesson — but they are no longer the last line.

> **Figure 5 — The counterexample: screens pass, density fails (figure not included in this pack).** The counterexample is the note's main honesty check. Its positive, smooth, strictly convex total variance passes the minimum and Lee screens (A), while Durrleman's density factor becomes negative (B). The cheap screens control common failures; they do not characterize the butterfly-free domain. — Panel A plots the Vogt slice's total variance: positive everywhere (minimum 0.0116), strictly convex, with wing coefficients maxing out at 0.174, far below the buffered cap of 1.95 — both coded screens pass with a wide margin. Panel B plots its Durrleman factor $g(k)$: both tails settle toward positive limits of about $0.25$ (per equation (30)), yet the interior dips below zero, reaching $-0.033$ near $k=0.88$. The negative dip is a genuine butterfly arbitrage sitting between two perfectly clean tails.

Martini and Mingone give a full characterization of the no-butterfly raw-SVI domain [MartiniMingone2022]. It is exact but not a single short inequality: the practical test involves parameter rescaling, root finding, and numerical minimization. Vol-Fitter's current raw-SVI calibrator does not implement that certified domain. It instead bounds, certifies on the traded range, repairs, measures, and projects through six separate layers.

1. **Core screens.** Every fit appends the two minimum/Lee hinge rows of equation (32) below.
2. **The display certificate.** Every slice a user sees is re-measured by a dense sampling of Durrleman's $g$ — 801 points across the traded strike range, from the closed-form derivatives — before it counts as ready. A failing slice fails readiness, and the publish gate refuses the surface outright. This is a certificate about the sampled grid on the traded range, stated as such; it is the layer that catches the counterexample below.
3. **Automatic repair.** When the certificate fails, the fitter re-solves once with an explicit belly hinge and keeps the repair only if the repaired slice certifies. Clean first fits never see a second solve. The repair is currently implemented for SVI only.
4. **Optional extrapolation enforcement.** With `extrapEnforce` on, tapered rows penalize sampled $g<0$, calendar crossings against the previous displayed slice, and inconsistent wing order in the extrapolated region. Only this small block is finite-differenced.
5. **Advisory diagnostics.** The Quality path reports remaining extrapolated-region violations using model-native quantities: closed-form raw SVI derivatives here, structural density for LQD, and the SIV diagnostic for that family.
6. **Publish-time projection.** The export path can apply the model-agnostic discrete wing projection of Note 09 while leaving the fitted core fixed.

No item in that list silently upgrades the raw fit to a global certificate on the whole line. The exact criterion remains Proposition 2; the production layers state what they sample or alter, and the certificate scopes its promise to the traded range where the money is.

The two core residuals are

$$
r_{\rm core}=W
\begin{pmatrix}
[-w_\star]_+\\[2pt]
[\max(\beta_L,\beta_R)-\beta_{\max}]_+
\end{pmatrix},
\qquad [x]_+=\max(x,0), \tag{32}
$$

with default residual multiplier $W=1000$. Because least squares squares residuals, the objective coefficient is $W^2$. The two components do not even have the same natural unit: one is total variance and one is a wing coefficient. $W$ is therefore an engineering multiplier, not a financial variance weight. At a strictly feasible point both rows and their Jacobian rows vanish, so the penalized and unpenalized objectives agree locally. That fact does *not* imply identical optimizer paths or bitwise identical fits for arbitrary data.

## 6. How production fits the slice

The optimizer never works directly with a bounded raw vector: it fits in an unconstrained chart of $\mathbb{R}^5$ and maps back. Production ships two such charts. The historical *raw chart* receives $\theta\in\mathbb{R}^5$ and maps

$$
a=\theta_1,\qquad
b=\operatorname{softplus}(\theta_2),\qquad
\rho=\tanh(\theta_3),\qquad
m=\theta_4,\qquad
s=e^{\theta_5}. \tag{33}
$$

For every finite $\theta$ in exact arithmetic, $b>0$, $|\rho|<1$, and $s>0$. This is the hard structural guarantee. It says nothing about $w_\star$, $g$, or calendar order. The shipped default is a second, *structural* chart whose coordinates are the screened quantities themselves; we construct it in the subsection "The structural chart: fitting in the screened coordinates", after seeing what the residual stack asks any chart to carry. The raw chart remains available as explicit configuration — for comparability with historical benchmarks, and as rollback.

### 6.1 One residual stack

Suppose price inversion has produced quote total variances $w_i$ at log-moneyness $k_i$, with working IVs $I_i=\sqrt{w_i/\tau}$ and non-negative weights $\omega_i$. In mid mode the data rows are

$$
r_i(\theta)=\sqrt{\omega_i}
\left(\sqrt{\frac{w(k_i;\theta)}{\tau}}-I_i\right). \tag{34}
$$

The core problem is

$$
\min_{\theta\in\mathbb{R}^5}\frac12
\left\|
\begin{pmatrix}
r_{\rm data}(\theta)\\ r_{\rm core}(\theta)\\
r_{\rm calendar}(\theta)\\ r_{\rm optional}(\theta)
\end{pmatrix}
\right\|_2^2. \tag{35}
$$

With no optional target the last two blocks are empty. Bid–ask and haircut modes replace the mid data rows by a vol-space band hinge plus a small mid anchor. The surfaced quote-weight choices are `equal` and `tv_density`; the low-level calibrator also accepts arbitrary weights, including vega-squared research weights.

The raw structure does not prevent a trial $a$ from making $w$ negative. To keep the IV residual evaluable, the calibration residual floors trial total variance at $10^{-12}$ inside the square root and sets the derivative to zero where the floor is active. The `RawSVI.implied_vol` method itself has no such floor; this is a solver device, not a model definition.

### 6.2 A geometric, deliberately rough start

The initializer sorts the quotes, uses the observed argmin as a seed for $m$, and estimates two finite-span slopes from the endpoints to the array midpoint. Those slopes seed $b$ and $\rho$; the width starts at one tenth of the quoted $k$ span, floored at $0.01$, and $a$ is backed out from the observed minimum with a small positive floor. Each transformation in equation (33) is then inverted to produce $\theta_0$.

This is an initializer, not an estimator. The observed argmin is generally an estimate of $k_\star$, not of raw $m$; the array midpoint need not be ATM on an uneven or one-sided chain; and finite quoted slopes are not asymptotic wings. The construction is useful because it usually lands in the correct basin, not because its intermediate numbers have structural meaning.

### 6.3 The analytic Jacobian

The chain has three layers:

$$
\theta\longmapsto(a,b,\rho,m,s)
\longmapsto w(k)
\longmapsto I(k)
\longmapsto r_i.
$$

With $x$ and $r$ from equation (6), the raw partial derivatives are

$$
\frac{\partial w}{\partial(a,b,\rho,m,s)}=
\left(
1,\ \rho x+r,\ bx,\ -b\left(\rho+\frac{x}{r}\right),\
\frac{bs}{r}
\right). \tag{36}
$$

The latent-coordinate factors are

$$
\frac{\mathrm{d} b}{\mathrm{d}\theta_2}=1-e^{-b},\qquad
\frac{\mathrm{d}\rho}{\mathrm{d}\theta_3}=1-\rho^2,
\qquad \frac{\mathrm{d} s}{\mathrm{d}\theta_5}=s, \tag{37}
$$

and the IV factor is

$$
\frac{\partial I}{\partial w}
=\frac{1}{2\tau I}=\frac{1}{2\sqrt{\tau w}}. \tag{38}
$$

Multiplying these factors gives the data Jacobian without another model evaluation. Active hinge rows use the derivative of their linear branch and inactive rows use zero; at a kink the implementation chooses the inactive subgradient. In particular the $|\rho|$ term in the Lee row uses $\operatorname{sgn}(\rho)$, with the zero subgradient at $\rho=0$.

The analytic module covers the mid or band data block, both core rows, and the sampled calendar floor. A var-swap target or persistence-prior block switches the whole fit to finite differences because those rows are not differentiated there. Extrapolation enforcement keeps a hybrid Jacobian: the dominant core remains analytic and only the small extrapolation block is centrally finite-differenced. Both optimizer charts run this same analytic machinery: the structural chart of the next subsection multiplies the raw-space Jacobian by a closed-form $5\times5$ chain matrix rather than re-differentiating anything.

**Table 4 — Every optional target is expressed in the native currency of raw SVI, but not every row has yet been differentiated analytically. "Analytic" is a performance statement, not an arbitrage statement.**

| Residual block | Purpose | Jacobian path |
|---|---|---|
| mid or band data | fit working IV, or stay inside bid–ask/haircut band | analytic |
| minimum and Lee | weak core screens, equation (32) | analytic subgradient |
| calendar floor | reduce sampled crossings against the nearer expiry | analytic subgradient |
| extrapolation | sampled $g$, calendar, and wing-order hinges | analytic core + FD block |
| var-swap quote | pull replicated fair variance toward a quote | finite-difference fit |
| strike/operator prior | preserve under-observed prior shape or operators | finite-difference fit |

> **Performance.** The solver remains Levenberg–Marquardt. A tested switch to trust-region reflective was slower on noisy real chains because it took more iterations through hinge changes; the useful change was the Jacobian, not the optimizer. On the generated 25-quote case, run in the raw chart for continuity with the historical benchmarks, a warmed median-of-five run measures 3.69 ms with finite differences and 1.18 ms analytically, a 3.14× speed-up with objective costs agreeing to $2.7\times10^{-33}$. The separately recorded spike-regime measurement was 26.3→10.2 ms per real node (2.58×). The first number is machine-local and regenerated; the second is a dated historical benchmark recorded in `backend/backtest/FINDINGS_calibration_arb.md`.

> **Figure 6 — Timing: analytic versus finite-difference Jacobian (figure not included in this pack).** The analytic Jacobian removes repeated residual evaluations rather than changing the optimizer. The fresh synthetic timing (A) and the historical real-node timing (B) have different scales and provenance, but both isolate the same implementation change. Both panels time the raw chart; the default structural chart of the next subsection is benchmarked separately. — Panel A is the note's regenerated microbenchmark on the 25-quote synthetic case: paired bars showing 3.69 ms per fit with finite differences against 1.18 ms with the closed-form Jacobian, a 3.14× speed-up at objective costs agreeing to $2.7\times10^{-33}$. Panel B is the dated June-2026 spike-regime measurement on real backtest nodes: 26.3 ms before against 10.2 ms after, a 2.58× speed-up. The consistent ratio across very different data confirms the saving comes from eliminating the $1+P$ perturbed residual evaluations per LM step.

### 6.4 The structural chart: fitting in the screened coordinates

The raw chart guarantees the hyperbola's structure and nothing else. The two quantities the screens police — the minimum and the wing coefficients — are left to soft hinge rows, and nothing prevents a trial, or a converged fit, from sitting exactly on a hinge; the boundary incident of Proposition 4 was precisely that. The alternative is to parameterize the slice by the policed quantities themselves, so that the inequalities live in the chart rather than in the penalty. Production's default chart describes the slice by $(\beta_L,\beta_R,k_\star,w_\star,\kappa_\star)$ — the two wing coefficients, the vertex location, the minimum total variance, and the vertex curvature $\kappa_\star=w''(k_\star)$ — and lifts the constrained four:

$$
\beta_L=\beta_{\max}\operatorname{logistic}(\theta_1),\qquad
\beta_R=\beta_{\max}\operatorname{logistic}(\theta_2),\qquad
w_\star=\operatorname{softplus}(\theta_4),\qquad
\kappa_\star=e^{\theta_5}, \tag{39}
$$

with the vertex location $k_\star=\theta_3$ entering unlifted, and $\beta_{\max}=1.95$ the buffered Lee cap. Every finite $\theta$ now has strictly Lee-clean wings, a strictly positive minimum, and strict convexity at the vertex — by construction, not by penalty.

Recovering the raw coordinates is Proposition 1 read backwards. The wings give scale and tilt exactly as in equation (16); the vertex curvature, evaluated from equation (7) at $r=s/\sqrt{1-\rho^2}$, is $\kappa_\star=b(1-\rho^2)^{3/2}/s$, which determines the width; and the vertex equations (8) then release $m$ and $a$:

$$
b=\frac{\beta_L+\beta_R}{2},\quad
\rho=\frac{\beta_R-\beta_L}{\beta_R+\beta_L},\quad
s=\frac{b(1-\rho^2)^{3/2}}{\kappa_\star},\quad
m=k_\star+\frac{s\rho}{\sqrt{1-\rho^2}},\quad
a=w_\star-bs\sqrt{1-\rho^2}. \tag{40}
$$

Two consequences follow immediately. The two core rows of equation (32) are structurally zero at every iterate, and the trial-variance floor of the residual never fires, because $w(k)\ge w_\star>0$ everywhere: the fences become inert bookkeeping. What the chart does *not* buy is $g\ge0$ — the Vogt slice of Figure 5 passes wings and minimum with room to spare — so the display certificate remains the acceptance authority.

**Remark 1 (Strict in $\mathbb{R}$, not yet strict in float64).** The chart's inequalities are strict for every finite real $\theta$, and both statements failed in IEEE-754 before the analytic-Jacobian lock exposed them. A logistic evaluated at a modestly large argument rounds to exactly $1.0$, parking a wing exactly *at* the cap — the boundary the chart exists to keep strict; and with one wing saturated against an ordinary other, the quotient for $\rho$ rounds to $\pm1$, making $1-\rho^2$ an exact zero, the width zero, and $m$ a NaN. Production clips the logistic one ulp inside $1$ and computes $1-\rho^2$ by the exact product identity $4\beta_L\beta_R/(\beta_L+\beta_R)^2$. *A chart proved strict in exact arithmetic must be re-proved in floating point.*

The default was not flipped on elegance. A two-round pre-registered benchmark over roughly twenty-nine thousand real-chain fits adjudicated the two charts, and its headline lesson is statistical rather than numerical: the raw chart's apparently lower aggregate arbitrage rate was a survivorship artifact. A third of the raw arm's fits exhausted the evaluation cap before converging, and those unconverged fits — rarely arbitrage-flagged, because they never reached any optimum — diluted its rate. Compared converged against converged, the structural chart is cleaner (0.822% versus 1.076% genuine-arbitrage incidence), matches or beats every precision median, never hard-breaks, exhausts the evaluation cap 594 times against 9,472, and fits roughly 3× faster. On that record the default was ratified; the raw chart stays as explicit rollback, and the frozen benchmark arm of the backtest harness deliberately keeps it for continuity. The laboratory figures of this note run the raw chart for the same reason.

## 7. Laboratory case: JW to raw to fit to JW

An exact-family, noise-free recovery is not market evidence. It is the right laboratory test for a coordinate conversion and a Jacobian: any visible miss is an implementation error.

Take $\tau=0.5$ and

$$
(v,\psi,p,c,\widetilde v)=(0.0425,-0.25,0.75,0.25,0.034). \tag{41}
$$

The production `jw_to_raw` converter builds the target. We sample 25 noise-free total-variance quotes on $[-0.35,0.30]$, fit production raw SVI from its geometric start, then read JW back using equation (14). This is a genuine

$$
\text{JW}\longrightarrow\text{raw target}
\longrightarrow\text{raw fit}\longrightarrow\text{JW readout}
$$

round trip.

**Table 5 — Recovered raw coordinates.**

| Parameter | Value |
|---|---:|
| $a$ | +0.010625 |
| $b$ | +0.072887 |
| $\rho$ | −0.500000 |
| $m$ | +0.058310 |
| $s$ | +0.100995 |

**Table 6 — Recovered JW functionals.**

| Handle | Value |
|---|---:|
| $v$ | +0.042500 |
| $\psi$ | −0.250000 |
| $p$ | +0.750000 |
| $c$ | +0.250000 |
| $\widetilde v$ | +0.034000 |

The maximum quote error is $5.6\times10^{-13}$ vol bp after 21 residual evaluations. The maximum absolute JW round-trip error is $3.9\times10^{-16}$, and the recovered wing coefficients are 0.1093 and 0.0364. On the plotted diagnostic grid, $g$ stays above 0.343. These numbers test algebra and implementation; they do not measure SVI's ability to fit a non-SVI market.

> **Figure 7 — Laboratory recovery (figure not included in this pack).** The laboratory target and fit coincide (A), so the useful evidence is the residual scale (B) and the independent Durrleman diagnostic (C). The test validates conversion, initialization, calibration, and reverse readout in one reproducible path; it deliberately says nothing about real-market expressiveness. — Panel A superimposes the target slice built by `jw_to_raw` from the handles $(0.0425,-0.25,0.75,0.25,0.034)$ and the production refit on the 25 sampled quotes over $[-0.35,0.30]$; the two curves are visually indistinguishable. Panel B plots the per-quote residuals, whose largest magnitude is $5.6\times10^{-13}$ vol bp — machine precision, reached in 21 residual evaluations. Panel C plots the independent Durrleman diagnostic $g(k)$ over the plotted grid, staying above 0.343 everywhere, confirming the recovered slice is comfortably butterfly-clean on that range.

## 8. Where one hyperbola stops being enough

Strict convexity of total variance gives SVI one minimum and one transition between two wing slopes. This is desirable regularization on sparse equity index chains, but it is also a hard expressiveness limit. A W-shaped total-variance target, a double-humped event density, or a sharply localized short-dated kink asks the curve to turn more than once.

> **Figure 8 — One-hyperbola rigidity (figure not included in this pack).** A deliberately synthetic positive target has two minima and a central hump. Production raw SVI returns the best one-hyperbola compromise (A), leaving an RMS miss of 147.6 vol bp and a maximum miss of 351.9 vol bp (B). This is a geometric stress test, not a claim that the synthetic target is itself an arbitrage-free market smile. — Panel A shows the synthetic W-shaped target — two local minima flanking a central hump — with the fitted SVI slice cutting one smooth convex compromise through the middle, unable to reproduce either minimum. Panel B shows the structured residual left behind, oscillating with the target's humps at an RMS of 147.6 vol bp and peaking at 351.9 vol bp. The failure is structural, not an optimizer artifact: a strictly convex curve has exactly one minimum.

Sparse identification is a different limitation. On a narrow or one-sided quote window, distinct raw tuples can price the observed strikes almost identically while implying different remote wings. The fitted curve may be stable even when $(a,b,\rho,m,s)$ is not. JW is easier to interpret, but its wing handles are still extrapolated functionals when the market has not quoted the wings. Across fits, compare prices, curves, and economically observed handles before comparing raw coefficients.

The historical spike-regime sweep recorded SVI at 24.3 vol bp RMS in-sample and 26.8 out-of-sample over roughly 1,576 nodes per regime. Those values are retained for continuity with the current note and deck, but the underlying result parquets are not checked into this workspace; they are historical evidence, not a result regenerated by this manuscript. The same audit changed the SVI butterfly flag rate from 20.8% under a reconstructed finite-difference diagnostic to 9.2% under the model-native analytic diagnostic. The surviving flags are consistent with the lesson of Figure 5: numerical noise exaggerated the old count, while genuine violations remain possible.

## 9. The honest product and mathematical contract

SVI, SVI-JW, and the no-arbitrage analysis are classical. Raw SVI is due to Gatheral; the JW chart is documented by Gatheral and Jacquier; Lee supplies the wing moment bound; Durrleman supplies the density factor; and Martini–Mingone give the full raw-SVI butterfly domain [Gatheral2004, GatheralJacquier2014, Lee2004, Durrleman2010, MartiniMingone2022].

The contribution here is narrower: a clock-consistent derivation in Vol-Fitter notation, an explicit full-image theorem including the non-identified stratum, a conditioning analysis tied to the actual converter, a production-accurate separation of screens from certification, an executable checked reference map, and traceability from the mathematical claims to code and tests.

**Table 7 — The shortest reliable summary of what the model, coordinate chart, and implementation do and do not guarantee.**

| Claim or feature | Status | Qualification |
|---|---|---|
| raw SVI evaluation | shipped | runtime model uses `RawSVI` |
| raw SVI fit and storage | shipped | selected overlay is calibrated and stored in raw coordinates |
| structural fit chart | shipped default | wings, minimum, and vertex convexity strict by construction; raw chart is explicit rollback |
| five-handle JW entry/bump/export | not shipped | guarded converter and desk-unit ticket shipped and test-locked as the mandatory gateway; no runtime UI/API entry yet |
| raw ↔ JW equivalence | exact | unique only on equation (21); singular on equation (22) |
| structural raw inequalities | hard | for finite latent coordinates in exact arithmetic |
| minimum and Lee controls | soft under raw chart | buffered cap $\beta_{\max}=1.95$; structurally inert under the default chart |
| butterfly freedom on the traded range | certificate-gated | 801-point $g$ certificate gates readiness and publish; optional one-shot certified repair (SVI only) |
| global butterfly freedom | not guaranteed | requires Proposition 2; counterexample is test-locked |
| global calendar freedom | not guaranteed | sampled finite-weight floors reduce crossings |
| one minimum and linear wings | structural | strength for regular smiles, limitation for event/WW shapes |
| analytic core Jacobian | shipped | both charts; optional var-swap/prior blocks revert to FD; extrapolation is hybrid |

## 10. Traceability

The table names existing repository anchors. A test locks only the claim in its row: selected invalid converter cases do not constitute full input validation, and a finite diagnostic grid does not constitute a global proof.

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 8 — Mathematical and production claims with code/test anchors.**

| Claim | Note object | Code and test anchors |
|---|---|---|
| Clock-independent $w$; production uses working $\tau$ for annualization | equation (2) | `api/quotes.py::PreparedQuotes`; `api/service.py::build_slice_fit_task`; `api/table.py` |
| Raw evaluation and production JW→raw conversion | equations (3), (19) | `models/svi_jw/svi.py`; `tests/test_lqd_pricing.py::test_jw_conversion_matches_note` |
| Regular round trips and singular $\psi=0$ family | Theorem 1 | `models/svi_jw/svi.py`; `tests/test_svi_domain.py::test_regular_domain_round_trips`; `::test_psi_zero_stratum_not_identified` |
| Selected unguarded-converter failure cases | Table 2 | `tests/test_svi_domain.py::test_invalid_inputs_fail_loudly_not_plausibly` |
| Guarded converter and desk-unit ticket | section "Changing coordinates, and where the chart tears" | `models/svi_jw/svi.py::jw_to_raw_checked`; `models/svi_jw/desk.py`; `tests/test_svi_desk_and_guards.py` |
| Structural chart lift, inert screens, chain Jacobian | subsection "The structural chart" | `models/svi_jw/structural.py`; `tests/test_svi_structural_chart.py`; `tests/test_svi_structural_jacobian.py` |
| Buffered Lee cap and boundary incident | Proposition 4 | `tests/test_svi_lee_boundary.py`; certification case `svi_lee_boundary` |
| Display certificate gates readiness and publish | section "Convex total variance is not an arbitrage certificate" | `models/diagnostics.py::belly_certificate`; `tests/test_belly_certificate.py`; certification case `belly_certificate` |
| Minimum/Lee screens do not certify $g\ge0$ | Figure 5 | `models/svi_jw/calibrate.py::_penalties`; `tests/test_svi_domain.py::test_core_screens_do_not_certify_butterfly_freedom` |
| Noise-free raw recovery and curve reproduction | section "Laboratory case: JW to raw to fit to JW" | `models/svi_jw/calibrate.py`; `tests/test_svi_calibrate.py::test_recovers_benchmark_parameters`; `::test_curve_reproduced_to_machine_precision` |
| Analytic Jacobian and active/inactive hinge rows | subsection "The analytic Jacobian" | `models/svi_jw/jacobian.py`; `tests/test_svi_jacobian.py` |
| Band objective reaches SVI | Table 4 | `calib/band.py`; `tests/test_band_fit.py`; `tests/test_svi_jacobian.py::test_band_fit_admissible` |
| Sampled calendar floor and no-floor no-op | equation (35) | `models/svi_jw/calibrate.py`; `tests/test_overlay_calendar.py::test_svi_no_floor_is_byte_identical`; `::test_svi_floor_crushes_calendar_violation` |
| Hybrid extrapolation block and advisory measurement | section "Convex total variance is not an arbitrage certificate" | `calib/extrap.py`; `tests/test_extrap_enforce.py`; `tests/test_diagnostics.py::test_extrapolated_arb_flags_negative_g_in_wing` |
| Var-swap target reaches SVI | Table 4 | `calib/varswap.py`; `tests/test_varswap.py::test_penalty_pulls_model_varswap_toward_quote_all_models` |
| Operator and strike-anchor priors reach SVI | Table 4 | `calib/operators.py`, `calib/prior.py`; `tests/test_prior_parametric.py::test_operator_prior_pulls_all_models_toward_prior_skew`; `::test_strike_anchor_reaches_svi_and_sigmoid` |
| Model-native analytic butterfly diagnostic | Proposition 2 | `backtest/dispatch.py::_analytic_butterfly`; `tests/test_backtest_arb.py` |
| Settings defaults and SVI overlay wiring | Appendix A | `api/schemas.py::FitSettings`; `models/display.py::build_display_fit`; `tests/test_api_settings.py` |

## Appendix A. Control atlas

The table lists direct SVI controls and the shared residual controls that alter an SVI overlay. Prior persistence has its own larger atlas in Note 13; the rows here identify the entry points relevant to this calibrator.

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 9 — SVI and shared calibration controls.**

*FitSettings: direct and shared slice controls*

| Knob | Default | Role |
|---|---|---|
| `model` | `lqd` | Set to `svi` to display the raw-SVI overlay. |
| `sviChart` | `structural` | Optimizer chart, equation (39); `raw` is the historical vector, equation (33), kept for comparability and rollback. |
| `bellyRepair` | true | One-shot certified repair refit when the display certificate fails; clean fits never see a second solve. |
| `sviPenaltyWeight` | 1000 | Residual multiplier $W$ in equation (32); $0$ disables both core screens. |
| `leeSlopeMax` | 1.95 | Buffered cap $\beta_{\max}$, strictly inside Lee's bound of $2$ (the boundary itself is broken); values above the bound are accepted by the schema. |
| `weightScheme` | `equal` | Unit or time-value-density quote weights. Arbitrary low-level arrays are also accepted. |
| `haircut` | $0.005$ | Absolute-vol tightening used only in haircut band mode. |
| `midAnchorWeight` | $0.05$ | Small mid anchor appended in bid–ask and haircut modes. |

*OptionsSettings / request-level shared controls*

| Knob | Default | Role |
|---|---|---|
| `fitMode` | `mid` | Persisted default: mid, bid–ask band, or haircut band. |
| `enforceCalendar` | true | Threads the nearer displayed slice into the sampled calendar floor. |
| `calendarWeight` | $10^6$ | Squared-objective weight; residual rows use its square root. |
| `extrapEnforce` | false | Adds tapered extrapolation rows and activates the hybrid Jacobian. |
| `eventsEnabled` | true | Uses event-weighted $\tau$; when the event calendar is empty, $\tau=t$. |
| `varSwapEnabled` | true | Allows an available variance-swap quote to append its target row. |
| `varSwapWeightPct` | $10$ | Var-swap budget as a percentage of summed option-quote weights. |
| `priorPersistenceMode` | `hybrid` | Routes active transported priors to strike/operator/factor targets; absence of an active prior leaves the blocks empty. |

*Internal numerical choices*

| Knob | Default | Role |
|---|---|---|
| $b=\operatorname{softplus}(\theta_2)$ | — | Enforces $b>0$ for finite $\theta_2$. |
| $\rho=\tanh(\theta_3)$ | — | Enforces $\lvert\rho\rvert<1$ for finite $\theta_3$. |
| $s=e^{\theta_5}$ | — | Enforces $s>0$ for finite $\theta_5$. |
| LM tolerances | $10^{-15}$ | `xtol`, `ftol`, and `gtol`. |
| trial-$w$ floor | $10^{-12}$ | Keeps IV residuals finite on negative-variance trial slices; never fires under the structural chart; not part of `RawSVI.implied_vol`. |
| certificate grid | 801 pts, tol $10^{-4}$ | Traded-range Durrleman certificate gating readiness and publish for any displayed model. |

## Appendix B. Performance and numerical qualifications

1. **Analytic core.** The main saving is replacing one base residual plus five parameter perturbations by one closed-form Jacobian. The generated microbenchmark is a warmed median of five timings on the current development machine; it is a regression signal, not a universal latency number.
2. **LM rather than trust region.** LM was retained after matched experiments on noisy real nodes. The result is empirical: a different residual stack or constraint strategy can change the conclusion.
3. **Conditional acceleration.** Mid/band, core penalties, and sampled calendar rows are analytic. Var-swap and prior rows trigger full finite differences. Extrapolation enforcement is hybrid.
4. **Finite arithmetic.** The hard map, equation (33), is exact for finite real inputs. Floating-point `tanh` can round to $\pm1$, exponentials can underflow or overflow, and $1-e^{-b}$ is less accurate than `-expm1(-b)` for extremely small $b$. The production range encountered in ordinary fits stays away from those extremes; the mathematical statement should nevertheless not be mistaken for an IEEE-754 proof.
5. **Low-level input contract.** The calibrator assumes $\tau>0$, finite quote arrays, non-negative price-implied total variances, and enough residual rows for LM. It does not promise a meaningful five-parameter fit to an empty, tiny, or one-sided chain, nor global convergence from every start.
6. **Converter conditioning.** The checked reference map below uses equation (25); it still rejects the singular stratum because no numerical rearrangement can select a unique missing curvature.

## Appendix C. Executable reference maps

The original note prints an executable Python listing here, imported and executed by the figure generator `figures/gen_svi_rewrite.py`. Before figures are written, its checked inverse is compared with production `jw_to_raw` *and* with the guarded production converter `jw_to_raw_checked` on three regular-domain cases to relative tolerance $2\times10^{-12}$. The inverse uses the stable denominator, equation (25); the reverse map is exactly the functional definition, equation (14). Historical note: this listing predates the guarded production converter, which adopted its domain checks and stable denominator wholesale — the reference map was, in effect, promoted to production. Per the transfer policy of this pack, the listing is replaced by the following complete algorithm specification; it carries every algorithmic detail of the code.

**Algorithm C.1 (forward map, raw → JW).**

*Inputs:* a raw slice $(a,b,\rho,m,s)$ and a variance clock $\tau>0$.
*Outputs:* the five JW handles $(v,\psi,p,c,\widetilde v)$.

1. Compute the ATM total variance $w_0=w(0)=a+b\left(-\rho m+\sqrt{m^2+s^2}\right)$, the core radius at ATM $r_0=\sqrt{m^2+s^2}$, and $\sqrt{w_0}$.
2. Return
$$
v=\frac{w_0}{\tau},\qquad
\psi=\frac{b\left(\rho-m/r_0\right)}{2\sqrt{w_0}},\qquad
p=\frac{b(1-\rho)}{\sqrt{w_0}},\qquad
c=\frac{b(1+\rho)}{\sqrt{w_0}},\qquad
\widetilde v=\frac{a+bs\sqrt{1-\rho^2}}{\tau}.
$$
This is exactly the functional definition, equation (14), with no domain checks: it is pure evaluation.

**Algorithm C.2 (checked regular inverse, JW → raw, cancellation-resistant).**

*Inputs:* a JW point $(v,\psi,p,c,\widetilde v)$ and a clock $\tau>0$.
*Outputs:* the unique regular raw slice $(a,b,\rho,m,s)$, or a domain error.

1. **Domain guard.** Verify, in this order, that $\tau>0$, $v>0$, $p>0$, $c>0$, $-p/2<\psi<c/2$, $\psi\ne0$, and $\widetilde v<v$ — the exact regular domain of equation (21), with $\psi\ne0$ and $\widetilde v<v$ together rejecting the singular stratum of equation (22) explicitly. If any condition fails, raise a domain error ("JW point is outside the regular inverse domain"); the guarded production converter raises a structured error with six machine-readable reason codes, one per inequality.
2. Set $w_0=v\tau$.
3. Wings to scale and tilt: $b=\tfrac12\sqrt{w_0}\,(p+c)$ and $\rho=(c-p)/(c+p)$, per equation (16).
4. ATM skew to normalized displacement: $\chi=\rho-4\psi/(p+c)$, per equation (17).
5. Compute $q_\rho=\sqrt{1-\rho^2}$ and $q_\chi=\sqrt{1-\chi^2}$.
6. **Stable denominator.** Rationalize the square-root difference as $\delta q = \dfrac{(\chi-\rho)(\chi+\rho)}{q_\rho+q_\chi}$ (algebraically $q_\rho-q_\chi$), then evaluate
$$
D=\frac{(\rho-\chi)^2+\delta q^2}{2q_\chi},
$$
which is exactly equation (25) with no subtraction of nearly equal numbers.
7. Width from the belly gap: $s=\dfrac{w_0-\widetilde v\tau}{bD}$.
8. Displacement and level: $m=\chi s/q_\chi$ and $a=\widetilde v\tau-bs\,q_\rho$, per equation (19).
9. Return $(a,b,\rho,m,s)$; production stores the width in the field named `sigma`.

*Verification contract:* before any figure of this note is drawn, Algorithm C.2 is executed against both production converters (`jw_to_raw` and `jw_to_raw_checked`) on three regular-domain cases and required to agree to relative tolerance $2\times10^{-12}$.

## References

- [Gatheral2004] J. Gatheral. *A parsimonious arbitrage-free implied volatility parameterization with application to the valuation of volatility derivatives.* Presentation, Global Derivatives, Madrid, 2004.
- [GatheralJacquier2014] J. Gatheral and A. Jacquier. *Arbitrage-free SVI volatility surfaces.* Quantitative Finance, 14(1):59–71, 2014. doi:10.1080/14697688.2013.819986.
- [Lee2004] R. W. Lee. *The moment formula for implied volatility at extreme strikes.* Mathematical Finance, 14(3):469–480, 2004.
- [Durrleman2010] V. Durrleman. *From implied to spot volatilities.* Finance and Stochastics, 14(2):157–177, 2010. doi:10.1007/s00780-009-0112-1.
- [MartiniMingone2022] C. Martini and A. Mingone. *No arbitrage SVI.* SIAM Journal on Financial Mathematics, 13(1):227–261, 2022. doi:10.1137/20M1351060.




