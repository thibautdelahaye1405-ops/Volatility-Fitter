# Grounding brief 1 — What the four Note 01 editions already contain

Compiled 2026-08-03 from a full read of the four LQD note editions in `Docs/notes/`.
Purpose: (a) the paper must NOT repeat these editions' pedagogical angles;
(b) the paper MUST be at least as mathematically complete; (c) every formula
below is verified against the production code.

Sources (repo-internal, for the author's eyes only — the paper itself cites
NONE of these, it is a standalone publication):
- `Docs/notes/01_lqd_model.tex` — original technical note (1473 ln)
- `Docs/notes/01_lqd_model_percentile_ruler.tex` — prevailing edition (1613 ln)
- `Docs/notes/01_lqd_model_lecture.tex` — lecture edition (1579 ln)
- `Docs/notes/01_lqd_model_coordinates.tex` — coordinates edition (2702 ln)
- `Docs/notes/LECTURE_REWRITE_GUIDE.md`, `Docs/notes/STYLE_GUIDE.md`
- `Docs/notes/reviews/committee_review_note01_2026-07-19.md`

## 1. The model, precisely

**LQD = log quantile density.** For one expiry: X = log(S_T/F_T) under the
T-forward measure, Q(u) its quantile function, q(u) = Q'(u) the quantile
density; the model parameterizes l(u) = log q(u).

Normalization: Y = S_T/F_T, X = log Y, k = log(K/F_T), E[Y] = 1.
Normalized call: c(k) = C$(F_T e^k, T)/(D_T F_T) = E[(Y - e^k)^+].

Logistic seed: Lambda(z) = 1/(1+e^{-z}), rho(z) = Lambda(z)(1-Lambda(z)),
with tails rho(z) ~ e^z (z->-inf), ~ e^{-z} (z->+inf). P = Lambda(Z) uniform,
Z = log(P/(1-P)) log-odds; z=0 the median, +-log 9 the 90th/10th percentiles.

**Central model (transport form, prevailing edition eq 7):**

    X = x(Z),   x(z) = m + int_0^z exp(h(Lambda(t))) dt,   h in P_N[0,1]
    h(p) = sum_{n=0}^N d_n P_n(1-2p)          (shifted Legendre)

Production separates the endpoint chord:

    h(p) = (1-p) L + p R + sum_{n>=2} a_n P_n(1-2p)
    d_0 = (L+R)/2, d_1 = (L-R)/2, d_n = a_n (n>=2)
    log lambda_- = L + sum a_n,  log lambda_+ = R + sum (-1)^n a_n

**Canonical LQD form (original eq 4 / coordinates eq 5):**

    l(u) = -log u - log(1-u) + (1-u)L + uR + sum_{n>=2} a_n P_n(1-2u)
    q(u) = e^{g(u)} / (u(1-u)),  g(u) = (1-u)L + uR + sum a_n P_n(1-2u)

Orders: current shipped default N=16, API range 4<=N<=24, per-slice cap
N+1 <= quotes/2 never below min(N,6). Note examples: SPX-style case order 9,
event/double-hump case order 16 (older editions use N=6 and N=12).

Martingale centering:  m = -log int e^{b(z)} rho(z) dz, where b(z) =
int_0^z v, v(z) = e^{h(Lambda(z))}; equivalently mu = -log int e^{Qbar} u(1-u) dz.

**No-arbitrage.**
- Endpoint speeds lambda_- = e^{h(0)}, lambda_+ = e^{h(1)} (aka A_L, A_R).
- Normalizer tails ~ C_- e^{(1+lambda_-)z} (left), C_+ e^{-(1-lambda_+)z} (right).
- Proposition (finite forward): lambda_+ < 1. Hard wall (A_R < 1), not a preference.
- Density positivity is STRUCTURAL: F_X(x(z)) = Lambda(z),
  f_X(x(z)) = rho(z)/v(z) > 0; f_X(Q(u)) = 1/q(u) = u(1-u) e^{-g(u)}.
- Convexity claim is in STRIKE y, not log-strike k: c~'(y) = -P(Y>y),
  c~''(y) = f_Y(y) >= 0. (In k, extra change-of-variable terms appear.)

**Calendar / convex order.** With the integrated asset-quantile
G_T(p) = int_p^1 y_T(r) dr (the "upper share" in rank coordinates):
    Y_1 <=_cx Y_2  <=>  G_1(p) <= G_2(p) for all p in [0,1],
