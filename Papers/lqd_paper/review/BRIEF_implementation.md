# Grounding brief 2 — The production implementation (for the computational section + annex)

Compiled 2026-08-03 from a full read of `backend/volfit/models/lqd/` and call
sites. The paper refers to this only as "our production implementation" —
no repo paths, no internal names in the paper body. Code snippets in the
ANNEX may be lightly adapted Python/NumPy in paper notation.

## Module anatomy (11 files, pure NumPy/SciPy — no numba anywhere in LQD)

basis.py (params + Legendre + endpoint scales + Lee), quadrature.py (the
slice build + pricing), interp.py (Hermite + monotonicity certificate),
calibrate.py (objective + solver), jacobian.py (analytic sensitivities),
charts.py (optimization coordinate charts), atm.py (exact ATM handles),
ortho.py (ATM-orthogonal chart + GN metric), packages.py (RR/BF package
directions), band.py (delta-method functional bands).

## 1. Parameterization

- `LQDParams(L, R, a)` frozen dataclass; `a[i]` = Legendre coefficient
  a_{i+2}; order N = len(a)+1; wire vector theta = (L, R, a_2..a_N).
- Model: l(u) = -log u - log(1-u) + (1-u)L + uR + sum_{n>=2} a_n P_n(1-2u).
- Legendre via stable three-term recursion (n+1)P_{n+1} = (2n+1)xP_n - nP_{n-1}.
- Everything evaluated in the logit coordinate z = log(u/(1-u)):
  dQ/dz = e^{g(Lambda(z))}. Pipeline (quadrature.py::build_slice):
  1. g on the cached grid; overflow guard: max g <= EXP_BUDGET=700 else
     clean ValueError ("interior overflow").
  2. dq_dz = exp(g); anchored Qbar(z) = cumulative Simpson of e^g, anchored
     at the center node z=0.
  3. Martingale: mass = exp(Qbar) * u(1-u); total = trapz + two analytic
     tail corrections exp(Qbar[+-Z] -+ Z)/(1 -+ a_right/left);
     mu = -log(total); q_z = mu + Qbar. Guard max Qbar too.
  4. Reverse cumulative for upper share A(z) with right-tail correction.
  Exact nodal derivatives dq_dz and da_dz = -e^Q u(1-u) stored on the slice
  => cubic Hermite interpolation is O(h^4) with NO spline solve.
- Endpoint scales: A_L = exp(L + sum a_n), A_R = exp(R + sum (-1)^n a_n)
  (P_n(1)=1, P_n(-1)=(-1)^n). Admissibility A_R < 1 - EPS_AR, EPS_AR=1e-6,
  hard reject in build_slice.
- Lee psi in the stable form psi(p) = 2 - 4/(sqrt(1+1/p)+1) — the naive
  2-4(sqrt(p^2+p)-p) loses +p once p>1e15 and returns ~2 where truth ~0.
  Underflow guards: A==0 => beta=0 (finite limit, was a ZeroDivisionError
  500 on a far-dated node); A_R>=1 => beta_R=2.

## 2. Quadrature & pricing numerics

- Grid: uniform z in [-40, 40], N_POINTS=8001 (odd => z=0 is a node);
  optimization grid OPT_N_POINTS=2001, accepted fit rebuilt at 8001
  (parameters agree ~1e-6).
- cumulative_simpson (4th order) with dx= (uniform fast path), trapezoid
  fallback for old scipy.
- Cached parameter-independent pieces: `_static_grid` and `_legendre_grid`
  lru_cached, returned READ-ONLY (writeable=False so an accidental in-place
  write errors). build_slice runs ~900x per FD fit — the cache was ~40% of
  build_slice, part of a measured 2.7x fit speedup (96 -> 35 ms).
- u(1-u) formed as expit(z)*expit(-z) — naive u*(1-u) collapses to 0 once
  expit(z) rounds to 1 (z > ~36.7).
- call_price: C = A(z_k) - exp(k - logaddexp(0, z_k)) — cash leg in log
  space (same expit-rounding hazard; a REAL production bug: far right wing
  stepped up to the bare share, caught by the randomized audit).
- Beyond-grid asymptotes (both sides), continuous at the seam, same tail
  form as the truncation corrections:
      right: C(k) = e^{k - z_r} A_R/(1-A_R), z_r = Z + (k - Q(Z))/A_R
      left:  P(k) = e^{k + z_l} A_L/(1+A_L), z_l = -Z... (mirrored)
  Needed so the functional band's Jacobian does not die at the grid edge.
- density(): f_X(Q(u)) = u(1-u)e^{-g} evaluated fully in log space
  (log pdf = -logaddexp(0,-z) - logaddexp(0,z) - g) so far tails never
  underflow. Positivity is STRUCTURAL — there is no positivity penalty
  anywhere in the codebase.
- Var swap closed form: w_vs = -2 trapz(q_z * u(1-u), z).
- Exact ATM handles (atm.py): C'(0) = -(1-u_0), C''(0) = f_0 - (1-u_0),
  then implicit differentiation through the Black partials — no FD of IV.

