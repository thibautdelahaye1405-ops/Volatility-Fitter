# The book's notation ledger

One ledger for the whole book. A chapter ADDS its symbols here before using
them; it never redefines an existing one. Conventions (book-wide): a prime
denotes the ordinary derivative of a one-variable function; `∂` denotes a
partial derivative; τ is always variance time; at most one boxed display per
chapter.

## Chapter 2 — the log-quantile-density model (the founding ledger)

| Symbol | Meaning |
|---|---|
| `X`, `Y = e^X` | log and gross forward return |
| `u`, `z = logit u` | rank (percentile) and log-odds |
| `k`, `y = e^k` | log and normalized strike |
| `Λ`, `ρ` | logistic CDF and density |
| `c`, `P` | normalized call and put |
| `Q`, `q = Q'` | quantile function and quantile density |
| `w = σ²τ` | total implied variance (`σ` implied vol, `τ` variance time) |
| `g` | smooth log-speed in rank (the LQD object) |
| `x`, `m` | transport and martingale shift |
| `G` | upper-share ledger |
| `L, R, a_n` | LQD polynomial coordinates |
| `λ₋, λ₊` | endpoint speeds |
| `u_k, z_k` | strike rank and log-odds |
| `u*, f*, Δ` | ATM rank, density, digital gap |
| `β_L, β_R` | Lee wing slopes (left/right, in total variance per \|k\|) |
| `N, Z_max` | basis order and grid half-width |
| `g_D` | Durrleman function (positive density in the volatility chart) |
| `δ` | butterfly half-width (certificate check) |
| `h` | haircut (band shrink, vol points) |
| `η` | vega floor |
| `α, ν` | ridge weight and power |
| `Ψ` | (reserved by Ch. 2) |

Also in general use from Chapter 2 on: `B` the Black call formula, `Φ`, `φ`
the normal CDF/density, `F` forward, `D` discount factor, `T` expiry date.

## Chapter 3 — SVI-JW and superposition

Rule applied here: literature names that collide with the founding ledger are
subscripted, never silently reused. Raw SVI carries subscript `S`; the five
jump-wing handles carry subscript `J` (always subscripted — `ψ_J` never
appears bare, keeping it apart from Ch. 2's `Ψ`; `c_J` apart from the
normalized call `c`). Chapter-3 *constructions* use calligraphic letters.