proved both directions via the conjugate (Legendre) pair
c~_T(y) = sup_p {G_T(p) - (1-p) y}, G_T(p) = inf_y {c~_T(y) + (1-p) y}.
Production ENFORCEMENT is different: support-confined price rows
sqrt(w_cal) taper_m (C_near(k_m) - C_far(k_m))^+ on the intersection of
retained quote spans, cos^2 C1 taper — because a full-grid G floor drags the
extrapolated tail into the constraint (measured phantom drag: far expiry
10.6 -> 1095 vol bp on an acute short-dated pair). "Control, not theorem."

**Pricing: the ledger.** G(z) = int_z^inf e^{x(t)} rho(t) dt,
G'(z) = -e^{x(z)} rho(z). With x(z_k) = k, p_k = Lambda(z_k):

    c(k) = G(z_k) - e^k (1 - p_k)        ("asset delivered minus strike bill")
    c'(k) = -e^k (1-p_k)
    c''(k) = -e^k(1-p_k) + e^k rho(z_k)/v(z_k)
    e^{-k} (c''(k) - c'(k)) = f_X(k)     (Breeden–Litzenberger in one division)

**Constant-speed exact solution.** h = log s, 0<s<1: E[e^{sZ}] = pi s/sin(pi s)
(Euler beta integral B(1+s,1-s)); m = -log(pi s / sin pi s); x(z) = m + s z.
Var(Z) = pi^2/3 gives the cold start s ~ sqrt(3 w_0)/pi. Lecture edition also
shows the cold-start ATM match is ~8% off: C(0) ~ s log 2, w_ATM ~ 2 pi (log 2)^2 s^2.

**ATM microscope (exact handles from three numbers).** With
p_* = Lambda(z_*), f_* = f_X(0), c_0 = G(z_*) - (1-p_*):
    a = PhiInv((1+c_0)/2), w_0 = 4a^2, n = phi(a), Delta = p_* - Phi(a)
    w'_0 = (2 sqrt(w_0)/n) Delta
    w''_0 = (2 sqrt(w_0)/n) f_* - 2 + (1/(2 w_0) + 1/8) (w'_0)^2
    sigma_0 = sqrt(w_0/tau); sigma'_0 = Delta/(n sqrt(tau));
    sigma''_0 = [f_*/n - 1/sqrt(w_0) + (sqrt(w_0)/4)(Delta/n)^2]/sqrt(tau)
Headline: **total-variance skew is exactly a digital mismatch** Delta between
the model percentile of the forward and the matched-flat-Black percentile.
Level/skew/curvature depend only on (c_0, p_*, f_*) and tau.

**Wings/moments/Lee.**
    P(X>x) ~ K_+ e^{-x/lambda_+};  P(Y>y) ~ K_+ y^{-1/lambda_+} (and mirrored)
    E[e^{rX}] < inf  <=>  -1/lambda_- < r < 1/lambda_+
    pi_+ = 1/lambda_+ - 1, pi_- = 1/lambda_-
    Psi(q) = 2 - 4(sqrt(q^2+q) - q);  limsup w(k)/|k| = Psi(pi_+-/+)
Closed speed-to-slope forms:
    beta_+ = 2 lambda_+ / (1 + sqrt(1-lambda_+))^2   (0<lambda_+<1)
    beta_- = 2 lambda_- / (1 + sqrt(1+lambda_-))^2   (lambda_->0)
Small speeds beta ~ lambda/2; lambda_+ -> 1 gives beta_+ -> 2. Lee gives only
limsup; polynomial endpoint => regular power tails => Benaim–Friz upgrades to
ordinary limits. Trader caveat: effective slope at 10-delta/1-delta sits well
below the k->inf limit (measured ratios 1.7–6x).

**Analytic Jacobian (envelope cancellation).** With h_theta = sum theta_j phi_j:
    r_j(z) = d b(z)/d theta_j = int_0^z v phi_j(Lambda) dt
    x_j(z) = r_j(z) - int e^{x} r_j rho dt      (martingale-shift term)
    G_j(z) = int_z^inf e^{x} x_j rho dt
    THEOREM:  d c(k;theta)/d theta_j = G_j(z_k)
Proof: moving-root terms combine to [G'(z_k) + e^k rho(z_k)] dz_k/dtheta_j = 0
by G' = -e^x rho and x(z_k) = k. Basis: phi_L = 1-u, phi_R = u, phi_{a_n} = P_n(1-2u).
Complexity honesty: the analytic pass is O(P n_grid) — it removes the rebuilds,
not the linear-in-P work. Measured speedups 1.44–1.97x.

**Var swap / log contract.** w_log = -2 E[X] = -2 int Q(z) u(1-u) dz
(integrand decays z e^{-|z|}); sigma_log = sqrt(w_log/tau). Analytic derivative
d w_vs/d theta = -2 int (dQ/dtheta) u(1-u) dz rides the same quadrature pass.
Honesty clause: prices the log contract; identification with a realized-var
swap assumes continuous monitoring of a continuous path.

**Numerical safety catalogue (the notes' "dangerous" list):**
- Past |z| ~ 36.7, expit(z) rounds to exactly 1: form u(1-u) as
  expit(z)*expit(-z); evaluate the cash leg e^k(1-u) as exp(k - logaddexp(0,z)).
  (An earlier build failed a randomized audit exactly here; fix moved worst
  butterfly violation 1e-2 -> 3e-13.)
- Beyond-grid asymptote: C(k) = e^{k - z_R(k)} A_R/(1-A_R),
  z_R(k) = Z + (k - Q(Z))/A_R (mirrored left), continuous at the seam,
  Lee-consistent; needed because short-dated display edges genuinely reach it.
- Truncation corrections: int_{z_R}^inf e^b rho dz ~ e^{b(z_R)-z_R}/(1-lambda_+),
  int_{-inf}^{z_L} ~ e^{b(z_L)+z_L}/(1+lambda_-). Grid Z=40, 8001 points (odd),
  optimization grid 2001.
- Three optimization charts (lqdCoords): lr (raw), endpoint
  ((log A_L, log A_R, a) — unit-determinant linear map; body modes
  endpoint-neutral), logistic (A_R = expit(rho): the wall is unreachable;
  production default). d log A_R/d rho = 1 - A_R compresses at the wall.
  Footnote: logistic removes the mathematical wall, not the floating-point
  one — beyond rho~36, A_R rounds to 1.0; EPS_AR=1e-6 stays the hard guard.
- Soft barrier: b(theta) = log(1 + e^{s(A_R - c)}), c=0.90, s=50, via logaddexp.
- Interior overflow budget: endpoint cancellation can keep A_R<1 while the
  body blows up e^g — EXP_BUDGET=700 on max g and max Qbar, clean ValueError.

## 2. Where full derivations live (by edition)

- Breeden–Litzenberger: all four; prevailing does it "by one division".
- Quantile<->density duality: lecture §2 fullest.
- Why logit removes both endpoint singularities: lecture §4.1 fullest.
- Universality/density of the family (Weierstrass + Cesàro-smoothed Legendre,
  Wasserstein-p for p < 1/A_R; atoms = jumps of Q excluded): ONLY coordinates
  (Prop 1 §3). Any density claim must carry this scope honestly.
- Moment strip exact change-of-variables: lecture §5.2 and coordinates §4.2.
- Logistic MGF via beta integral: coordinates §6 fullest.
- ATM implicit differentiation with all five Black partials: prevailing
  App A.3 (B_k = -e^k Phi(d_-) etc.), coordinates §8.1.
- Envelope cancellation: prevailing §9 (z-space), lecture §12 (u-space
  Leibniz — cleanest), coordinates §10.1 (+ remark linking to American
  exercise boundaries).
- Convex order conjugate-duality proof both directions: prevailing §11.1,
  coordinates §11.
- Gauss–Newton metric chart U = G^{-1}J^T(J G^{-1} J^T)^{-1}: coordinates §8.2.
- Fritsch–Carlson certificate + randomized strike-space audit + expit incident:
  coordinates §7.4 only.

## 3. Figure inventory per edition (floor for the paper: >= 12)

Original: 6 graphics / 3 figure envs (SVI fit + error; density + log q;
double-hat fit + density). Prevailing: 7 (ruler 3-panel; butterfly/secant +
discrete-butterfly-vs-density; tails 3-panel speed->moments->Lee; SPX-case
fit/residual/density; modes 3-panel a2/a3/a4; Jacobian-vs-FD; event/bimodal).
Lecture: 9 (logistic walkthrough 3-panel; tail map; SVI fit/error; density/
log q; double-hat pair; Jacobian timing bars). Coordinates: 17 (butterfly;
4-chart thesis figure; tail map; modes; endpoint-decoupling demo; ruler;
vega-floor weight regimes; ortho/retarget; Jacobian heat map + FD audit;
calendar gap trio; SPX case; SPX tails; identifiability fan (tail_study);
effective-slope-vs-Lee; event case; event order-control N=16 vs N=6; timing).

All are matplotlib PDFs from generators in `Docs/notes/figures/`
(gen_lqd.py, gen_lqd_fresh.py, gen_lqd_lecture.py, gen_lqd_geometry.py,
gen_lqd_referee.py, gen_lqd_audit.py). Pattern to copy: ONE generator per
paper; every quoted number emitted as a LaTeX macro file, never retyped.

## 4. Pedagogical arcs ALREADY TAKEN (the paper must not repeat)

1. Original: engineering justification ("fit within the space of densities,
   then read off IV"), four-invariant march, production vocabulary inline.
2. Prevailing: monotone transport / "percentile ruler"; finite-forward as a
   "right-tail credit limit"; call as two tail ledgers with a hand-priced
   ticket; skew as digital mismatch; ends with an honest-contract table.
3. Lecture: distribution-first desk lecture opening on a production failure
   (negative butterfly); "only three ideas"; gentlest derivations.
4. Coordinates: "in which coordinates is the arbitrage-free set trivial?" —
   six-chart shopping trip costed in "constraints left over"; post-review
   candour (certification, tail-stability fans, model card).

Untaken angles the explorer identified: information/identifiability (what
quotes pin vs what the basis chooses); the ledger G as THE organizing object
(pricing = Legendre transform, Jacobian = envelope, calendar = convex order,
var swap = first moment — four jobs, one array); the model as a
numerical-analysis object (what a structural theorem survives after
discretization).

## 5. Notation (adopt, and keep the discipline the notes sometimes broke)

Ledger: X, Y=e^X; u rank, z=log(u/(1-u)); k log-moneyness; Q, q=Q';
w total variance, sigma vol, tau ACTIVE variance time (three clocks: expiry
date T, calendar year fraction t_T, event-dilated tau_T — every w, vega,
annualized handle uses tau); g smooth part of log q; theta coefficients;
A_L, A_R endpoint scales e^{g(0)}, e^{g(1)}; mu martingale shift; G upper
share; sigma_0, s_0, kappa_0 ATM handles; beta Lee slope, Psi Lee map,
p moment order; Phi, phi normal CDF/PDF.

RULES (from the guides, enforced): ONE differentiation convention — primes
for one-variable functions (C', w', sigma'), subscripted partials for
several (∂_k B, ∂G/∂θ); never B_k/B_w subscript-letter style. No
near-identical symbol pairs (omega_i vs w rejected; per-quote weights live
in prose). Prefer deleting a symbol to renaming it. One boxed display per
paper. Z=40 is the logit integration half-width, unrelated to any quote
screen.

## 6. Committee flags (review of 2026-07-19 — bake the honesty in from day one)

1. Do not overclaim "coordinates for the space of smiles": every admissible
   vector is arb-free, NOT every arb-free slice is representable (atoms,
   bounded support, gaps, default mass, Gaussian/super-exponential tails
   excluded). Fair scope: "unconstrained coordinates for a flexible
   exponential-tail class."
2. Body and tails are NOT separated in the raw chart: a_2 += 0.10 multiplies
   BOTH tail scales by ~1.105 (hence the endpoint chart).
3. Reported tail parameters are model priors, not observations — weakly
   identified; report what quotes + order + ridge + vega floor + endpoint
   coupling jointly selected. Traders care about effective slope at
   10-delta, not the k->inf limit.
4. The numerical implementation must EARN the continuous proof: Q and G are
   Hermite-interpolated separately; monotonicity needs the Fritsch–Carlson
   certificate, not faith.
5. A_R < 1 is insufficient for computational safety (interior overflow;
   expit rounding at z~36.7).
6. Identifiability and market performance need evidence, not assertion.
7. The Euclidean pseudoinverse ATM chart is metric-arbitrary; kernel basis
   rotates between calibrations (hence GN-metric chart + quote packages).
8. Calendar enforcement is layered/finite-grid — say "control, not theorem"
   EARLY; report violations in economic units.
9. Performance numbers: median + dispersion from ONE run; O(P n_grid) honesty.
10. Acknowledge Petersen–Müller (Wasserstein regression/log-quantile-density
    literature) and Keelin's metalog; don't call ATM identities + envelope
    cancellation "genuinely original" without comparison.

Committee's preserve-list (keep in the paper): rank/log-odds intuition, the
solved logistic example + hand-priced ticket, moment-strip and Lee
derivation, the upper-share ledger, ATM digital/density interpretation, the
cancellation identity, multi-chart figures, caution boxes, candour about
synthetic evidence and soft calendars.