## 3. Calibration

Objective (vega-normalized PRICE residuals, so loss ~ vol error):

    min_theta sum_i w_i ((C_lqd(k_i) - target_i)/(vega_i + eta))^2
              + lam sum_{n>=4} n^{2r} a_n^2        (a_2, a_3 unpenalized)

- eta = _VEGA_FLOOR = 1e-4; targets precomputed: target_price =
  black_call(k, w_quotes), inv_vega from black_vega at quote vol.
- Stacked residual = concat(fit, reg, cal_G, cal_price, [barrier],
  varswap, prior_anchor, prior_varswap, operator_prior).
- Fit modes: mid | bidask | haircut. Band residual per quote:
  relu(model-hi) + relu(lo-model), PLUS sqrt(0.05) * (model - mid) anchor;
  haircut tightens: lo = min(iv_bid + h, iv_mid), hi = max(iv_mid,
  iv_ask - h), h default 0.005 (0.5 vol pt). A quote tighter than 2h
  degenerates to a mid fit on that strike. Band specified in vol, converted
  ONCE to price edges: price_lo = black_call(k, iv_lo^2 t) etc. Band mode
  doubles the fit rows (violation + anchor).
- Regularization: reg = sqrt(lam) * n^r for n>=4 (defaults lam=1e-6, r=1).
- A_R admissibility, two layers: hard reject in build_slice caught by the
  calibrator returning a LARGE FINITE residual (10.0 + a_right — a
  non-finite residual would poison trf's step control); smooth soft barrier
  softplus via logaddexp(0, 50*(A_R - 0.90)) (log1p(exp(x)) overflows at 709).
- Calendar, two independently-nullable blocks sharing weight 1e6:
  (a) G(alpha)-space slack keyed on z-VALUES (exact on the coarse grid);
  (b) support-confined price-space floor — production surface path:
      sqrt(w) * taper * relu(C_floor(k_m) - C(k_m)) on the intersection of
      retained quote spans, cos^2 C1 taper (frac 0.15 of span, min 0.05,
      max 0.25). Constraint-node count scales with order:
      n_nodes = max(49, 4*N + 1) — a fixed grid lets a high-order slice
      slip a violation between nodes.
- Solver: scipy least_squares trf, xtol=ftol=gtol=1e-10, max_nfev=4000.
  1e-10 is ~6 orders below the ~5 vol bp fit budget; stops trf grinding
  (P+1)-eval iterations chasing 1e-15.
- Warm starts: logistic_init (a=0, L=R=log s, s = sqrt(3 w_0)/pi from
  Var(Z)=pi^2/3); sequential surface threads prev.params; init discarded on
  order mismatch.
- Order guard (API layer): effective order = clamp so params N+1 <=
  quotes/2, floor min(N, 6). Measured failure modes: error-bar saturation
  at params ~ quotes-1; latency cliff on a 19-quote 0DTE book —
  params/quotes 0.47 -> 7 evals/20 ms; 0.58 -> 63/166 ms; 0.68 -> 2568
  evals/7.6 s. Locked by perf tests (19 quotes => N=8; 40 quotes => N=16).

## 4. Optimization charts (lqdCoords)

- "lr": raw theta = (L, R, a). Identity (chart object None, fast path).
- "endpoint": phi = (log A_L, log A_R, a_2..a_N), theta = M phi with M
  unit-determinant: M = I except row0[2:] = -1, row1[2:] = -(-1)^n. Body
  modes become endpoint-neutral (a_2 bump no longer multiplies both tails
  by e^{0.10} ~ 1.105).
- "logistic" (production default): A_R = expit(rho). Stable maps:
  log A_R = -softplus(-rho) = -logaddexp(0,-rho); inverse rho = la -
  log(-expm1(la)). d log A_R/d rho = 1 - A_R = expit(-rho) — compresses
  trust-region steps exactly at the wall; the admissible set is the whole
  chart. Chain rule wraps fun/jac; solution Jacobian pulled back to
  canonical coordinates. Caveat: removes the mathematical wall, not the
  floating-point one — beyond rho~36, A_R rounds to 1.0; EPS_AR stays.
  Chart-independence of the optimum is TESTED (params to 1e-5, information
  matrices J^T J to 1e-3 relative).

## 5. Analytic Jacobian (jacobian.py)

- Central identity: with C(k) = A(z_k) - e^k(1-u_k) and Q(z_k)=k, at z_k
  the slope dA/dz = -e^Q u(1-u) = -e^k u_k(1-u_k) EXACTLY cancels
  d/dz[e^k(1-u_k)], so the moving-root terms drop and dC/dtheta =
  hermite_eval(z_k; dA/dtheta, d(dA/dz)/dtheta).
- slice_sensitivities: ONE quadrature pass gives all nodal theta-
  sensitivities (O(P n_grid) — removes rebuilds, not linear-in-P work).
- Var-swap row rides the same pass: dw_vs/dtheta = -2 int (dQ/dtheta)
  u(1-u) dz, chained by dsigma/dw = 1/(2 sqrt(w t)). Before this, a
  var-swap target forced the whole fit to finite differences.
- Eligibility: analytic when prior_anchor and operator_prior are absent;
  matches 3-point FD to <1e-3 relative in all configurations (tested).
- Measured: analytic vs FD calibration 1.44-1.97x; the earlier headline
  "2.7x" was the grid-cache+coarse-grid work, a separate win.

## 6. Downstream instruments (paper: mention, annex: summarize)

- ATM-orthogonal chart (ortho.py): J = 3xd FD Jacobian of handles
  H=(w_0, skew, curv); primary directions U = right inverse (Euclidean or
  GN-metric G = J_r^T J_r from the converged residual Jacobian:
  U = G^{-1}J^T (J G^{-1} J^T)^{-1}, Tikhonov floor 1e-8 tr(G)/d); shape
  directions = QR of the projector kernel; retarget = exact 3-d Newton
  (tol 1e-12). HONEST caveat: kernel basis unique only up to rotation —
  session-local, not persistent trader coordinates; hence...
- packages.py: stable vocabulary = market packages RR25/BF25/RR10/BF10/
  VarSwap (ATM excluded, handles own it). xi_i = argmin |xi| s.t.
  (dP/dtheta V) xi = e_i via SVD pseudo-inverse; returns cross-talk matrix
  dP/dtheta . directions (identity iff independent) + condition + rank.
- band.py: delta-method functional bands from the 3x3 handle posterior:
  6 perturbed slices (2 per handle, FD steps (3e-4, 5e-4, 5e-3) = 1e-2 x
  natural handle scales) price EVERY functional at once (IV band, var-swap
  sd, density band, exact tail-mass sd via CDF(k) = u(z_k)). PSD-clip the
  covariance; degradation UNDER-states (fallback dIV/dsigma_0 = 1 exact at
  ATM; skew/curv contribute nothing) — "under-stating beats fabricating".
- Fritsch-Carlson certificate (interp.py::hermite_monotone_margin):
  monotone on a segment if both endpoint derivatives in [0, 3*secant];
  margin = min over active segments of min(d0, d1, 3s-d0, 3s-d1); segments
  with everything < flat_tol=1e-9 (underflowed far tail) are certified
  flat-to-tolerance — state this caveat. Certify decreasing curves by
  negation. This is the "the discretization must EARN the continuous
  theorem" audit.
- Belly certificate (diagnostics.py): Durrleman g on 801 points over the
  TRADED range, g >= -1e-4, from the model's own w(k) derivatives (never
  differenced prices); ~0.05 ms; failing it blocks publish. Grid density:
  the Axel Vogt dip is -0.033 and spans ~0.02 in k.

