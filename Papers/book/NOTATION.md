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

## Chapter 5 — integrals and wings (variance swaps beyond the last quote)

The chapter is mostly a consumer of earlier ledgers: `w, σ, τ, k, y, c, P,
B, Q, Λ, ρ, x, m, G, λ±, r±*, Ψ, g_D, β_L, β_R, β, β_max, v(τ,y), f(τ,y)`
are recalled, never redefined.  New symbols:

| Symbol | Meaning |
|---|---|
| `w_vs` | fair variance-swap strike in total-variance units (`w_{\rm vs}`; first written in Ch. 2 eq. (varswap), adopted book-wide here) |
| `σ_vs = √(w_vs/τ)` | the same number quoted as a volatility |
| `v_τ` | instantaneous variance along the path (§5.1 derivation; in Ch. 4's representative model it is the field `v` evaluated on the path — the subscript marks a process, the parenthesized `v(τ,y)` stays the field) |
| `𝒲(τ,y)` | expected remaining variance to expiry (the field-side backward function; Ch. 3's scalar hinge multiplier `W` and Wasserstein `W_p` are unrelated) |
| `𝒮(k)` | cumulative accrual of the strike-side var-swap integral up to log-strike `k`, as a share of `w_vs` (§5.3) |
| `k̄, c̄, s̄` | the last quoted call-side log-strike, the normalized call there, and the last secant slope in strike — bars mean "frozen at the last quote" (§5.5; the put side is mirrored in words; `ȳ = e^k̄`) |
| `w^+(k), w^-(k)` | upper and lower edges of the envelope of admissible completions beyond the last quote (§5.5) |

## Chapter 6 — forwards, dividends, and carry

Part II works on raw dollar quotes, before normalization is available.  New
convention introduced here: an upright sans-serif letter marks a *raw market
quote* (`𝖢(K)`, `𝖯(K)`); Ch. 2's normalized `c`, `P` are unchanged.  Hats
mark least-squares estimates (`F̂`, `D̂`, `r̂`).  Reserved letters are
never reused bare: the regressed observable is `Π` (not the reserved `y`),
the dividend yield is `q_d` (bare `q` stays the quantile density), cash
dividends are `d_i` (the differential stays upright `\dd`).

| Symbol | Meaning |
|---|---|
| `S` | spot — today's traded level (`Y = S_T/F` keeps its Ch. 2 role) |
| `K` | dollar strike (`k = log(K/F)` connects to the normalized ledger) |
| `t` | calendar year fraction to expiry (`T` stays the expiry date; `τ` stays variance time; discounting and carry always accrue on `t` — Ch. 8 separates the two clocks) |
| `𝖢(K), 𝖯(K)` | observed dollar call / put mid at strike K (sans-serif = raw quote) |
| `Π(K) = 𝖢 − 𝖯` | price of the parity portfolio (long call, short put) — the regressed observable |
| `ε` | quote-noise standard deviation of one mid (dollars) |
| `n` | number of paired strikes in a parity fit |
| `K̄`, `K̄_μ` | mean strike; μ-weighted mean strike (μ_i in its Ch. 3 role: per-quote weights) |
| `S_KK` | strike dispersion `Σ_i (K_i − K̄)²` (regression sum of squares) |
| `F̂, D̂, r̂` | least-squares estimates of forward, discount, implied rate |
| `r` | implied rate `−log D/t` (Ch. 2's `r±*` is always starred) |
| `q_d` | dividend yield (continuous-mode carry; subscripted — bare `q` reserved) |
| `d_i, t_i` | cash dividend amounts and their ex-date year fractions (always subscripted) |
| `f_i` | proportional dividend fractions (always subscripted; the densities `f*`, `f(τ,y)` keep their Ch. 2/4 roles) |
| `PV` | present value of a dividend schedule (roman, two letters — `V` stays MCS's) |
| `b, b_min` | borrow spread (residual carry); its identifiability floor |

## Chapter 7 — removing early exercise

The chapter deliberately introduces almost nothing.  The observed American
mids are Ch. 6's raw quotes `𝖢(K)`, `𝖯(K)`; the carry pair `(r, q_d)` and
calendar `t` are Ch. 6's.  The early-exercise premium has NO symbol: it is
always written `A − E` or named in words (a symbol used fewer than three
times in display math would violate the contract's symbol budget).

| Symbol | Meaning |
|---|---|
| `A(σ)` | American model (tree) price of one option as a function of σ, all else fixed |
| `E(σ)` | its European twin: the same tree with the stopping right removed |
| `A_j^{(n)}, E_j^{(n)}` | node values on tree layer n, node j (§7.3 rollback) |
| `σ*` | the de-Americanized volatility: the root of A(σ*) = quoted mid (star = distinguished value, as `u*`, `f*`) |
| `p` | CRR up-move probability (Ch. 3's JW slope stays `p_J`; Ch. 4's adjoint states stay `p^n`) |
| `N_t, Δt` | tree step count on the calendar clock and the step `t/N_t` (Ch. 4's `N_τ, Δτ` pattern; `Δt` composite, no clash with bare `Δ`) |
| `ϑ, 𝒯` | a stopping time; the set of stopping times on [0, t] (§7.2 only; `ϑ` is vartheta, kept visually apart from Ch. 3–4's `θ`) |

Note on `E`: italic `E` is always a PRICE in this book; the expectation
operator stays blackboard `𝔼`.  Stated once at first use in §7.1.

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
