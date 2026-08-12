# Generalized LQD tails + full-line calendar — implementation roadmap

Adopted 2026-08-12 (user-ratified decisions below). Source of truth for the
mathematics: **book Chapter 2** (`Papers/book/chapters/02_lqd/`, the rewrite
integrated 2026-08-12), which derives the generalized tail family and the
full-line calendar certificate. Equation references below are to that chapter.
Status: GREEN-LIT (user, 2026-08-12) — the current implementation arc.
Work the phases in order, starting at Phase 0; commit per green batch.

## The two features

1. **Generalized tails.** Two per-side tail exponents `α−, α+ ∈ [0, 1/2]`
   interpolate the log-return tails from exponential (`α = 0`, today's model,
   exactly) to Gaussian rate (`α = 1/2`), asymmetrically. Transport speed
   becomes `dQ/dz = e^{g} · ℓ−(z)^{−α−} · ℓ+(z)^{−α+}` with gauges
   `ℓ∓(z) = 1 + softplus(∓z)` (eq. ellgauges / xspeed). Consequences derived
   in the chapter: moment domain (α > 0 ⇒ all moments on that side finite),
   Lee slope 0 with sublinear wing law
   `w(k) ~ ½ (λ/(1−α))^{1/(1−α)} · |k|^{(1−2α)/(1−α)}` (eq.
   rightsublinearwing), the λ+ < 1 wall replaced by the numerical saddle
   guard `x'(Z_max) ≤ 1 − ε` (eq. operationaltailguard), Gaussian reference
   law `λ = s/√2` at `α = 1/2`.

2. **Full-line calendar order.** Ledger order ⇔ call order on the whole line
   (thm. ledgerorder); the gap `ΔG = G_far − G_near` is monotone between
   quantile-curve crossings (eq. calgapderivative), so a **finite
   certificate** — evaluate ΔG at every crossing root, the grid boundaries,
   and the analytic tail order — proves the continuum property. Tail-policy
   coupling: with common exponents, `λ±` must be nondecreasing in maturity
   (eq. tailscalecalendar); a farther expiry can never have a lighter
   asymptotic tail.

## Ratified decisions (2026-08-12 — do not re-litigate)

- **α scope: per-underlier, common across expiries.** One `(α−, α+)` pair
  applies to the whole maturity stack. Per-expiry variation (monotone
  no-lighter-far-tail rule) is a recorded later option, not v1.
- **α is a fixed policy input, never optimized.** The book's §2.5.4 argument
  is binding: any small α > 0 is indistinguishable from α = 0 on a finite
  strike strip while flipping the moment domain — per-slice estimation is
  ill-conditioned. Scenario fits are the comparison instrument.
- **Calendar enforcement: both, phased.** Phase 0 ships the exact
  certificate as the acceptance/publish authority on top of today's
  penalty+escalation solver; the in-solver active-set exchange (hard
  constraints, book-faithful) is a later phase (Phase 4).
- **Compatibility bar: `α− = α+ = 0` is the default and must produce
  byte-identical fits.** The full suite (959 tests incl. golden fits) stays
  green unmodified; new behavior enters only behind non-default settings and
  new goldens.

## Where the code stands today (survey 2026-08-12)

- The tail is hard-coded exponential: `dQ/dz = e^g`
  (`volfit/models/lqd/quadrature.py`, `build_slice` ~:218-278), closed-form
  tail masses `1/(1−A_R)`, `1/(1+A_L)`, linear tail continuation in
  `call_price` (~:150-171). `endpoint_scales`/`lee_slopes` in
  `models/lqd/basis.py` assume the exponential class and the `A_R < 1` wall
  (`EPS_AR`, quadrature ~:47, build_slice ~:229). No tail-exponent notion
  anywhere in backend code (grep-confirmed).
- Calendar enforcement already goes beyond quoted strikes: full-grid ledger
  floor rows on a stride-25 z-subgrid (`calib/calendar.py` ~:208-227 +
  `models/lqd/calibrate.py` ~:129-134), confined tapered price floor over
  common support, symmetric-solver seam/wing-slope tail contract
  (`calib/symmetric.py` ~:158-181, `calib/symmetric_stack.py`), extrap-region
  hinges (`calib/extrap.py`), publish-time wing projection
  (`models/projection.py`) and publish blockers (`api/export.py`
  `_node_blockers` ~:291-308), quality checks sampled on grids
  (`api/quality.py` ~:155-193). **Missing vs the book:** the *exact*
  crossing-root certificate (current checks are sampled), the
  min-adjacent-ledger-gap as a published number, and hard-constraint
  acceptance semantics.

## Phase 0 — Exact full-line calendar certificate (α = 0), publish authority

