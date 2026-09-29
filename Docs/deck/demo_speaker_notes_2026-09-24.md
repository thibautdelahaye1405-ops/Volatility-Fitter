# Vol-Fitter — speaker notes

Internal technical presentation for quants and traders. Rewritten 28 September 2026.

Companion: [HTML deck](demo_deck.html). The numbering and titles below match the deck. Press **N** for the notes, **O** for the contents, and use the arrow keys to navigate. The deck works offline.

The archived app captures are dated 24 September 2026. Numerical examples labelled *illustrative* explain a mechanism; recorded measurements retain their date, inputs, and scope. Volatility is stored as a decimal: one vol point = 0.01 and one vol bp = 0.0001. Calendar time is t, the pricing variance clock is τ, normalized strike is x = K/F, and log-moneyness is k = log(K/F). Inline `$…$` spans are LaTeX, as on the slides.

## Contents

- [01. Models, calibration and inference](#slide-01)
- [02. Objects and calculation order](#slide-02)
- [03. Universe, observations and fit state](#slide-03)
- [04. Snapshots, streaming and subscription coverage](#slide-04)
- [05. Synchronising quotes to the current spot](#slide-05)
- [06. Forward and discount from put–call parity](#slide-06)
- [07. Dividends, borrow and the American fixed point](#slide-07)
- [08. Removing the early-exercise premium](#slide-08)
- [09. Exercise correction: numerical cost and accuracy](#slide-09)
- [10. The units of a calibration residual](#slide-10)
- [11. Mid, bid–ask and haircut targets](#slide-11)
- [12. Quote weights and strike spacing](#slide-12)
- [13. What each model parameterises](#slide-13)
- [14. LQD: constructing a probability law](#slide-14)
- [15. LQD: quantiles to option prices](#slide-15)
- [16. LQD calibration and analytic sensitivities](#slide-16)
- [17. ATM handles and delta-based operators](#slide-17)
- [18. SVI and Jump-Wings coordinates](#slide-18)
- [19. MCS: local shape corrections](#slide-19)
- [20. Generalised LQD tail exponents](#slide-20)
- [21. Wing slopes and finite moments](#slide-21)
- [22. Variance swaps as an integrated constraint](#slide-22)
- [23. Calendar consistency across expiries](#slide-23)
- [24. Calendar repair and numerical certification](#slide-24)
- [25. A piecewise-affine local-variance surface](#slide-25)
- [26. The forward Dupire pricing calculation](#slide-26)
- [27. Calibrating through the PDE](#slide-27)
- [28. Fitted local variance and the Dupire-derived surface](#slide-28)
- [29. Event-weighted variance time](#slide-29)
- [30. Auto-calibrating isolated variance peaks](#slide-30)
- [31. Spot transport between calibrations](#slide-31)
- [32. Activating a prior where quote support is weak](#slide-32)
- [33. Persisting shape versus absolute strike values](#slide-33)
- [34. Temporal filtering of ATM handles](#slide-34)
- [35. Observation covariance and active filtering](#slide-35)
- [36. Series replay and independent calibration lanes](#slide-36)
- [37. Graph state: changes from transported priors](#slide-37)
- [38. Graph operators and their assumptions](#slide-38)
- [39. A precision-message relation](#slide-39)
- [40. Calendar and cross-asset relation controls](#slide-40)
- [41. The joint posterior and shared information](#slide-41)
- [42. Layered propagation and residual memory](#slide-42)
- [43. Reconstructing and displaying an inferred smile](#slide-43)
- [44. Validation against a transported baseline](#slide-44)
- [45. Choosing the next observation](#slide-45)
- [46. Where calibration time is spent](#slide-46)
- [47. Reading fit quality and publication state](#slide-47)
- [48. A complete worked sequence](#slide-48)
- [49. One calculation, read in dependency order](#slide-49)

<a id="slide-01"></a>

## 01. Models, calibration and inference

*Vol-Fitter · internal technical presentation*

The construction of a volatility surface from option quotes, and its evolution between observations.

The subject is the complete calculation: which market observations enter, what mathematical object is fitted, and what additional assumptions are used when a quote is missing or the market moves. The presentation follows the dependencies in that calculation rather than the order of the application menus.

A single option chain contains several different problems. Put–call pairs give information about the forward. Exercise style determines whether a price can go straight into a European inversion. A smile fit distributes its available flexibility across the selected quotes. A surface adds relations across maturities. Between calibrations, a spot rule and stored information determine how the displayed mark evolves.

Use the same distinction throughout: observed quotes, fitted quantities, and inferred quantities. Equations describe the mechanisms. Illustrative examples make their units visible. App screenshots are archived captures from 24 September 2026; timings and empirical scores are attached to their recorded experiment rather than presented as general performance constants.

**Sources.** [README.md](../../README.md); [ROADMAP.md](../../ROADMAP.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-02"></a>

## 02. Objects and calculation order

*1 · Market inputs*

A node is one underlying and one expiry. A surface couples the nodes belonging to an underlying.

| Stage | Input | Output |
| --- | --- | --- |
| Prepare | Quotes, exercise style, spot, carry | European prices, F, D and total variance |
| Fit | Prepared quotes + objective + model | A smile, or a local-variance surface |
| Constrain | Adjacent expiries and tail policy | Calendar diagnostics and a repaired surface |
| Update | Spot move and saved state | Transported fit, prior or filtered estimate |
| Infer | Observed handle changes and relations | Dark-node handles, smile and uncertainty |

Normalize the call price by the discounted forward, DF. The normalized terminal underlying has mean one under the model's deterministic-carry convention, which is the object used for the smile-law and calendar arguments. Normalized strike x and log-moneyness k are different coordinates; local volatility uses x, while the parametric smile is usually displayed against k.

The distinction between t and τ matters. A quoted price determines total variance w through Black inversion. Choosing a variance clock changes σ = sqrt(w/τ), while the rate discount and exercise calculation continue to use calendar time. When comparing two reported volatilities, first establish that their clocks and forward conventions agree.

ATM handles are the level σ(0), skew ∂σ/∂k at zero, and curvature ∂²σ/∂k² at zero. They summarize local shape and give the temporal filter and graph a common state. They do not specify an entire smile: reconstruction still needs a baseline shape and a model family.

The calendar interpretation assumes compatible normalization and carry across expiries. With actual cash dividends, the preprocessing convention is part of that interpretation. Comparing raw option prices at an unchanged cash strike also requires accounting for the different forwards and discount factors.

**Notation and units.** $x = K/F$; $k = \log(K/F)$; $c = C/(DF)$; $w = \sigma^2\tau$. Calendar time $t$ drives carry and exercise. The variance clock $\tau$ defines the volatility reading. One vol bp is 0.0001 of absolute volatility.

**In the app.** Open one node on the Parametric lens and read the Fit diagnostics card: the three handles, the RMS on the smile and on the surface.

**Sources.** [00_system_overview.md](../../Docs/handoff/notes/00_system_overview.md); [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [10_calendar_unnamed_martingale.md](../../Docs/handoff/notes/10_calendar_unnamed_martingale.md).

<a id="slide-03"></a>

## 03. Universe, observations and fit state

*1 · Market inputs*

The universe selection determines which smiles are observed and which are inferred.

Explain the node before showing the controls: it is a smile for one underlying and expiry, not a single option. The universe includes both the observations available to the fitter and the locations at which the graph is asked to produce marks. A dark designation withholds that node's current calibration observation from the graph.

An existing saved prior may still contain historical information about a dark node. Dark therefore means no current observation, not that the system has never seen the node. This distinction is essential when designing a held-out experiment. A same-session fit saved just before darkening is useful for demonstrating the interface, but it is not an independent forecast test.

Fetching quotes and fitting a model are distinct state transitions. With auto-calibration disabled, new data marks the fitted snapshot stale and waits for the user to calibrate. Auto-calibration schedules that same operation. A spot update uses the selected transport rule; it does not solve again for the stored parameters.

The calibration scopes are parametric, local volatility, or both. LQD provides the backbone state; SVI and MCS can be displayed as comparator fits on the same prepared observations. Local volatility is fitted jointly across an underlying's expiry ladder.

**Visual.** 24 September capture: six underlyings, 47 selected expiries. Filled and outlined expiry controls identify lit and dark nodes.

**In the app.** Open Manage universe, identify one lit and one dark expiry, then show the Calibrate scope menu and the stale indicator.

**Sources.** [ROADMAP.md](../../ROADMAP.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [README.md](../../Docs/deck/demo_2026-09-24/README.md).

<a id="slide-04"></a>

## 04. Snapshots, streaming and subscription coverage

*1 · Market inputs*

A displayed chain can combine continuously updated contracts with older observations.

The stream updates individual contracts, so recency can differ across a displayed chain. The local book has a timestamp per quote. The subscription plan prioritizes contracts near the money and those needed by the focused node. The remaining capacity is shared across tickers.

In the recorded Massive configuration, the plan targets 950 contracts on a connection whose tested capacity was approximately 1,000. Contracts outside that allocation are filled from a REST snapshot refreshed about once a minute. Acknowledgement, receipt of an actual quote, and feed delay are separate facts; the health view reports them separately.

The recorded Bloomberg setup uses a configured 3,000-subscription budget. When the plan exceeds it, a reserved set of slots cycles through overflow buckets. A bucket remains subscribed until its contracts paint or its timeout expires, then the next bucket begins. Each paint retains its own timestamp and underlying spot. These are application settings and September observations, not universal vendor entitlements.

The next step is to reconcile this asynchronous collection with the current spot. Refresh frequency alone does not perform that reconciliation. Historical or file-based sources also need the correct as-of context so that prices, carry and remaining maturity refer to the same instant.

**Visual.** 24 September capture: 420 acknowledged contracts against a configured 950-contract plan. The source is on a delayed cluster.

**Sources.** [massive_streaming.md](../../Docs/massive_streaming.md); [bloomberg_setup.md](../../Docs/bloomberg_setup.md); [ROADMAP.md](../../ROADMAP.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-05"></a>

## 05. Synchronising quotes to the current spot

*1 · Market inputs*

An old option price should first be inverted using the forward associated with its own timestamp.

$$
\Delta\sigma_{\mathrm{naive}}\simeq-\frac{\Delta_{F}\,\Delta F}{\mathrm{Vega}}
$$

$$
s_{\mathrm{age}}=a\sqrt{\mathrm{age}_{\mathrm{min}}}\,\frac{\sigma_{\mathrm{ATM}}}{0.15}
$$

Hold an old option price fixed and invert it with a forward that has moved. The first-order pricing identity is zero ≈ delta_F times ΔF plus vega times Δσ. This gives the negative sign in the displayed spurious IV change. On a short-dated option, small vega can make a modest forward mismatch look like a large volatility change.

The preparation step instead associates each quote with the forward implied by its own spot. It performs de-Americanisation and inversion in that frame. It then uses the selected dynamics and the last committed fit to express the observation at the current spot. Under sticky strike the fixed-strike variance correction is zero, although the strike's moneyness label still changes.

The uncertainty allowance scales with square-root age and with the prevailing ATM volatility. In band modes it widens the tolerated interval; for a mid target it reduces the observation weight. This is a modelling rule for stale-quote uncertainty, separate from the deterministic transport. With no reference smile, the code records that absence and uses no reference-based variance correction.

The 24 September status note records remaining differences in how LV and comparison preparation paths consume age weights. Describe the implemented quote-synchronisation mechanism without implying that every downstream diagnostic has identical age treatment.

**Illustrative calculation.** At 15% ATM volatility and four minutes of age, $a = 3.6$ vol bp per $\sqrt{\text{minute}}$ gives a 7.2 vol bp age allowance.

**In the app.** Options ▸ Calibration: the Quote synchronisation switch and the age uncertainty in bp per √minute.

**Sources.** [ROADMAP.md](../../ROADMAP.md); [quote_sync.py](../../backend/volfit/api/quote_sync.py).

<a id="slide-06"></a>

## 06. Forward and discount from put–call parity

*1 · Market inputs*

Call–put pairs at several strikes identify the intercept and slope of a line.

$$
C(K)-P(K)=D(F-K)=a+bK
$$

$$
D=-b,\qquad F=\frac{a}{D}
$$

European put–call parity gives a two-parameter regression. The intercept a equals DF and the slope b equals minus D. The forward can also be read as the strike at which the fitted call–put difference crosses zero. This is useful because it shows why the regression uses a collection of pairs rather than a single ATM pair.

The implementation starts from two-sided, uncrossed pairs, requires at least three, and applies a bounded number of MAD trimming rounds. The implied discount rate is constrained to a configured range; if it reaches that constraint, the forward is recomputed from the price level using the relevant weights. The number of pairs, residual size and dropped count provide context for the estimate.

A broad strike range helps identify the slope, but observations must belong to a compatible settlement and exercise convention. Combining different roots or settlement times simply because their calendar date matches can generate a misleading line.

For American options, the difference of exercise premia is strike dependent, so raw parity can tilt both F and D. The refinement de-Americanises selected nearby pairs and reduces the mismatch in call and put implied volatility near the forward. The next slide treats the link to dividends and borrow.

**Illustrative calculation.** If $C - P = 101 - 0.98K$, then $D = 0.98$ and $F = 103.0612$. The zero crossing is the forward.

**Visual.** Reference-note figure: the fitted line exposes the two quantities being inferred. Residuals measure inconsistency among the selected pairs.

**In the app.** Forwards lens (Alt+2): the ladder's Parity, Theo and Active columns and the residual count per expiry; the Forward panel's Parity / Theo / Manual mode.

**Sources.** [06_forwards_dividends_inference.md](../../Docs/handoff/notes/06_forwards_dividends_inference.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-07"></a>

## 07. Dividends, borrow and the American fixed point

*1 · Market inputs*

A parity forward becomes a carry estimate only after choosing the dividend and rate inputs.

$$
F_{\mathrm{theo}}(b)=(S-\mathrm{PV}_{\mathrm{div}})e^{(r-q-b)t}
$$

$$
b_{n+1}=b_n+\frac{1}{t}\log\!\left(\frac{F_{\mathrm{theo}}(b_n)}{F_{\mathrm{parity}}(b_n)}\right)
$$

The theoretical forward discounts cash dividends separately and applies the continuous rate, yield and borrow over calendar time. If both q and a cash schedule are used, they represent different pieces of the supplied dividend model; do not count the same payment twice.

The sign of the fixed-point update is informative. If the theoretical forward is above the parity forward, the logarithm is positive and borrow increases, which lowers the next theoretical forward. However, the parity estimate is not fixed while this happens: the exercise correction is recomputed under the new carry. That dependence is why a single logarithmic borrow read can be biased.

At a fixed theoretical forward, a small relative error δF/F produces a borrow error approximately −δF/(Ft). The division by t explains why a short expiry can have a large annualized borrow uncertainty even when its forward appears tightly estimated in cash units. The reported ±σ should be read with that sensitivity in mind.

Dividends are inputs in this workflow, not an independently identified output of the parity regression. A mismatch between parity and theory can reflect borrow, a dividend schedule, rates, timing or quote quality. The captured XOM table illustrates the calculation and its dependence on those inputs; its numbers are not a current borrow recommendation.

**Visual.** 24 September XOM capture. The Joint and $\pm\sigma$ columns show the carry estimate and its reported uncertainty; the example uses the saved desk inputs.

**In the app.** Forwards lens: tick Joint carry — the Joint and ±σ columns appear; hover a cell for the iterations and the ATM-vol sensitivity per 100 bp of borrow.

**Sources.** [06_forwards_dividends_inference.md](../../Docs/handoff/notes/06_forwards_dividends_inference.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-08"></a>

## 08. Removing the early-exercise premium

*1 · Market inputs*

Estimate a European-equivalent volatility from the American mid, then remove the corresponding premium.

$$
A_{\mathrm{CRR}}(\sigma^*)=A^{\mathrm{mid}}
$$

$$
\widehat{\mathrm{EEP}}=\max\!\left(A^{\mathrm{mid}}-E_{\mathrm{Black}}(\sigma^*),0\right)
$$

The American price contains both a European option value and the value of the exercise opportunity. The latter is not directly quoted. The tree supplies a model for it: solve for the volatility whose American value equals the observed mid, then use that volatility in the European Black formula with the resolved carry.

Apply the same estimated premium to all three sides. This preserves the quoted dollar spread before subsequent static-bound screens and any wing repair. It does not preserve a constant spread in volatility units, since price-to-vol inversion is nonlinear.

For cash dividends, the recombining tree diffuses the spot net of the present value of remaining payments. At an exercise decision, the remaining dividend value is added back to form the actual spot used in the payoff. This is a tractable modelling approximation to the cash-dividend stopping problem.

The real-data image is useful for seeing why exercise style matters, but it includes deep ITM options. Those are not the options used by the production OTM calibration path. The preparation study recorded a median absolute correction of about 4.2 vol bp on the fitted population, with larger put-wing corrections. A quote on its intrinsic plateau may contain no resolvable volatility and needs the corresponding screen rather than an invented root.

**Visual.** Recorded SPY example: the largest displayed wedge is on deep ITM puts. The actual calibration population uses OTM quotes, where the correction is smaller.

**In the app.** Forward panel: switch the Dividend model to continuous with q = 0 and Apply — call and put markers split at the money; restore the schedule and Calibrate.

**Sources.** [05_deamericanization_stopping.md](../../Docs/handoff/notes/05_deamericanization_stopping.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [deam_real_numbers.json](../../Docs/notes/figures/deam_real_numbers.json).

<a id="slide-09"></a>

## 09. Exercise correction: numerical cost and accuracy

*1 · Market inputs*

Root-solve precision, tree discretisation and quote uncertainty are different error sources.

| Component | Implementation / recorded check | Interpretation |
| --- | --- | --- |
| American tree | 192 CRR steps on the batch path | Fixed depth; $O(N^2)$ rollback per price |
| Volatility root | 24 bracketed bisections | About 0.002 vol bp bracket width at $\sigma \le 4$ |
| Discretisation check | Within ±5.4 vol bp in the recorded round trip | Against American prices from a 2,001-step tree |
| Batch execution | Compiled kernel across quotes | About 0.07–0.10 ms per quote in the recorded runs |
| Prepared-quote cache | Keyed on market data, carry and time inputs | A change to fit settings can reuse preparation |

Twenty-four bisections make the numerical uncertainty of the scalar root much smaller than the tree error. Increasing bisections therefore does little once the root has converged for the chosen tree. Increasing tree depth changes the discretised stopping problem and can still move the European-equivalent volatility.

At N steps, a CRR rollback visits order N squared nodes. Each iteration uses multiplication, addition, discounting and a maximum with the exercise value. The compiled implementation hoists repeated powers and evaluates a batch of quotes; this reduces interpreter overhead without changing the model.

The reference comparison measures discretisation error within the chosen exercise model. Both calculations use the same escrowed dividends, resolved forward and exercise conventions. The recorded round trip used a known volatility to generate a high-resolution American price, then inverted it through the production batch path.

The cache is important when discussing end-to-end time. Forward, dividend, timestamp or market-data changes invalidate preparation, while changes confined to the fitting objective can reuse the prepared quotes. Time a cold market refresh separately from a repeated model fit so that cached work is visible in the measurement.

**Recorded accuracy experiment · 23 September 2026.** $S = 100$, $r = 4.5\%$, $q = 1.2\%$, $t = 0.5$ year, $\sigma = 25\%$. The reference and batch paths use different tree depths; the comparison measures numerical resolution under that model.

**Sources.** [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [deamericanization_calibration_speed_note.md](../../Docs/deamericanization_calibration_speed_note.md).

<a id="slide-10"></a>

## 10. The units of a calibration residual

*2 · Objective and smile models*

The objective measures how much the fitted model misses the selected market observations.

$$
r_i(\theta)=\frac{c_\theta(k_i)-B(k_i,w_i)}{\partial_\sigma B(k_i,w_i)+\varepsilon}
$$

$$
r_i\simeq\sigma_\theta(k_i)-\sigma_i
$$

Start with a Taylor expansion of Black price around the quoted volatility. To first order, the price difference is vega times the volatility difference. Dividing by vega puts residuals from different strikes on comparable volatility scales. Without the division, a price-squared objective gives most influence to high-vega options even if their volatility errors are no larger.

The next term is one half of vomma times the square of the volatility difference. Thus the normalised price residual is not an exact IV error far from the optimum. This matters for cold starts and deep wings. A final IV error obtained by inversion and a residual measured inside the optimizer need not be identical.

The floor is a deliberate numerical choice. As maturity or time value approaches zero, a tiny price movement can correspond to a large IV movement. The floor prevents the solver from treating that unstable conversion as an arbitrarily precise volatility observation.

Beyond residual units, the fit needs two further choices: which values inside a quote band are acceptable, and how much weight each region of strike carries. Model regularisation, calendar constraints and prior rows are additional blocks in the same residual stack; they should not be confused with observed quote error.

**Illustrative calculation.** A $0.04 price error with vega of $20 per unit of decimal volatility gives 0.002 = 20 vol bp. The approximation is local; a large miss also contains a vomma contribution.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md).

<a id="slide-11"></a>

## 11. Mid, bid–ask and haircut targets

*2 · Objective and smile models*

A band target allows a range of fitted values, with a weak mid anchor selecting among them.

$$
L_i=(m_i-u_i)_+^2+(l_i-m_i)_+^2+\theta_{\mathrm{mid}}(m_i-\bar m_i)^2
$$

Use m, l and u in a common residual coordinate. For a price model, the volatility sides are mapped into price and the rows are vega normalised. The positive-part terms measure violation of the upper and lower bounds. They are zero inside the interval.

The weak mid anchor has a different job: the bands alone may leave many parameter vectors with zero quote loss. A small preference for mid, together with intrinsic regularisation and any active prior, selects a solution in that set. With a 0.05 anchor, entering a band reduces the data contribution; it does not make the entire objective flat.

For the illustrative quote, a 20.4% model lies inside both the original and trimmed interval. It pays only the weak anchor. A 20.8% model lies inside the original interval but is 0.3 vol point above the trimmed upper side, so the haircut objective adds an upper-side violation.

Reported band RMS measures distance to the chosen target interval. A near-zero band RMS does not mean that every mid is reproduced. Keep the target mode fixed when comparing errors across models, and state whether a displayed number includes only quote error or also penalty terms.

**Visual.** Illustrative 19% / 21% quote. A 0.5 vol-point haircut leaves [19.5%, 20.5%]. The band includes a 0.05 mid-anchor weight.

**In the app.** Show the target shading on the Smile, then the Mid / Bid–Ask / Haircut controls in Calibration options.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-12"></a>

## 12. Quote weights and strike spacing

*2 · Objective and smile models*

A sum over listed strikes approximates a chosen distribution of weight along log-moneyness.

$$
\omega_i\propto f(k_i)\min\!\left(\frac{s_i}{\bar s},10\right),\qquad \frac{1}{n}\sum_i\omega_i=1
$$

Consider a continuum objective integrating squared error against f(k) dk. On an irregular listing, the corresponding sum uses f(k_i) times the width of the cell around quote i. Without the cell width, an increasingly dense listing can change the objective even if the underlying curve has not changed.

The practical correction uses half the gap to each neighbour, with endpoint handling and a cap on an isolated quote's spacing multiplier. Mean normalisation keeps the total data weight comparable when switching schemes. The cap deliberately changes the ideal continuum quadrature in extremely sparse regions to limit the influence of one quote.

A target shaped by vega or time value already favours certain regions of moneyness. The spacing correction then accounts for how those regions were sampled. These are two separate operations: a flat target does not imply equal weights on an irregular grid, while equal weights do not imply uniform mass along log-strike.

The weight strip and Quality weight breakdown make this distribution inspectable. A switch of weighting scheme may change the fitted curve and the aggregate RMS because it changes which errors are emphasised. Compare the per-strike differences as well as the single aggregate score.

**Illustrative calculation.** Three quotes spanning 0.03 in $k$ each represent roughly 0.01. A single quote representing 0.03 receives about three times an individual clustered quote's raw spacing weight, before caps and normalisation.

**Visual.** Reference-note example of the spacing correction. A weighting scheme controls the allocation of fit error; the quote band controls tolerance.

**In the app.** Smile view: switch the Weights layer on in the layer rail — the strip under the chart shows the target beside the weight the fit sums; hover a bar for k · target · ×spacing · weight.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-13"></a>

## 13. What each model parameterises

*2 · Objective and smile models*

The four families place flexibility in different mathematical objects.

| Model | Unknown object | Pricing / inversion | Main constraints or controls |
| --- | --- | --- | --- |
| LQD | Log quantile density of log-return | Integrate a probability law | Moment integrability; numerical pricing checks |
| SVI–JW | Total implied variance w(k) | Black formula | Structural wing bounds; density checks |
| MCS | Variance profile with local corrections | Black formula | Wing budget; positivity and density checks |
| Local volatility | Local variance $\nu(\tau, x)$ | Forward Dupire PDE | Positive vertices; roughness; lattice checks |

These models do not simply differ by parameter count. LQD represents a distribution through its quantile derivative. SVI and MCS describe a total-variance or variance-rate curve, whose associated density must be inspected. Local volatility describes an instantaneous diffusion coefficient whose accumulated action generates prices across maturities.

All are calibrated against the same prepared market observations and share the vocabulary of targets and weights. Their intrinsic regularisers differ because their unknowns differ. An LQD spectral penalty, an MCS correction penalty and an LV roughness penalty are not interchangeable merely because each is multiplied by a coefficient.

In the application, the LQD backbone also provides handles for prior, filter and graph calculations, including when a comparator is displayed. The local-volatility lens owns a surface fit across expiries. Those distinctions matter when attributing computation time.

A comparison should expose price or IV reproduction, density and tails, then sensitivity to thinning or held-out strikes. An in-sample RMS alone cannot determine how the models behave between quotes or beyond the observed range. The following slides examine the construction of each family.

**Comparison convention.** Use the same prepared quotes, forward, variance clock, target mode and weighting. Record the tail and regularisation choices alongside the fit error.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [02_svi_jw_rewrite.md](../../Docs/handoff/notes/02_svi_jw_rewrite.md); [03_multicore_mcs_corrections.md](../../Docs/handoff/notes/03_multicore_mcs_corrections.md); [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md).

<a id="slide-14"></a>

## 14. LQD: constructing a probability law

*2 · Objective and smile models*

Let $Q(u)$ be the quantile of $X = \log(S_T/F_T)$, with $u$ between zero and one.

$$
Q'(u)=q(u)=\frac{e^{g(u)}}{u(1-u)}
$$

$$
g(u)=(1-u)L+uR+\sum_{n=2}^{N}a_nP_n(1-2u)
$$

$$
f_X(Q(u))=\frac{1}{q(u)}>0
$$

The quantile derivative is sometimes called the quantile density, but it is not the density of log-return. The two are reciprocal at matching ranks: f_X(Q(u)) = 1/Q′(u). A positive derivative makes the quantile increasing, and a uniform rank U therefore defines a valid random variable X = Q(U).

The singular factor 1/[u(1−u)] gives logarithmic quantile growth at the endpoints. The smooth function g changes the speeds of those tails and shapes the central distribution. Its Legendre expansion supplies an adjustable order. In the displayed raw coordinates, the higher-order modes also affect the endpoints; L and R alone are not the endpoint scales.

Write an unshifted quantile Q̄, calculate M = integral exp(Q̄(u)) du, and set μ = −log M. This makes exp(X) have mean one. In the exponential-tail case the right scale A_R = exp(g(1)) must be below one for M to exist. A logistic endpoint chart enforces that condition during fitting.

Calls generated by a positive mean-one law are decreasing and convex in strike. That is the continuous model statement. Numerical quadrature, interpolation and extrapolation still need finite-tolerance checks. Generalised tails later extend the endpoint family; the formulas on this slide describe α = 0.

**Visual.** Reference-note figure: the logarithmic endpoint terms set the tail structure; the smooth Legendre component controls the body.

**In the app.** Parametric ▸ Density ▸ Log Q-density: the two logarithmic walls at the ends and the Legendre body between them; Density and CDF are one click away.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md).

<a id="slide-15"></a>

## 15. LQD: quantiles to option prices

*2 · Objective and smile models*

A cumulative asset-share integral prices every strike after one construction of the slice.

$$
z=\log\frac{u}{1-u},\qquad \frac{dQ}{dz}=e^{g(u(z))}
$$

$$
G(u)=\int_u^1 e^{Q(v)}\,dv
$$

$$
c(k)=G(u_k)-e^k(1-u_k),\qquad Q(u_k)=k
$$

The price identity is simply the payoff integral over ranks above the exercise threshold. The first term is the normalized underlying value in those outcomes. The second is the strike paid in the fraction 1−u_k of outcomes in which the call exercises.

Switching to log odds gives du/dz = u(1−u), which cancels the singular factor in Q′. The resulting integrand exp(g) is smooth on the working z grid. The implementation constructs the quantile, its normalization and the cumulative asset share together, then reuses them for all strikes.

Between nodes, cubic Hermite interpolation uses the available nodal values and derivatives. A bracketed local root identifies z_k. Far outside the grid, the selected tail continuation supplies the price rather than a flat clipping rule. Stable evaluation of u and 1−u on their respective sides avoids rounding a small tail probability to zero.

The constant-g example is a useful analytic check. Integrating (u/(1−u))^a over the unit interval yields Γ(1+a)Γ(1−a) = πa/sin(πa). It exposes both the normalization and the a < 1 right-moment condition. It is an illustrative law, not a market fit.

**Illustrative calculation.** For $g = \log a$, $Q(u) = \mu + a\log[u/(1-u)]$. If $0 < a < 1$, $\mu = -\log[\pi a/\sin(\pi a)]$. At $a = 0.10$, $\mu \approx -0.01650$ and the mean of $e^{X}$ is one.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md).

<a id="slide-16"></a>

## 16. LQD calibration and analytic sensitivities

*2 · Objective and smile models*

The strike-boundary term cancels when differentiating an option price.

$$
\frac{dc}{d\theta}=\frac{\partial G}{\partial\theta}\bigg|_{u_k}
$$

$$
\left[\frac{\partial G}{\partial u}(u_k)+e^k\right]\frac{du_k}{d\theta}=0
$$

| Work | Scaling / reuse |
| --- | --- |
| Slice and sensitivities | O(MP) for M grid nodes and P coefficients |
| Many strikes | Reuse the same cumulative arrays |
| Nearby calibrations | Warm starts reuse the previous parameter vector |

Differentiate c = G(u_k) − exp(k)(1−u_k) at fixed strike. Since G′(u_k) = −exp(Q(u_k)) = −exp(k), the two terms multiplying du_k/dθ cancel. This is the envelope mechanism behind the analytic sensitivity. It eliminates the need to numerically differentiate the strike root.

Each coefficient changes g through a known basis row. Differentiating exp(g) multiplies that row by exp(g), so the quantile and asset-share sensitivities are additional cumulative integrals on the same grid. The martingale shift and endpoint corrections are differentiated as part of the same calculation.

The displayed operation count describes construction of the slice and its Jacobian, not the entire optimization. Iteration count, linear algebra, active residual blocks and rejected steps still affect wall time. Coarser optimization quadrature reduces per-iteration cost; the final finer build provides the reporting object.

The order guard is a heuristic tied to quote count, with a minimum retained order. The ridge also changes the selected shape. Vary order and regularisation while scoring withheld strikes, density and the wing to assess how much flexibility the observed strip supports.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-17"></a>

## 17. ATM handles and delta-based operators

*2 · Objective and smile models*

Local derivatives and option packages describe different aspects of the fitted smile.

$$
h=(\sigma_0,s_0,\kappa_0)=(\sigma(0),\sigma'(0),\sigma''(0))
$$

$$
\mathrm{RR}_d=\sigma(k_{c,d})-\sigma(k_{p,d})
$$

$$
\mathrm{BF}_d=\frac{\sigma(k_{c,d})+\sigma(k_{p,d})}{2}-\sigma_0
$$

| Quantity | Meaning | Use |
| --- | --- | --- |
| ATM / skew / curvature | Level and local derivatives in k | Filter and graph state |
| RR25 / BF25; RR10 / BF10 | Differences across delta-selected strikes | Persistence operators |
| Wing and variance-swap operators | Deep-strike slope or integrated smile | Additional tail information |

The ATM handles are derivatives with respect to log-moneyness. Skew and curvature therefore have different units from the ATM volatility, even though all are derived from one smile. They are local summaries: a distant wing change can leave all three nearly unchanged.

The RR and BF operators use forward Black delta. At call delta d, the strike solves k = w(k)/2 − sqrt(w(k)) Φ⁻¹(d); the put leg at absolute delta d corresponds to call delta 1−d. The smile dependence requires a fixed-point or root calculation. This is not a premium-adjusted FX delta convention.

For persistence, the leg locations are found on the transported prior and then frozen when comparing prior and current model. Otherwise the residual would mix a change in volatility with a change in the strike being sampled. The quoted RR sign here is call minus put; the interface can reverse its display sign.

At frozen leg strikes, RR and BF are invariant to a common additive volatility level move. ATM and an absolute variance-swap level are not. These package operators are available as diagnostics and persistence carriers. The application does not expose them as a complete set of independently draggable straddle, collar and butterfly market-quote controls.

**Illustrative calculation.** ATM 20%, $25\Delta$ call 19%, $25\Delta$ put 23% gives $\mathrm{RR}_{25} = -4$ vol points and $\mathrm{BF}_{25} = +1$ vol point. At these fixed leg strikes, a common +2-point shift leaves $\mathrm{RR}$ and $\mathrm{BF}$ unchanged.

**In the app.** Options ▸ Prior: the Operators chips (ATM · RR25 · BF25 · RR10 · BF10 · WingL · WingR · VarSwap) and the Collar sign; the Fit diagnostics card reads the handles.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [operators.py](../../backend/volfit/calib/operators.py).

<a id="slide-18"></a>

## 18. SVI and Jump-Wings coordinates

*2 · Objective and smile models*

SVI fits a five-parameter total-variance curve; Jump-Wings expresses the same curve in more interpretable quantities.

$$
w(k)=a+b\left[\rho(k-m)+\sqrt{(k-m)^2+\xi^2}\right]
$$

The raw formula is a tilted hyperbola in total variance. Its limiting slopes are b(1−ρ) on the left and b(1+ρ) on the right. The shape is compact, so a small number of parameters jointly determines the body and both wings.

Jump-Wings is a coordinate change. With w₀ = w(0), v = w₀/τ is ATM variance rate; the normalised wing quantities are p = b(1−ρ)/sqrt(w₀) and c = b(1+ρ)/sqrt(w₀). The minimum variance rate is [a + bξ sqrt(1−ρ²)]/τ. The JW skew quantity is w′(0)/(2 sqrt(w₀)), so it should not be confused with σ′(0) without the appropriate clock factor.

The production structural chart uses an interior slope cap of 1.95. This constrains the far-wing slopes but is not by itself a proof that the density is nonnegative everywhere. The belly condition involves w, w′ and w″ and is checked separately.

SVI provides a compact comparator to the distribution-based construction. On a surface, calendar consistency is an additional relation between expiries. The eSSVI reference available in comparisons is a restricted surface construction.

**Visual.** Reference-note curve annotated in Jump-Wings quantities: ATM variance and skew, the two wing slopes, and the minimum variance.

**In the app.** Parametric ▸ Compare: click the SVI chip — the same quotes, one RMS column, Lee slopes and tails beside LQD; + reference adds eSSVI.

**Sources.** [02_svi_jw_rewrite.md](../../Docs/handoff/notes/02_svi_jw_rewrite.md); [02_svi_jw_moments.md](../../Docs/handoff/notes/02_svi_jw_moments.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-19"></a>

## 19. MCS: local shape corrections

*2 · Objective and smile models*

A smooth base is augmented with local corrections whose contribution vanishes in the far wings.

$$
\Phi_\kappa(u)=\frac{4}{\kappa^2}\log\cosh\!\left(\frac{\kappa u}{2}\right)
$$

$$
H(u)=\frac{\Phi_\kappa(u-h)-2\Phi_\kappa(u)+\Phi_\kappa(u+h)}{2\Phi_\kappa(h)}
$$

The log-cosh function becomes linear at large positive or negative argument. Taking a symmetric second difference of a linear function gives zero, so the hat correction decays in either far wing. This separates local body adjustments from the base's asymptotic slopes.

The full variance-rate profile adds a sum of these hats to a base containing level, a linear term and log-cosh curvature. The app labels the model MCS; the technical notes also call it Multi-Core SIV or Multi-Core Sigmoid. Define the naming once and then use MCS.

A correction can reproduce a localized shoulder or an additional bend that a single global SVI curve may not represent closely. Its effect on the risk-neutral density can be substantial because density depends on second derivatives. The sign and magnitude of the correction therefore require positivity and butterfly controls.

The core count increases capacity; the correction ridge discourages fitting narrow quote noise. Compare the fit at several core counts using the same target and weights, then inspect the density and held-out strikes. The relevant comparison includes the structural constraints and regularisation settings of each fitted model.

**Visual.** Reference-note decomposition. The hats alter the body while tending to zero as the base becomes linear in either tail.

**In the app.** Parametric ▸ Compare: the MCS chip; Options ▸ Parametric: MCS cores R and the wing penalty.

**Sources.** [03_multicore_mcs_corrections.md](../../Docs/handoff/notes/03_multicore_mcs_corrections.md).

<a id="slide-20"></a>

## 20. Generalised LQD tail exponents

*3 · Tails and maturity consistency*

A fixed exponent on each side changes the asymptotic return-tail class.

$$
\frac{dQ}{dz}=e^{g(u)}\ell_-^{-\alpha_-}\ell_+^{-\alpha_+},\qquad 0\leq\alpha_\pm\leq\frac12
$$

$$
\ell_-=1-\log u,\qquad \ell_+=1-\log(1-u)
$$

| Exponent on one side | Log-return tail | Far-wing total variance |
| --- | --- | --- |
| $\alpha = 0$ | Exponential | Asymptotically linear in $\|k\|$ |
| $0 < \alpha < 1/2$ | Faster than exponential | Sublinear growth; limiting Lee slope zero |
| $\alpha = 1/2$ | Gaussian rate | Tends to a constant set by the tail scale |

The endpoint gauges are smooth versions of the distance along the two ends of the log-odds axis. At α = 0 they disappear and recover the original LQD construction. At a positive exponent, the quantile grows more slowly than linearly in |z|, producing a faster-decaying log-return tail.

For a fixed positive exponent, all exponential moments in the corresponding tail direction exist. This changes the limiting wing behaviour even when the observed body of the distribution changes very little. The distinction is mathematical but may be weakly identified by the available strike strip.

The implementation consequently treats α as a fixed tail-policy input, not an optimization variable. Its scope is one pair per underlying across the expiry stack. At common exponents, the far-expiry tail scales must have a compatible order for full-line calendar consistency; the acceptance policy and numerical certificate examine this separately from the in-strip fit.

At α = 1/2, Gaussian rate describes the asymptotic decay, not a statement that the entire distribution is normal. The body can still be skewed or multimodal. Similarly, α > 0 gives a zero limiting Lee slope while allowing a substantial slope at finite strikes.

**Illustrative calculation.** A tiny positive $\alpha$ can resemble $\alpha = 0$ over the quoted range while changing the limiting moment domain. Compare tail-policy scenarios at common quotes rather than estimating $\alpha$ separately at every expiry.

**In the app.** Options ▸ Parametric ▸ Tail α− · α+ with the presets Exp · Int · Gauss; the Quality node card reads Lee L/R and Tail order.

**Sources.** [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-21"></a>

## 21. Wing slopes and finite moments

*3 · Tails and maturity consistency*

Lee's relation connects asymptotic total-variance slopes to the moments of the normalized underlying.

$$
\psi(p)=2-4\left(\sqrt{p^2+p}-p\right)
$$

$$
\beta_R=\psi(p^*),\quad p^*=\sup\{p\geq0:\mathbb{E}[Y^{1+p}]<\infty\}
$$

Use Y = S_T/F_T in this formula. The right critical moment is an additional moment beyond the first, since E[Y] is already fixed at one. The left critical moment is a negative moment. These definitions explain the minus one on the right LQD formula and its absence on the left.

The more moments that exist, the flatter the limiting total-variance wing. If all positive moments exist, the right Lee slope is zero. This is compatible with sublinear growth and does not imply a flat finite-strike smile.

The production SVI and MCS controls place their configured limiting slopes below 1.95. The buffer avoids operating exactly at the edge of the selected structural chart. The general Lee bound includes the limiting value two; admissibility at that boundary depends on the complete asymptotic expansion.

There are two separate questions in wing inspection: the theoretical class chosen for remote strikes, and numerical price or density behaviour over the actual exported range. A finite-grid check can diagnose the latter without identifying the former. For the exponential LQD right tail, proximity of A_R to one also makes the martingale normalization numerically sensitive.

**Visual.** Reference-note curve: larger finite-moment orders correspond to smaller limiting wing slopes. The admissible bound is between zero and two.

**Sources.** [09_wings_last_quote.md](../../Docs/handoff/notes/09_wings_last_quote.md); [02_svi_jw_moments.md](../../Docs/handoff/notes/02_svi_jw_moments.md); [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md).

<a id="slide-22"></a>

## 22. Variance swaps as an integrated constraint

*3 · Tails and maturity consistency*

A variance-swap quote adds information about the weighted option strip, including extrapolated wings.

$$
w_{\mathrm{VS}}=2\left[\int_0^1\frac{p(x)}{x^2}\,dx+\int_1^\infty\frac{c(x)}{x^2}\,dx\right]
$$

$$
\sigma_{\mathrm{VS}}=\sqrt{w_{\mathrm{VS}}/\tau}
$$

$$
r_{\mathrm{VS}}=\sqrt{\lambda_{\mathrm{VS}}}(\sigma_{\mathrm{VS}}^{\mathrm{model}}-\sigma_{\mathrm{VS}}^{\mathrm{quote}})
$$

Here c and p are undiscounted normalized call and put prices. The split at normalized strike one selects OTM puts below the forward and OTM calls above it. The integral gives total log-contract variance w_VS and is independent of the choice of annualisation clock. In log-strike coordinates it carries an exp(−k) weight.

The total log-contract value equals −2E[log Y] under the normalization and integrability assumptions. Its equality with expected integrated quadratic variation uses continuous paths; jumps and discrete monitoring require separate adjustments. A calendar-annualised variance strike is w_VS/t. The current application builds the target and displays the volatility level using its working variance clock τ, hence σ_VS = sqrt(w_VS/τ). A quote expressed on calendar time must be converted consistently when τ differs from t.

LQD can evaluate the expectation in its native quantile coordinates. A generic smile can use a static replication grid. The local-volatility implementation also has a source-PDE route. Finite integration domains and grid convergence matter whenever the tail contribution is material.

A variance-swap quote introduces a scalar constraint into a much larger shape problem. The percentage weight scales it relative to the sum of vanilla quote weights. A setting called Hard pin uses a very large finite penalty, so it remains a numerical penalty rather than an exact equality constraint. Read the remaining quote-to-model difference and the contribution attributed to the unquoted wings.

**Visual.** 24 September QQQ capture: quoted volatility 25.04%, model 25.03%, with a saved 15% penalty setting. These are recorded fit values.

**In the app.** Parametric aside ▸ Variance swap card: seed a quote at the model level, move it, watch the wing; Hard pin makes it a stiff row.

**Sources.** [08_varswap_representations.md](../../Docs/handoff/notes/08_varswap_representations.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [service.py](../../backend/volfit/api/service.py); [varswap.py](../../backend/volfit/calib/varswap.py).

<a id="slide-23"></a>

## 23. Calendar consistency across expiries

*3 · Tails and maturity consistency*

Individually valid slices also need a compatible order across maturity.

$$
c_{T_2}(k)\geq c_{T_1}(k)\quad\Longleftrightarrow\quad w_{T_2}(k)\geq w_{T_1}(k)
$$

$$
G_{T_2}(u)\geq G_{T_1}(u),\qquad G_T(u)=\int_u^1 e^{Q_T(v)}\,dv
$$

At fixed normalized strike, the Black call is increasing in total variance, so call-price order and total-variance order are equivalent. With equal means, ordering every call payoff is the same as convex order of the terminal normalized underlying.

Integrated quantiles provide another equivalent representation. The upper-share function G is compared at the same rank u, whereas call prices are compared at the same strike. These are different comparisons that encode the same distributional order. Comparing the pointwise densities would not provide an equivalent test.

The normalization is essential. This is the mean-one martingale surface condition used by the engine, under compatible deterministic carry conventions. Raw prices at a fixed cash strike with changing forwards and cash-dividend effects require their own interpretation.

Two slices may each be generated by positive densities and still cross in total variance. Calendar coupling is therefore additional to the single-slice butterfly property. Conversely, a decreasing annualised ATM term structure is not by itself a violation; the numerical example demonstrates why the clock multiplier must be retained.

**Illustrative calculation.** Three months at 24% gives $w = 0.0144$. Six months at 20% gives $w = 0.0200$. The annualised volatility falls, while total variance rises.

**Visual.** Reference-note example of crossing expiry curves. A local negative difference in total variance identifies a calendar-order violation.

**In the app.** Parametric ▸ Stacked IV: total variance per expiry, non-crossing; Quality's Cal viol column and the calendar certificate per node.

**Sources.** [10_calendar_unnamed_martingale.md](../../Docs/handoff/notes/10_calendar_unnamed_martingale.md); [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md).

<a id="slide-24"></a>

## 24. Calendar repair and numerical certification

*3 · Tails and maturity consistency*

Fitting constraints and acceptance checks operate at different resolutions.

| Step | Calculation | Purpose |
| --- | --- | --- |
| Independent fits | Fit each observed expiry with its own data terms | Obtain a starting surface |
| Violation screen | Compare adjacent expiries on relevant support | Identify components needing joint repair |
| Symmetric repair | Optimize coupled expiries with calendar penalties | Allow both sides to adjust within their fit costs |
| Stored-ledger certificate | Check gap extrema, boundaries and tail continuation | Inspect between sampled grid points |
| Policy decision | Apply quote-region and full-line acceptance settings | State which violations block an exported surface |

A nearest-to-farthest sequential floor forces the later expiry to accommodate the earlier one. The symmetric route first fits independently, detects the connected components with identified violations, then repairs those components jointly. The data objectives determine how costly it is for each expiry to move.

A large penalty is still a soft optimization mechanism. Its numerical outcome needs a separate acceptance check. The implementation evaluates the minimum of the stored integrated-quantile gap between interpolation nodes by finding its stationary points. This is more informative than checking a sparse set of samples.

For the interior cubic Hermite representation, the derivative is quadratic, making the candidate set finite. The tails add continuation candidates and asymptotic-order clauses. The certificate describes the stored numerical representation at stated tolerances.

The implementation distinguishes fitted-range repair, tail continuation and publication policy. Full-line tail order can be advisory or gating according to settings. A hard-constraint exchange solver remains deferred in the roadmap.

**Illustrative calculation.** For a cubic gap on one interpolation interval, minima occur at its endpoints or roots of its quadratic derivative. Checking only the stored nodes can miss an interior dip.

**Sources.** [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [calendar_certificate.py](../../backend/volfit/calib/calendar_certificate.py).

<a id="slide-25"></a>

## 25. A piecewise-affine local-variance surface

*4 · Local-volatility calibration*

The local-volatility fit chooses instantaneous variances whose forward prices reproduce the option quotes.

$$
\nu_\theta(\tau,x)=\sum_{\ell}\theta_\ell\phi_\ell(\tau,x),\qquad x=K/F
$$

The unknowns are local variances, not implied volatilities. A single vertex affects option prices over a region of maturity and strike through the PDE, so it cannot be read as the implied volatility of an option at that coordinate.

The basis functions are piecewise affine on the triangulation. Inside a triangle only its three vertex weights are active. Positive bounds on the vertices therefore give positivity on the hull directly. A cash or implied-volatility smile is then obtained by pricing, not by interpolating those vertex values as if they were implied vols.

The positive-interpolation argument applies inside the triangulated domain. Outside it, the continuation rule is a separate modelling choice, with its own numerical checks. The implementation uses a flat right continuation and a left continuation related to the first cell's slope.

A dense vertex grid provides flexibility but increases the inverse problem's weakly identified directions. Option prices integrate local variance over paths and time; different sheets can reproduce nearly identical vanilla prices. Grid choice and roughness controls therefore affect the fitted latent surface even when quoted IV errors appear similar.

**Visual.** 24 September capture of the fitted local-variance mesh. The visible stale label refers to the saved snapshot; the mesh illustrates the parameterized object.

**In the app.** Local Vol lens (Alt+4) ▸ LV surface: drag to rotate the mesh; the toolbar badges arb-free and rms · conv · max bp.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [04_local_volatility_forward.md](../../Docs/handoff/notes/04_local_volatility_forward.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-26"></a>

## 26. The forward Dupire pricing calculation

*4 · Local-volatility calibration*

Given local variance, march normalized call prices from the intrinsic payoff.

$$
\partial_\tau c=\frac12\nu(\tau,x)x^2\partial_{xx}c,\qquad c(0,x)=(1-x)^+
$$

$$
(I-\gamma\Delta\tau A^{n+1})U^{n+1}=aU^n-bU^{n-1}
$$

The PDE maps a local-variance surface to a family of call prices. In normalized strike, deterministic carry is absorbed into the forward convention. The working diffusion time is the event-weighted variance clock used by the local-volatility fit; rates and exercise correction were resolved in preprocessing.

The initial payoff has a kink at x = 1. Short-dated densities are narrow around it, so a uniform coarse grid can create operator error exactly where the fit has its most demanding quotes. Grading the spatial and temporal grids puts resolution where the payoff and density require it without making every cell equally small.

For BDF2 with step ratio ω, γ = (1+ω)/(1+2ω), a = (1+ω)²/(1+2ω), and b = ω²/(1+2ω). The first step and excessive growth in step size trigger an implicit-Euler step. All schemes retain a tridiagonal left-hand matrix, so factorization is linear in the number of strike nodes.

The M-matrix property gives a nonnegative inverse for the left solve. BDF2 also contains a subtraction of the previous time layer, so that property is not an unconditional monotonicity proof for the full recurrence. Density, calendar and grid-refinement diagnostics assess the output of the complete discretisation.

**Illustrative calculation.** At a constant BDF2 step size: $\gamma = 2/3$, $a = 4/3$, $b = 1/3$. The negative coefficient on $U^{n-1}$ means an M-matrix on the left alone does not prove unconditional positivity of the full two-step update.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [time_schemes.py](../../backend/volfit/models/localvol/time_schemes.py).

<a id="slide-27"></a>

## 27. Calibrating through the PDE

*4 · Local-volatility calibration*

Forward sensitivities reuse each time-step factorization for all parameter columns.

$$
M S_\ell^{n+1}=\frac{\partial\mathrm{RHS}}{\partial\theta_\ell}-\frac{\partial M}{\partial\theta_\ell}U^{n+1}
$$

$$
L(\theta)=L_{\mathrm{quotes}}+\lambda_x\|D_x^2\theta\|^2+\lambda_\tau\|D_\tau^2\theta\|^2+\lambda_d\|D_x^3c\|^2
$$

Write one discrete step as M(θ)U_next = RHS. Differentiating and moving the derivative of M to the right gives the displayed equation. Once M is factored, each parameter sensitivity is another right-hand side; factorization does not need to be repeated P times.

The implementation propagates forward sensitivities rather than a scalar-objective adjoint. This is convenient because the least-squares solver wants price derivatives at many quote rows. Only columns reached by the time march need to be active. Multi-right-hand-side batching and sparse basis evaluation reduce the overhead.

The optimizer uses the Jacobian in projected Gauss–Newton steps with damping and an iterative least-squares solve. For a band objective, a predicted move can enter or leave an inactive quote interval, so the relevant hinge rows must be reconsidered. Acceptance is based on the actual new cost, not just the local quadratic prediction.

The roughness matrices include spacing factors; otherwise a change in grid density would silently change the regularization meaning. The call-price third-difference term addresses variation in density, which is related to the second strike derivative. These penalties resolve ambiguity in the local variance inferred from a finite set of vanilla prices; small quote error alone does not measure recovery of the latent sheet.

**Computational interpretation.** With $M_x$ strike nodes, $M_\tau$ time steps and $P$ active variance parameters, a full forward sensitivity march costs roughly $O(M_x M_\tau P)$. Shared factorization reduces constants, not the parameter dimension.

**In the app.** Local Vol aside ▸ Fit diagnostics: the per-expiry error table, N PDE solves · price rms, and the ⏵ calibration-trace player.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [04_local_volatility_forward.md](../../Docs/handoff/notes/04_local_volatility_forward.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-28"></a>

## 28. Fitted local variance and the Dupire-derived surface

*4 · Local-volatility calibration*

The Compare view separates the inverse fit from differentiation of a parametric surface.

The inverse fit adjusts the local variance parameters until their generated prices match the selected objective. Dupire extraction starts with a parametric price surface and differentiates it to obtain local variance. In normalized coordinates the continuous expression is ν = 2∂τc/(x²∂xxc), where the denominator is positive and nonzero.

Differentiation magnifies interpolation noise, particularly where density is small. The extracted surface therefore depends on the differentiability and smoothing of the parametric interpolation across both strike and maturity. A subsequent PDE reprice measures how well that derived local variance reproduces its own source prices.

The Compare view separates the source-parametric quote error, the round-trip error and the directly fitted LV error. Those are different questions. The captured comparison must also use compatible vertex and pricing lattices; the archived capture notes document when a surface was withheld because its lattice differed.

The SPY figures are from the recorded September measurement, not the QQQ image. Their purpose is to show why the reporting reprice matters: a solver can partly absorb its pricing-grid error into the fitted local-variance vertices. Refining the pricing grid then exposes that compensation. State both the fitting-grid and refined-grid error when discussing numerical accuracy.

**Recorded SPY measurement · 23 September 2026.** Nine expiries, 875 quotes, 253 vertices: 3.61 vol bp RMS on the fit operator and 5.12 bp on the refined reprice. The second number reveals a discretisation contribution.

**Visual.** 24 September QQQ Compare capture: the source parametric smile, its Dupire-derived reprice, and the directly fitted local-volatility smile.

**In the app.** Local Vol ▸ Compare ▸ Smiles: the three curves per expiry and the score table Parametric · Dupire twin · Affine · Round trip.

**Sources.** [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md).

<a id="slide-29"></a>

## 29. Event-weighted variance time

*5 · Time, spot and stored information*

The event clock changes the time denominator used to report a given total variance.

$$
\tau_{\mathrm{raw}}(t)=t+\frac{1}{365}\sum_{t_e\leq t}N_e
$$

$$
\sigma_{\mathrm{calendar}}=\sqrt{w/t},\qquad \sigma_{\mathrm{event}}=\sqrt{w/\tau}
$$

Total variance is the pricing quantity. The Black map uses w, so the same option price can be labelled by different annualised volatilities according to the chosen denominator. The raw event clock adds N_e/365 to every expiry beyond an event. Its units remain years.

If the optional one-year budget normalization is active, divide the raw clock by its one-year value. This rescales the background clock as well as the events, so the simple unnormalised example on the slide should not be mixed with a normalized desk setting.

For the example, w = 0.20² times 35/365. Dividing by 30/365 gives a calendar volatility of 0.20 sqrt(35/30) = 21.60%. If the event has passed and no other information changes, its additional variance budget drops out of the remaining horizon. A drop in calendar volatility can therefore reflect the removal of event variance.

The invariance is a statement about re-expressing a fixed w. Recalibrating after changing the clock can change regularisation scales, local-variance interpolation and other clock-dependent terms. Separate the display conversion from the fitting experiment. Carry, discounting and American exercise continue on calendar time.

**Visual.** Illustrative 30-day expiry with five extra event days: a 20% event-clock volatility corresponds to 21.60% on the calendar clock, without budget normalisation.

**In the app.** Use the Term view's two clock readings and inspect the event date and extra-day weight.

**Sources.** [11_event_market_clock.md](../../Docs/handoff/notes/11_event_market_clock.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-30"></a>

## 30. Auto-calibrating isolated variance peaks

*5 · Time, spot and stored information*

The expiry ladder identifies excess variance in an interval, rather than the exact event date.

$$
f_i=\frac{w_i-w_{i-1}}{d_i},\qquad N_i=d_i\left(\frac{f_i}{r_i}-1\right)
$$

| Illustrative interval | Days $d$ | Variance per day $f$ | Extra days |
| --- | --- | --- | --- |
| Before | 30 | 0.0001 | 0 |
| Peak | 30 | 0.0002 | 30 |
| After | 30 | 0.0001 | 0 |

Construct the forward-variance ladder from consecutive ATM total variances. This uses differences of two fitted quantities, so first inspect the freshness and consistency of the expiry fits. A stale rung can manufacture a peak even if the underlying quotes have no corresponding event feature.

For an interior interval, the detector compares its daily variance rate with the hotter neighbouring rate. Solving Δw/(d+N) = r yields the displayed extra-day formula. The implementation applies minimum size and relative-peak thresholds and clips peaks iteratively.

The interval location is identified by the expiry grid. The midpoint is a placement convention; the data in that ladder cannot distinguish Tuesday from Thursday within the same gap. A known earnings or policy date can be entered separately after identifying the interval.

The detector targets isolated local maxima. Ramps and broad plateaus require another interpretation of the term structure. The last interval is used as a reference, so a terminal rise alone does not produce a resolved final event.

**In the app.** Parametric ▸ Term: Auto-calibrate events with its horizon — the result line, the Ladder spread readout, and both clock readings on the chart. Use an all-lit ladder.

**Sources.** [ROADMAP.md](../../ROADMAP.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-31"></a>

## 31. Spot transport between calibrations

*5 · Time, spot and stored information*

The SSR rule translates the stored total-variance curve in current log-moneyness.

$$
w_1(k)=w_0(k+Rh),\qquad h=\log(F_1/F_0)
$$

$$
\Delta\sigma_{\mathrm{ATM}}\simeq R\,s_0h
$$

At a fixed strike, k_new = k_old − h. Under R = 1, substituting into the curve rule gives w_new(k_new) = w_old(k_old), which proves the sticky-strike property. This is a useful sign check for the formula.

At the new ATM, the curve reads the old smile at Rh. Differentiating volatility locally gives Δσ_ATM ≈ R s₀ h. For a negative equity skew and a falling forward, this is a positive ATM move when R is positive. The plotted curves use an illustrative quadratic smile; the stated changes are first-order values.

The production display transport acts on total variance. The documentation also gives a vol-space linear scenario approximation; these two conventions agree only to the relevant approximation order. The LV approximation uses the nonlinear map log[exp(h)(exp(k)+1)−1] in its valid domain; the frozen-grid regime performs a PDE reprice. The analytic map is an approximation to dynamics, whereas the grid reprice solves the chosen numerical local-volatility model.

Transport wraps the stored fit instead of changing its fitted parameters. The same rule is used to bring a saved prior to the current forward before forming an innovation. A transported snapshot need not match new option quotes; Calibrate is the operation that incorporates those observations.

**Visual.** Illustrative $h = -2\%$, ATM skew $s_0 = -0.30$. First-order ATM changes are 0, +60 and +120 vol bp for $R = 0, 1$ and $2$.

**In the app.** Spot move card ▸ Scenario: the ±0.1 % dial transports every lens; Options ▸ Dynamics switches the regime Mny · Strike · LV · LV grid · SSR while the fit stays.

**Sources.** [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [ssr.py](../../backend/volfit/dynamics/ssr.py).

<a id="slide-32"></a>

## 32. Activating a prior where quote support is weak

*5 · Time, spot and stored information*

Each persisted operator receives a gate based on the support around the strikes it uses.

$$
g_j=\left[\mathrm{clip}\!\left(1-\frac{\pi_j^{\mathrm{obs}}}{\pi^{\mathrm{req}}},0,1\right)\right]^\gamma
$$

$$
r_j=\sqrt{\lambda_j}\frac{O_j(\theta)-O_j(\mathrm{prior})}{s_j},\qquad \lambda_j=B\frac{g_j}{\sum_m g_m}
$$

The prior preserves selected features of a previous accepted smile when the current observations do not support estimating them closely. Before comparing those features, transport the saved smile into the current spot and forward context. Otherwise a pure spot move could be mistaken for a shape innovation.

For each leg, the support proxy sums quote weights under a Gaussian kernel around its log-strike. For a basket with coefficients c_a and leg supports s_a, the proxy precision is [sum c_a²/(s_a+ε)]⁻¹. This is motivated by independent leg-estimation variances inversely proportional to support.

The gate is exactly zero when this proxy reaches the required threshold. If all gates are closed, the operator budget is not allocated. If some are open, the configured percentage of total quote weight is distributed across them. This rule has an exact local statement: a removed row contributes no cost or derivative.

It does not follow that every well-observed feature is globally unchanged by persistence. Other active rows, nonlinear parameter coupling and model restrictions can move it indirectly. Kernel support also does not measure spread inconsistency or full Fisher information. The Evidence view is useful for seeing the individual gap, weight, source and transport distance rather than treating the mode name as a complete explanation.

**Visual.** Illustrative $\gamma = 1$ gate. Closing one operator's gate removes that residual; parameter coupling can still transmit effects from other active rows.

**In the app.** Options ▸ Prior ▸ Evidence: per expiry and operator, gap · λ · age · src · h — gap near zero where the quotes identify the operator.

**Sources.** [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [prior_persistence_design_options.md](../../Docs/prior_persistence_design_options.md).

<a id="slide-33"></a>

## 33. Persisting shape versus absolute strike values

*5 · Time, spot and stored information*

The choice of operator determines which market moves the prior resists.

$$
\mathrm{RR}(\sigma+c)=\mathrm{RR}(\sigma),\qquad \mathrm{BF}(\sigma+c)=\mathrm{BF}(\sigma)
$$

The operator leg strikes are located on the transported prior and held fixed. A risk reversal has coefficients +1 and −1, whose sum is zero. A butterfly has coefficients one half, one half and minus one, also summing to zero. Adding the same constant to every leg therefore leaves both operators unchanged. This algebra explains why they can preserve shape while current ATM quotes move the level.

An absolute strike anchor asks a different question: keep this unquoted value near the transported prior. That may be appropriate when the old wing level remains informative, but it can resist a genuine parallel volatility move if only the ATM region is currently quoted.

The hybrid mode combines the two ideas: operators carry selected shape or integrated quantities, while strike anchors cover deeper regions. ATM and absolute variance-swap operators are level-sensitive, unlike RR and BF; the gate determines when they are active.

The application offers free, prior and filter comparison fits for inspecting this effect on one node. Use the same quotes, model and objective when switching between them. A visual difference then shows the contribution of the anchoring blocks. Repeating the comparison over chronological frames shows how the effect changes with coverage and market moves.

**Illustrative calculation.** Yesterday's $25\Delta$ call / put = 19% / 23%. After a common +4-point move they are 23% / 27%; $\mathrm{RR}$ remains $-4$ points. An absolute 23% put anchor would oppose the new 27% level.

**Visual.** Illustrative curves: at fixed leg strikes, the +4-point shift preserves RR and BF. An absolute wing anchor retains the earlier level outside the shaded quote region.

**In the app.** On a thin node, compare the Free and +Prior views, then inspect which operator and strike-anchor rows are active.

**Sources.** [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-34"></a>

## 34. Temporal filtering of ATM handles

*5 · Time, spot and stored information*

The filter combines a transported prediction with a new estimate of level, skew and curvature.

$$
K_t=P_t^-(P_t^-+R_t)^{-1}
$$

$$
m_t^+=m_t^-+K_t(z_t-m_t^-)
$$

The observation z is a handle estimate obtained from a smile fit, rather than a raw price tick. The state is small: three handles per node. Before a new observation arrives, the previous state is transported and its covariance widened according to the time and transport model.

In the scalar case, the gain is prediction variance divided by the sum of prediction and observation variances. The example uses 0.30²/(0.30²+0.15²) = 0.8 when all values are expressed in the same vol-point units. The posterior takes 80% of the 0.4-point innovation, giving 20.32%. Its standard deviation is about 0.134 vol point.

The matrix version permits cross-covariances among level, skew and curvature. The implementation uses a Joseph-form covariance update, which retains positive semidefiniteness for a specified gain, including when a gain cap modifies the nominal optimal gain.

This feature answers a different question from a sparse-coverage prior. A region can contain many quotes but still provide a noisy curvature estimate because adjacent prices disagree. The persistence support gate may close there, while the filter still discounts the curvature innovation through a large R. Both depend on explicit modelling choices; the gain is computed from those choices and the observed fit.

**Visual.** Illustrative ATM update: prediction $20.0\% \pm 0.30\%$, observation $20.4\% \pm 0.15\%$ ($1\sigma$). $K = 0.80$ and the posterior mean is 20.32%.

**In the app.** Options ▸ Kalman filter: Overlay only, the diagnostics table K(ATM) · K(skew) · K(curv) · innov bp · ρ, and the Timeline; the smile's FILTER badge.

**Sources.** [15_kalman_computed_trust.md](../../Docs/handoff/notes/15_kalman_computed_trust.md).

<a id="slide-35"></a>

## 35. Observation covariance and active filtering

*5 · Time, spot and stored information*

Noise assumptions enter before the gain is computed; using the filtered state in calibration changes the objective.

$$
R_x\simeq\rho\,G\mathcal I_\theta^{-1}G^\top,\qquad G=\frac{\partial h}{\partial\theta}
$$

$$
L_{\mathrm{active}}=L_{\mathrm{quotes}}+\frac12\|h(\theta)-m^-\|_{(P^-)^{-1}}^2+L_{\mathrm{other}}
$$

| Mode / ingredient | Role |
| --- | --- |
| Information matrix | Quote Jacobian scaled by stated quote noise, plus intrinsic rows |
| Regularised inverse | Clamp small eigenvalues before inversion; retain uncertainty in weak directions |
| Misfit inflation $\rho$ | Widen observation covariance when quotes disagree with their stated noise |
| Use modes | Overlay displays the update; active MAP uses the prediction once inside the fit |

Relative fit weights are not inverse noise variances. The covariance builder first gives quote residuals a stated noise scale, based on bid–ask or haircut width with a floor and short-expiry treatment. It then propagates the regularized parameter information through the handle Jacobian. Intrinsic model rows are part of the information convention; temporal-prior contamination needs separate handling.

A literal Moore–Penrose pseudoinverse would assign zero inverse variance contribution to a direction with zero information. The implementation instead floors small information eigenvalues before inverting, so poorly identified directions remain uncertain. The residual inflation factor increases R when the fitted quote residuals are too large for the stated noise model.

Overlay mode leaves the calibration untouched. Active mode adds the predicted state m− and its covariance as a prior within one MAP optimization. Adding a posterior computed from today's quotes and then refitting those same quotes would count the observations twice. The active route therefore uses the prediction, removes overlapping persistence terms, and treats the committed fit as the posterior result.

Daily-cadence validation does not establish intraday short-expiry stability. The Series roadmap records variance collapse and frame timeouts in active-MAP runs at that cadence. Overlay mode provides gains, innovations and uncertainty diagnostics without changing the quote calibration.

**Recorded operating limitation.** The September Series experiments found severe slowdowns and fit degradation for active filtering on short expiries at intraday cadence. Overlay mode permits inspection without that feedback.

**Sources.** [15_kalman_computed_trust.md](../../Docs/handoff/notes/15_kalman_computed_trust.md); [observation_filter_roadmap.md](../../Docs/observation_filter_roadmap.md); [series_replay_roadmap.md](../../Docs/series_replay_roadmap.md).

<a id="slide-36"></a>

## 36. Series replay and independent calibration lanes

*5 · Time, spot and stored information*

A saved sequence lets different model and memory settings consume the same observations in time order.

| Object | Stored / carried information | Comparison purpose |
| --- | --- | --- |
| Frame | Quotes, spot, as-of time and source | Hold the market inputs fixed |
| Lane | Model and calibration settings | Change one policy or model choice |
| Lane history | Its own prior and filter state | Prevent one variant feeding another |
| Replay | Chronological calibration and transport | Measure response, fit error and runtime |
| Readouts | Smiles, term structure, handles and lane differences | Locate when and where the variants diverge |

A frame is an observation at an instant. A lane is a calculation policy applied to those frames, with its own sequence of fitted states. Keeping frames separate from lanes allows another lane to be calibrated without fetching a different market history.

Each lane must own its previous fitted surface and filter state. The prior for frame i is derived from that lane's earlier state, transported into frame i's context. With no warmup or explicit historical seed, the first frame is a seed fit rather than a steady-state test of persistence.

Replay should proceed in timestamp order. A comparison that recalibrates isolated frames with a later prior would use future information. Similarly, sharing the active filter state across variants would contaminate the experiment. The series workflow stores the selected settings and provides frame-level progress and limits for expensive or diverging calculations.

There are at least three useful outcomes to inspect: fit error to the current quotes, variability of handles through time, and responsiveness to a new move. Smoothing can reduce the second while worsening the third. The recorded short-expiry active-filter failures illustrate why runtime and failed-frame status belong alongside error metrics.

**Illustrative calculation.** Run Free, +Prior and +Prior with filter overlay on identical frames. Compare quote error and frame-to-frame handle movement separately; a smoother path alone is not proof of a better estimate.

**In the app.** Series lens (Alt+6): New series… with the lane presets, then Lanes — the metric chart and the summary table across frames.

**Sources.** [series_replay_roadmap.md](../../Docs/series_replay_roadmap.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-37"></a>

## 37. Graph state: changes from transported priors

*6 · Graph inference*

The graph estimates handle innovations across underlyings and maturities.

$$
d_i=h_i^{\mathrm{fit}}-h_i^0,\qquad h_i^{\mathrm{inferred}}=h_i^0+\widehat z_i
$$

The graph does not start from an empty volatility level. Every node has a resolved baseline, usually a saved prior transported to the current forward. The unknown is the change relative to that baseline. This allows the graph to propagate current movements without replacing the entire historical smile shape.

The baseline may come from that node's own prior or from a documented fallback such as a neighbouring expiry. The provenance changes how much of the final shape was directly known. Displaying the source and transport distance is therefore part of interpreting the output.

A lit node supplies a measured innovation together with uncertainty from its fit and baseline. A dark node supplies no current calibration observation. A component without informative support stays at zero innovation, so its central mark remains the transported baseline and its uncertainty is broad.

The three handles are model-independent summaries but are not a full smile. After the graph solves for their changes, a reconstruction step maps them back into the baseline's selected model. The resulting inferred curve and its residual handle mismatch must be interpreted with that reconstruction in mind.

**Visual.** 24 September capture: 39 observed nodes and eight extrapolated nodes. Calendar and cross-asset relations link the selected universe.

**In the app.** Graph lens (Alt+1): Run, then click a dark node — the Inspector's Prior source, Transport, Innovation and Posterior confidence (1σ).

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [graph_reconstruct.py](../../backend/volfit/api/graph_reconstruct.py).

<a id="slide-38"></a>

## 38. Graph operators and their assumptions

*6 · Graph inference*

The operator determines how relations, observations and retained state contribute to an inferred move.

$$
\widehat z_F=-Q_{FF}^{-1}Q_{FS}d_S
$$

| Operator | Mathematical construction | Behaviour |
| --- | --- | --- |
| Smooth field | A quadratic smoothness prior plus baseline anchoring | Nearby innovations are regularised together |
| Precision messages | Pairwise Gaussian relation factors | Jointly condition all connected innovations |
| Layered | Directed predictions, residual state and reciprocal completion | One-way influence where specified; fresh certified boundaries |

The same universe can be solved under different assumptions about how missing observations relate to the observed ones. A smooth-field prior penalizes departures from a spatially smooth pattern of innovations. Its stiffness and baseline screen determine both reach and attenuation. The legacy formulation also contains an optional transport-geometry term; the documented configuration leaves that term at zero.

The precision-message operator instead builds one Gaussian factor per specified relation. A factor gives an expected relative move and a residual variance. Conditioning all variables jointly accounts for competing relations and shared sources. An arrow in this representation is a written convention, not a causal cut.

The layered operator adds explicitly one-way prediction and a node-specific residual state, then uses reciprocal relations to complete missing values. The displayed Dirichlet equation is the simple reciprocal case with fixed boundaries and no additional target predictions or screen. It follows by differentiating the quadratic energy with respect to the free variables.

When directed predictions or baseline screens are present, they add information to the free-node system. Fixing the central value of a fresh boundary does not make its statistical uncertainty zero. Compare the modes on the same observation set and baseline, then inspect which modelling assumption explains the difference in their outputs.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [graph_precision_message_framework.md](../../Docs/graph_precision_message_framework.md).

<a id="slide-39"></a>

## 39. A precision-message relation

*6 · Graph inference*

An edge specifies an expected response and the variance of departures from that response.

$$
z_i=\beta_{ij}z_j+\epsilon_{ij},\qquad \epsilon_{ij}\sim\mathcal N(0,p_{ij}^{-1})
$$

$$
Q_{\mathrm{msg}}=\sum_{j\to i}p_{ij}(e_i-\beta_{ij}e_j)(e_i-\beta_{ij}e_j)^\top
$$

| Illustrative source: 6M +1 vol point | $\beta = T_{\mathrm{source}}/T_{\mathrm{receiver}}$ | Predicted move |
| --- | --- | --- |
| 3M receiver | 2 | +2 points |
| 1Y receiver | 0.5 | +0.5 point |

Read the edge as a residual z_i − βz_j with a specified standard deviation. Its squared, precision-weighted value is a Gaussian factor. The rank-one matrix form is positive semidefinite even for negative β, and each factor touches only two nodes.

The calendar example uses β = T_j/T_i. This is a selected maturity scaling, motivated by a common total-variance increment when volatility levels are comparable and changes are small. It is not an exact conversion of finite vol-point moves into equal total-variance changes for arbitrary initial volatilities.

For an isolated known source, the receiver mean is βz_j and the relation variance is 1/p. In a full network with finite source uncertainty, competing messages or a baseline anchor, changing p can also change the posterior mean by changing the balance of information. The separation of the edge's amplitude and precision does not eliminate that global effect.

The arrow on a precision factor identifies its written convention. It does not stop information travelling in the reverse direction during joint conditioning. Reading a nonzero-β relation backwards changes the variance to 1/(pβ²). Automatically reciprocal views can describe one factor; explicitly adding another relation is an additional modelling choice.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md).

<a id="slide-40"></a>

## 40. Calendar and cross-asset relation controls

*6 · Graph inference*

The relation editor exposes the response coefficient and uncertainty in the receiver's units.

The response coefficient and relation standard deviation are displayed separately because they answer different questions. The first maps an informer change into the receiver's expected change. The second describes departures from that relation after making the mapping.

For the captured calendar relation, z_i = 1.755 z_j + ε with standard deviation 3.09 vol points. Rewriting gives z_j = z_i/1.755 − ε/1.755. The reciprocal response is about 0.570 and the reciprocal standard deviation about 1.761. It is the same factor written in different units, not an independent new observation.

Automatic relations use classes such as calendar, broad index, sector and peer. Desk edits can change the coefficients and uncertainties, while learned settings depend on the chosen estimation data. A coefficient learned on the scoring sample is not an independent forecast estimate; a replay needs the estimation window recorded.

In the interface, edits can be staged and inspected as previews. Applying a configuration promotes the intended relation set, and a recorded run uses that set. Inspect a changed relation's vote as well as the final posterior because other relations and anchors can alter how much of that vote reaches the result.

**Illustrative calculation.** A +1-point informer innovation gives a +1.755-point relation prediction. Reading the same factor backwards divides both the response and the noise scale by 1.755.

**Visual.** 24 September MSFT relation: $\beta = 1.755$ and $\sigma_{\mathrm{edge}} = 3.09$ vol points. The reverse reading is $\beta \approx 0.57$ and $\sigma \approx 1.76$ points.

**In the app.** Click an arrow on the canvas: the relation card — Confidence σ, β with link handles, Semantics; every edit stages a draft (Apply / Discard), Live previews the re-solve.

**Sources.** [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-41"></a>

## 41. The joint posterior and shared information

*6 · Graph inference*

Solve all coupled innovations together so that repeated routes from one source remain correlated.

$$
Q^+=Q_{\mathrm{msg}}+D_\kappa+H^\top R_dH
$$

$$
Q^+\widehat z=H^\top R_dd,\qquad \Sigma^+=(Q^+)^{-1}
$$

| Illustrative triangle: one noisy source, two routes | Target variance |
| --- | --- |
| Joint Gaussian calculation, all precisions $p$ | $5/(3p)$ |
| Incorrectly treating routes as independent | $6/(5p)$ |

H selects the observed nodes. R_d is a precision matrix here, unlike the observation covariance R used in the Kalman section. The notation is specific to this graph equation. Solving Q⁺z = b gives the posterior mean; the inverse is the mathematical covariance, while computation can use factorizations and selected solves.

For an innovation formed as current calibration minus baseline, the simple independent-error variance is the sum of their variances. The implementation's uncertainty bookkeeping places baseline uncertainty once for each relevant output rather than repeatedly along every route.

In the triangular example, A is observed with variance 1/p, and relations A–B, A–C and B–C each have precision p and unit β. The effective relation variance between A and C is 2/(3p). Adding the shared uncertainty of A gives 5/(3p). Treating the direct path's 2/p and the indirect path's 3/p as independent produces 6/(5p), which is too small.

This distinction also explains why the incoming conditional precision q_i is not the reciprocal marginal variance. A receiver can have precise relations to uncertain informers. Its final uncertainty then remains large even though its configured incoming precision is high.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md).

<a id="slide-42"></a>

## 42. Layered propagation and residual memory

*6 · Graph inference*

Directed predictions and reciprocal calendar completion serve different roles.

$$
m_i^D=\sum_j\frac{p_{ij}}{q_i}\beta_{ij}m_j+m_{u,i}
$$

$$
u_{i,t+\Delta}=2^{-\Delta/H_i}u_{i,t}+\omega_{i,t}
$$

A static precision factor cannot express every directional update policy. The layered mode explicitly separates influence arcs from reciprocal relations. The influence graph is acyclic and evaluated in topological order; directed cycles are rejected rather than silently turned into feedback.

The target prediction combines its parents in receiver units, then adds its own stored residual. When the target is actually observed, the difference between that observation and the systematic prediction updates this residual. The source is not recalibrated by the target's surprise. The illustrative sequence uses innovations relative to aligned baselines throughout, not absolute volatility levels.

Reciprocal calendar relations subsequently complete the remaining nodes. Fresh, certified calibrations can be fixed as central-value boundaries while their uncertainty still propagates. Directed predictions enter as target-side information, so the reciprocal completion does not create a new reverse influence arc to the original source.

The model has separate controls for response β, relation uncertainty, residual half-life and process uncertainty. They should be varied separately in a replay. With half-life five days, a −3-point residual becomes approximately −2.61 points after one day; with no decay it remains −3. Predicted graph marks are not saved back as fresh observed residual measurements.

**Visual.** Illustrative $\beta = 1$, no residual decay: a +13-point systematic prediction meets a +10-point target print, storing $u = -3$. The next +14-point prediction gives +11.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [dynamic_directed_harmonic_graph_framework.md](../../Docs/dynamic_directed_harmonic_graph_framework.md).

<a id="slide-43"></a>

## 43. Reconstructing and displaying an inferred smile

*6 · Graph inference*

The graph supplies target handles; the baseline and model supply the remaining shape.

Three target handles leave many possible full smiles. Reconstruction starts from an available fitted shape, otherwise a prior or nearest-expiry prior, and retains its additional shape information. The LQD ATM-orthogonal chart retargets total ATM variance σ₀²τ, skew and curvature while holding the remaining shape modes fixed.

The chart's nonlinear handle solve can fail for an extreme target combination; that node then has no reconstructed curve. SVI and MCS comparator curves are fitted to the reconstructed LQD target over strikes that clear the time-value floor, so their achieved handles can differ from the targets. Inspect the resulting curve and attained handles when comparing models.

The default graph band applies a delta-method calculation to the smile functional using a diagonal matrix of the three marginal handle variances. It therefore omits cross-handle covariance in that display calculation. The band is conditional on the reconstruction shape and the supplied marginal uncertainty.

The staging process calibrated nodes and saved priors before making some of them dark, so their baselines may contain same-session information. This capture illustrates the curve and uncertainty display. Chronological scoring requires a prior dated before the target observation.

The earlier fit remains as a stale comparison. The graph-inferred record has separate provenance and is not automatically committed as a prior or fresh calibration evidence. Projecting inferred smiles onto a local-volatility sheet is a subsequent fit with its own error and consistency diagnostics.

**Interpretation of this capture.** The reported ATM uncertainty is about 4.4 vol points, while the recorded graph shift is only a few vol bp. The band and central movement describe very different scales.

**Visual.** 24 September AAPL February 2027 capture: violet is the inferred curve; the solid earlier fit is marked stale. Current quote bands are visible for inspection.

**Sources.** [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [README.md](../../Docs/deck/demo_2026-09-24/README.md); [graph_reconstruct.py](../../backend/volfit/api/graph_reconstruct.py); [graph_inferred.py](../../backend/volfit/api/graph_inferred.py); [graph_band.py](../../backend/volfit/api/graph_band.py).

<a id="slide-44"></a>

## 44. Validation against a transported baseline

*6 · Graph inference*

A held-out observation measures incremental information beyond the prior and spot-transport rule.

$$
\zeta_i=\frac{h_i^{\mathrm{held\ out}}-\widehat h_i}{\sqrt{V_i^{\mathrm{pred}}+V_i^{\mathrm{held\ out}}}}
$$

The relevant question is how much the graph adds beyond the baseline, which already contains historical shape and a spot-dynamics assumption. Comparing graph output with a flat volatility surface would answer a different and much easier question.

Leave-one-out removes the target's current observation from the solve. It does not automatically remove historical information from its prior, nor does it make a same-session prior independent of the scoring target. A chronological experiment must seed priors before the held-out time and prevent scoring observations from updating persistent state.

The standardized residual divides by the combined predictive and held-out-estimate uncertainty under an independence approximation. With material correlations, the denominator needs the covariance term as well. A residual spread near one and suitable coverage are useful calibration diagnostics; a small mean error alone does not establish that a band is correctly sized.

The displayed table is a small snapshot check. Its three errors are close, and the baseline is already informative. The smooth-field and precision-message rows also differ in standardized spread and coverage. Treat the table as an illustration of the readout, not a general model ranking; a regime or cadence comparison requires a specified chronological replay and tuning split.

**Visual.** 24 September snapshot check, 39 held-out nodes: ATM RMSE 38.7 bp for the transported prior, 36.7 for smooth field, 38.5 for messages.

**In the app.** Graph drawer ▸ Validation ▸ Compare operators (LOO) — start it while talking; RMSE · ζ mean · ζ std · cov 80 · cov 95 per operator.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [README.md](../../Docs/deck/demo_2026-09-24/README.md).

<a id="slide-45"></a>

## 45. Choosing the next observation

*6 · Graph inference*

A candidate quote can be ranked by the reduction it would make in posterior uncertainty.

$$
\Sigma_{\mathrm{new}}=\Sigma-\frac{\Sigma a a^\top\Sigma}{a^\top\Sigma a+r}
$$

| Rank | Dark node | Variance reduction |
| --- | --- | --- |
| 1 | XOM April 2027 | $-49.5\%\ \sigma^2$ · resolves competing signals |
| 2 | MSFT April 2027 | $-49.4\%\ \sigma^2$ |
| 3 | AAPL April 2027 | $-49.4\%\ \sigma^2$ |
| 4 | NVDA April 2027 | $-39.2\%\ \sigma^2$ |
| 5 | AAPL February 2027 | $-8.1\%\ \sigma^2$ |

This is the Gaussian conditioning formula for adding one scalar noisy measurement. The covariance update does not depend on the unknown observed value, so expected information gain can be ranked before obtaining the quote. The value would affect the posterior mean after it arrives.

If a selects node i, the diagonal variance reduction at another node j is Σ_ji²/(Σ_ii+r). A candidate can therefore be valuable because it is uncertain itself, because it is correlated with several other targets, or both.

The assumed observation noise r matters. A very noisy future quote has little value even at a poorly known node. Changing the graph relations or the aggregation used in the ranking also changes the answer. The ranking is conditional on the specified statistical model.

A node appearing first in the archived table is the preferred place to acquire information under that saved model and objective. The displayed percentage measures uncertainty reduction. Costs of obtaining a quote can be added separately when converting that ranking into a decision.

**Visual.** 24 September capture: XOM April 2027 was ranked first under that run's covariance and candidate-observation assumptions.

**In the app.** Graph drawer ▸ Observation plan: Where to quote next, the ranked dark nodes; Re-rank after changing a relation.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-46"></a>

## 46. Where calibration time is spent

*7 · Computation and inspection*

Separate data retrieval, quote preparation, parametric fitting and the local-volatility inverse problem.

The chart describes one historical workload and one machine. The quoted LQD wall includes the nine-expiry fit stage with calendar processing; the clean ladder triggered no joint repair. It does not predict the cost of a conflicting ladder that requires a repair.

Local volatility dominates the inverse-calculation time in this example because every optimization iteration performs PDE pricing and sensitivities across a surface. A useful warm initial sheet reduces iteration count. The numbers distinguish that warm parameter start from loading a compiled kernel or reusing market preparation.

A live fetch was separately measured at roughly 1.2 to 1.4 seconds for the selected ladder in that experiment. Historical reconstruction and later data-layer changes have their own costs and dates. Adding an old fetch number to a later fitted-model number would not be a measured end-to-end result.

Independent timings can differ in cache state and overlap with shared preparation, so their sum is not necessarily the Calibrate button's time. The recorded whole-job measurement is given separately. On a multi-name universe, ticker-level parallelism can help; on a single ticker, pool startup and transfer costs can outweigh any useful distribution.

**Recorded scope.** Mid target on one captured SPY ladder. The whole Calibrate job was 3.34 s in its own serial run. Separately timed stage medians need not sum to that job measurement.

**Visual.** Recorded 23 September SPY experiment: nine expiries, 875 fit quotes, Intel i7-12700H. Local volatility used 253 vertices and a 368 × 116 pricing lattice.

**Sources.** [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-47"></a>

## 47. Reading fit quality and publication state

*7 · Computation and inspection*

Fit error, data freshness, arbitrage diagnostics and inference uncertainty describe different properties.

An aggregate RMS compresses a distribution of errors under the chosen weighting scheme. Read the maximum and per-expiry errors as well. In a band objective, a small RMS can mean the curve lies inside the selected quote intervals even when it is some distance from their mids.

The consistency checks answer separate questions. A positive single-expiry density does not imply a valid calendar stack. A finite-domain wing check does not identify the remote tail class. A local-volatility fit can have different errors on the fitting and refined operators.

Freshness is another dimension. A fit may have low historical error while its source observations are now old, or while the market has moved since its calibration. The stale marker indicates that the current inputs and saved fit context differ; a transported view is a model-based update of that old fit.

The Quality view consumes cached calibration information. Export and publication decisions use the configured checks and record metadata. Its readiness state summarizes which checks passed under the selected publication policy; model and extrapolation assumptions remain available for inspection.

**Visual.** 24 September capture: the dashboard aggregates cached fit records. Its displayed readiness is a result of the configured checks at that time.

**In the app.** Quality lens (Alt+5): the tiles, the per-ticker rollup and the node table sorted Exceptions first; a node card's certificates and data age.

**Sources.** [README.md](../../README.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [API_AND_UI_INVENTORY.md](../../Docs/handoff/API_AND_UI_INVENTORY.md).

<a id="slide-48"></a>

## 48. A complete worked sequence

*7 · Computation and inspection*

Follow one liquid node and one withheld expiry through the calculation.

| Action | Inspect | Calculation being illustrated |
| --- | --- | --- |
| Select the node and source | Timestamp, exercise style, forward and dividends | Definition of the market input |
| Fit one smile | Quote bands, error distribution, density and tails | Model and objective |
| Inspect the expiry ladder | Total variance, event clock and calendar gap | Maturity consistency |
| Move the spot | Stored fit and transported curve | Chosen spot–vol response |
| Compare anchoring modes | Active prior rows, filter gain and innovation | Use of earlier observations |
| Withhold a current observation | Baseline, incoming relations and inferred curve | Graph inference and reconstruction |
| Replay and score | Same frames, independent lanes, held-out errors | Sensitivity to the selected assumptions |

Choose an example with enough quoted strikes to show the distinction between the observed core and extrapolated wing. Record the source, as-of time, exercise style and carry inputs before fitting. Use the same node through the model, objective and density views so changes remain interpretable.

Next move to the expiry ladder. Compare total variance before interpreting the annualised term structure. If demonstrating event calibration, use a consistently fitted ladder with no stale dark rung creating an artificial local peak.

For the spot move, keep the stored calibration fixed and change only the transport rule or scenario spot. Return to the original spot before comparing prior or filter effects. Inspect active rows and gains to explain why the curve changes.

For a graph demonstration, distinguish a visual withholding exercise from chronological validation. A demonstration may start from saved same-session priors; a validation run needs priors dated before the held-out observations. Record the baseline, graph configuration, achieved reconstructed handles and band before revealing the target quotes.

The companion notes contain the mathematical definitions and computation details for each stage, with pointers to the project documentation. The contents control in the HTML can return directly to any topic during questions.

**Sources.** [README.md](../../Docs/deck/demo_2026-09-24/README.md); [series_replay_roadmap.md](../../Docs/series_replay_roadmap.md); [00_system_overview.md](../../Docs/handoff/notes/00_system_overview.md).

<a id="slide-49"></a>

## 49. One calculation, read in dependency order

*Close*

Observed quotes, fitted quantities and inferred quantities, with the assumptions that separate them stated where they apply.

Close on the distinction that organised the talk rather than on a list of features: what was observed, what was fitted to it, and what was inferred beyond it. Each transition added an assumption — a forward and exercise convention, an objective and a model family, a tail policy, a spot rule, a prior, a noise model, a set of relations — and each assumption is visible in the application next to the number it produced.

Invite questions by topic and use the contents overlay to jump back. The equations, the worked examples and the source references for every slide are in the companion notes; the archived captures and the recorded measurements keep their dates, so any number quoted today can be traced to the session or the experiment that produced it.

**Sources.** [demo_speaker_notes_2026-09-24.md](../../Docs/deck/demo_speaker_notes_2026-09-24.md); [README.md](../../Docs/deck/demo_2026-09-24/rewrite/README.md).