## 7. Certification battery (numbers the paper can cite as "our audit")

60 randomized slices (orders 4/6/8/12/16 x plain/near-wall(A_R<=0.993)/
wild-body x 4 draws), drawn THROUGH the logistic chart, audited at sub-grid
strikes in STRIKE space K = e^k (auditing convexity in log-strike was the
battery's own first bug — C is legitimately concave in k deep ITM).
Measured worsts: bounds 1.2e-9, butterfly 1.0e-14, digital 3.7e-12,
8001-vs-32001-grid price agreement 2.6e-9. Plus: far-wing no-rounding-step
lock (z_k > 37, subtrahend > 1e-4, agreement < 1e-15), seam
continuity/monotonicity of beyond-grid asymptotes, interior-overflow clean
refusal, double-hump bimodality lock (exactly 2 modes, mixture reproduced
to 15 vol bp), chart equivalence on 12 live nodes |dtheta| 3.6e-7.

## 8. Timing (medians, warm cache, single-threaded)

- One slice fit, 40-quote strip: ~35 ms at N=6 (was ~95 before the grid
  cache + coarse-grid work), ~29 ms at the shipped N=16 (analytic
  Jacobian). Warm 0DTE slice at guarded N=8: ~20 ms. CI rail 350 ms.
- Vectorized implied_total_variance (safeguarded Newton "rtsafe", BS seed
  w ~ 2 pi tv^2, analytic vega, bisection fallback): ~39x on a 241-pt
  curve render (27 -> 0.7 ms), matches Brent to ~1e-13.
- Methodology for reported numbers: median + IQR from ONE interleaved run
  (11 alternating analytic/FD solves per order after a warm-up) — never
  fastest-of-three.

## 9. Paper-relevant entry points (annex "map of the implementation")

build_slice (quadrature), LQDSlice.call_price / .density /
.var_swap_strike, g_eval + legendre_matrix, endpoint_scales + lee_slopes +
lee_psi, calibrate_slice (objective spec), residual stack, 
slice_sensitivities + residual_jacobian, endpoint_transform + build_chart,
effective order guard, atm_handles, build_atm_coordinates +
gauss_newton_metric, hermite_monotone_margin, functional_band,
confined_calendar_floor, band_residuals, implied_total_variance,
belly_certificate.