**Status: DONE 2026-08-12.** Shipped as specced with one recorded
refinement: the certificate isolates the roots of the *gap derivative* — the
closed-form per-segment quadratic that interpolates eq. calgapderivative's
right-hand side at the nodes — rather than the cubic quantile-crossing
roots. That set is EXACT for the stored Hermite ledger (the object
`call_price` prices), strictly stronger than sampling and equivalent to the
chapter's candidate set in the continuum limit; locked against a 16× dense
scan. The limiting-tail-order clause (eq. tailscalecalendar) is reported but
ADVISORY until Phase 2's endpoint-chart monotonicity rows exist — a publish
gate a fit cannot yet be asked to satisfy would block with no repair path
(recorded in the module docstring). Certification case:
`full_line_calendar_certificate`.

New module `volfit/calib/calendar_certificate.py` (small, standalone):

- Both slices of an adjacent pair share the same cached z-grid, so
  `Q_far − Q_near` is a nodal difference with nodal derivatives; isolate its
  roots per cubic-Hermite segment (a cubic root problem per segment,
  vectorized), add the two grid boundaries, the analytic tail roots under
  the linear continuations, and the limiting order decided by
  `(a_left, a_right)` (tie → the next asymptotic constant).
- Evaluate `ΔG = far.a_z − near.a_z` (Hermite) at all candidates. Output:
  min gap, its z/strike location, per adjacent pair. Degenerate segments
  (transports identical on a segment) contribute an endpoint only —
  ΔG is constant there by eq. calgapderivative.
- Wiring: `api/quality.py` (next to `calendar_violation_argmax`) — the exact
  certificate becomes the acceptance authority; the stride/window sampled
  diagnostics remain as cheap in-loop screens. `api/export.py`: publish
  `minAdjacentLedgerGap` (+ location) per pair; `_node_blockers` consumes
  the certificate, not the sample. Certification-pack case registered in
  `backend/backtest/certification.py` `CASES`.
- Tests: agreement with a brute-force dense scan on the frozen fixtures; a
  rigged pair whose violation sits between stride-25 nodes (sampled screen
  passes, certificate catches); perf rail (vectorized cubics, target well
  under the fit budget per pair).

Exit: certificate live in quality + publish, cert case green, no fit output
changes anywhere.

## Phase 1 — Generalized tail core (model layer)

**Status: DONE 2026-08-12.** Shipped as specced: alphas ride `LQDParams` as
validated config fields (`to_vector`/`from_vector` untouched — theta length
locked by test); the gauges fold into the ONE exponent that builds dQ/dz
(cached log-gauge arrays; α = 0 skips the branch — byte-identity is
test-locked across arrays, prices, density and the full suite's golden
fits); α > 0 tail masses/roots/prices live in the new
`volfit/models/lqd/tails.py` (log-domain Gauss–Legendre under the power
continuation, saddle guard as a build refusal, wall confined to α+ = 0);
`lee_slopes` branches to 0 and `wing_law()` exposes (class, exponent,
coefficient) per side. Goldens: `tests/test_generalized_tails.py` — the
α± = 1/2 constant-speed slice at λ = s/√2 checked against
scipy.integrate.quad (transport, both tail masses, beyond-grid calls),
martingale/symmetry/density, wing constant 2λ² = s², moment-domain flip
read off far-price decay, α-continuity, asymmetric mixes.

- `LQDParams` (`models/lqd/basis.py`) gains `alpha_left / alpha_right`
  **as model config, NOT theta components** — `to_vector`/`from_vector`
  unchanged, so the observation-filter state dimension, prior wire vectors,
  and graph handle Jacobians are untouched at any α.
- `quadrature.py`: gauge factors on `dq_dz`; **α = 0 takes the existing code
  path exactly** (no pow, no reordered float ops — byte-identity is a test).
  Cache the parameter-independent gauge arrays alongside the LRU static
  grid. Tail masses: α = 0 keeps the closed forms; α > 0 uses log-domain
  quadrature under the `(z+1)^{1−α}` continuation (eq. rightcontinuation)
  plus the saddle guard `x'(Z_max) ≤ 1 − ε` (refusal, mirroring the
  interior-overflow pattern). `call_price` tail branches use the power-form
  root (eq. rightroot) and `c ≈ e^{k−z_R} x'/(1−x')` (eq. beyondgrid).
- `basis.py`: `lee_slopes` branches — α > 0 ⇒ Lee slope 0; expose a
  `wing_law()` descriptor (class, exponent `(1−2α)/(1−α)`, coefficient)
  for plotting and the symmetric tail rows.
- Wall semantics: `A_R ≥ 1 − ε` refusal applies only when `α+ = 0`.
- New goldens: the Gaussian reference law `X ~ N(−s²/2, s²)` with
  `α± = 1/2`, `λ = s/√2` — transport, martingale shift, prices, density,
  wing constant `2λ² = s²`; α-continuity spot checks (small α ≈ α = 0 on
  the quoted strip, moment domain flips).