| Symbol | Meaning |
|---|---|
| `a_S, b_S, ρ_S, m_S, s_S` | raw SVI: level, steepness, tilt, center, width |
| `x_S, r_S, q_S` | SVI shorthands `k−m_S`, `√(x_S²+s_S²)`, `√(1−ρ_S²)` |
| `v_J` | JW ATM variance rate `w(0)/τ` (ATM IV is `√v_J`) |
| `ψ_J` | JW ATM slope of total volatility, `(√w)'(0)` |
| `p_J, c_J` | JW normalized put/call wing slopes `β_L/√w₀`, `β_R/√w₀` |
| `ṽ_J` | JW minimum variance rate `min w/τ` |
| `w₀` | ATM total variance `w(0)` (Ch. 2's `w` evaluated at `k=0`) |
| `I(k)` | working implied volatility `√(w(k)/τ)` |
| `χ` | normalized vertex displacement `m_S/√(m_S²+s_S²)` |
| `𝒟` | JW-inverse denominator (≥0 by Cauchy–Schwarz; ~`ψ_J²` near 0) |
| `β` | generic total-variance wing slope (β_L, β_R specialize) |
| `β_max` | wing-slope cap, strictly inside Lee's bound 2 |
| — | Lee moment budget reuses Ch. 2's `r±* = Ψ⁻¹(β) = (2−β)²/(8β)` |
| `W` | hinge-row multiplier (scalar; Ch. 2's Wasserstein always `W_p`) |
| `θ` | optimization-chart coordinate vector (componentwise θ₁..θ₅) |
| `k*, w*, κ*` | structural chart: vertex location, floor, vertex curvature |
| `ζ` | MCS standardized moneyness `k/(σ_ref √τ)` (NOT Ch. 2's z=logit u) |
| `ζ̄` | displacement along the ζ axis (kernel/base argument) |
| `σ_ref` | MCS reference volatility fixing the ζ scale |
| `𝒜_κ` | log-cosh primitive `(4/κ²) log cosh(κζ̄/2)` (softened \|·\|) |
| `V, V₀, V₁, V₂, ζ₀, κ_P, κ_C` | MCS base curve: level/slope/convexity at ζ₀, wing steepnesses |
| `𝓑_{ζ_r,ℓ_r,κ_r}` | zero-wing kernel: center, half-width, steepness |
| `γ_r, M` | signed kernel amplitude; number of cores (`R` stays LQD's) |
| `β_P, β_C` | MCS base wing slopes in k-space |
| `μ, μ_i` | strike-axis measure a fit integrates against; per-quote weights |
| `TV(k), TV_i` | time value: normalized OTM option price at a strike |
| `C_i, \|C_i\|` | quote i's Voronoi cell on the strike axis and its width |

## Chapter 4 — local volatility

Bare `v` is claimed here for the local-variance field (it was free: the JW
handles are always subscripted `v_J`, `ṽ_J`). The strike axis reuses Ch. 2's
`y = e^k`. Calligraphic letters name the chapter's operators; composite step
symbols `Δτ, Δy` do not collide with Ch. 2's bare `Δ` (digital gap).

| Symbol | Meaning |
|---|---|
| `v(τ, y)` | local-variance field (σ_loc² per unit variance time) |
| `σ_loc = √v` | local volatility (prose; never a formula symbol) |
| `f(τ, y)` | density of Y_τ (Ch. 2's density with the maturity explicit) |
| `𝓛` | Dupire generator ½ v y² ∂_yy, and its lattice discretization |
| `𝓜 = I − Δτ 𝓛` | implicit step matrix (an M-matrix) |
| `U^n` | lattice call values after step n |
| `Δτ, Δy` | lattice steps (`Δy_i^±` the non-uniform gaps) |
| `(τ_i, y_j), θ_ℓ, n_θ` | vertex grid; nodal local variances (θ in its Ch. 3 ledger role: optimization-chart coordinates); vertex count |
| `ℋ_ℓ` | hat (tent) basis function of vertex ℓ |
| `v_lo, v_hi` | nodal variance box |
| `a` | left-wing continuation slope multiple (LQD coefficients stay `a_n`) |
| `Γ` | spacing-aware second-difference (curvature) operator on the vertex grid |
| `λ, λ_0` | roughness weight; front-tie weight (endpoint speeds stay `λ±`) |
| `θ_ref` | roughness reference sheet |
| `η_q` | per-quote vega scale (Ch. 2's vega floor `η`, per quote) |
| `s_ℓ^n` | tangent sensitivities ∂U^n/∂θ_ℓ (SVI's `s_S` stays subscripted-S) |
| `N_τ, N_y` | lattice step and node counts (vertex counts stay `n_τ, n_y`) |
| `b^n` | boundary data entering step n through the stencil's boundary columns |
| `p^n` | adjoint lattice states (App. 4.A only; normalized put stays `P`) |
| `𝒥, 𝒪_n` | scalar objective; observation rows (App. 4.A adjoint only) |
| `Ξ` | smooth test function in the Fokker–Planck derivation (proof-local, §4.2; chosen because both phi glyphs are in service) |

## Reservation rules

- Never reuse: `X, Y, u, z, k, y, c, P, w, σ, τ, Λ, ρ, Q, q, g, x, m, G, L,
  R, a_n, λ±, u_k, z_k, u*, f*, Δ, β_L, β_R, N, Z_max, Ψ, r±*, ξ, g_D, δ,
  h, η, α, ν` (Chapter 2) — nor Chapter 3's additions above.
- Greek letters still free after Ch. 2+3: ι, π (as constant only), υ
  (avoid — reads as u); capitals Θ (careful vs θ), Ξ, Π, Σ (avoid —
  sums), Υ, Ω, Γ (bare; Ch. 3 does not use it).
- Function-definition dummies bound inside a single display (e.g. the
  affine `L` in the zero-wing lemma) are exempt; NAMED local variables
  are not — subscript or bar them instead (`x_S`, `ζ̄`).
- New chapters add a section here in chapter order, BEFORE first use.