Exit: `build_slice`/`call_price`/`density`/`var_swap_strike` correct for all
α ∈ [0, 1/2]²; byte-identity test at α = 0; Gaussian golden battery green.

## Phase 2 — Calibration & policy layer

- `FitSettings` (`api/schemas.py`): `tailAlphaLeft`, `tailAlphaRight`
  (default 0.0, bounds [0, 0.5]), persisted per underlier (settings
  persistence + options-version bump, `api/state.py` pattern). Applied at
  slice-task packaging (`api/service.py` `_slice_task`).
- `charts.py`: right endpoint chart branches per eq. rightchart —
  `α+ = 0`: existing logistic wall chart; `α+ > 0`: unconstrained
  `log λ+`. Left chart unchanged.
- `jacobian.py`: sensitivity pass under fixed α — gauge factors multiply the
  speed everywhere the pass touches `dq_dz`; tail-correction derivatives
  gain the α branches. **No α columns** (fixed-α policy).
- Stack coupling (symmetric solver): with common α, add `λ±` monotonicity
  rows in the endpoint chart (generalize `endpoint_rows` /
  seam-and-slope tail rows in `symmetric_stack.py` to the α-aware wing
  law); exact ties delegated to the Phase 0 certificate.
- **Rider from Phase 1 (recorded 2026-08-12):** the Phase 0 certificate's
  analytic tail candidates/order clause still assume the exponential
  (α = 0) continuation — generalize `calendar_certificate._tail_candidates`
  to the power continuation (equal-α pairs: same crossing structure in the
  (z+1)^{1−α} variable) before α > 0 stacks can reach quality/publish.
- Untouched: order guard, ridge, band/haircut machinery, prior anchors.

Exit: full stack fit under a nonzero α scenario on the reference fixture;
suite green with α = 0 byte-identical; Jacobian FD tests extended to α ≠ 0.

## Phase 3 — Surfaces, UI, wire formats, scenarios

- Wire/artifacts: `lqdParams` gains optional `alphaL`/`alphaR` (absent ⇒ 0,
  old workspaces load unchanged) in export, history, workspace, prior
  records; prior transport carries them (`api/prior_transport.py`). The
  priors' `lqd` theta vector is NOT extended (length stays order+1).
- Smile viewer: remote wings rendered from the α-aware wing law rather than
  inverting underflowed prices (the chapter's publication-chart rule; the
  far-wing no-rounding-step test pattern extends).
- Hyper-parameters panel: per-side α controls under the LQD model section —
  presets exponential 0 / intermediate 0.25 / gaussian 0.5 + numeric entry,
  per-underlier scope, disabled unless model = LQD. Options version bump.
- Scenario compare (the book's preferred practice): fit the same stack under
  a small α grid and report downstream deltas — var-swap strike, moment
  limits `r±*`, tail digitals, RR/BF packages. First as a backtest-style
  artifact/report; UI table later.

Exit: a saved workspace round-trips alphas; UI smoke green; scenario report
runs on the reference fixture.

## Phase 4 — In-solver active-set exchange (hard calendar constraints)

The book's exchange loop on top of the joint stacked solve
(`symmetric_stack.joint_refit`): solve with the current active rank set →
run the Phase 0 certificate → add the worst violating rank per pair →
repeat until the certificate passes. Reuse the calendar-G row + analytic
Jacobian machinery (`jacobian.py` calendar rows) with per-rank targeting
instead of the stride grid. Exit gates: no accepted surface fails the
certificate; benchmark-pack fit-quality regression bounded; perf rail.

## Risks & gotchas (recorded up front)

- **Never estimate α in-solver** — the α → 0 limit is nonuniform (Lee slope
  jumps); scenario policy only.
- **Saddle guard, not truncation**: for α+ > 0 with large λ+, the martingale
  integrand can peak beyond Z_max = 40 — refuse the build (as the wall does
  today), never silently truncate the mass.
- **Byte-identity discipline**: the α = 0 fast path must not multiply by
  `ℓ^0` or reorder ops; goldens pin this. `tests/conftest.py` pins serial
  calibration — keep it for the identity tests.
- **Wire compatibility**: alphas ride as sibling fields, theta length is
  load-bearing across priors/filter/graph (`to_vector` contract).
- **Perf**: gauges are parameter-independent per grid — cache them; the
  α = 0 path must show zero regression on the calibration perf rails.
- **Frozen artifacts**: the book's frozen fits and the app's golden fits all
  use α = 0; nothing regenerates.

## Registration

- ROADMAP.md STATUS → Next-up carries the pointer to this file.
- Conventions as everywhere: golden tests against the chapter's equations,
  module docstrings citing equation numbers, files ≤ 400 lines, commit per
  green batch.
