# Vol-Fitter — speaker notes

Internal technical presentation for quants and traders. Rewritten 28 September 2026.

Companion: [HTML deck](demo_deck.html). The numbering and titles below match the deck. Press **N** for the notes, **O** for the contents, and use the arrow keys to navigate. The deck works offline.

The archived app captures are dated 24 September 2026. Numerical examples labelled *illustrative* explain a mechanism; recorded measurements retain their date, inputs, and scope. Volatility is stored as a decimal: one vol point = 0.01 and one vol bp = 0.0001. Calendar time is t, the pricing variance clock is τ, normalized strike is x = K/F, and log-moneyness is k = log(K/F). Inline `$…$` spans are LaTeX, as on the slides.

## Contents

- [01. Models, calibration and inference](#slide-01)
- [02. Objects and calculation order](#slide-02)
- [03. Universe, observations and fit state](#slide-03)
- [04. Snapshots, streams and vendor limits](#slide-04)
- [05. Synchronising quotes to the current spot](#slide-05)
- [06. Forward and discount from put–call parity](#slide-06)
- [07. Dividends, borrow and the joint carry fixed point](#slide-07)
- [08. Removing the early-exercise premium](#slide-08)
- [09. Exercise correction: numerical cost and accuracy](#slide-09)
- [10. The units of a calibration residual](#slide-10)
- [11. Mid, bid–ask and haircut targets](#slide-11)
- [12. Quote weights and strike spacing](#slide-12)
- [13. What each model parameterises](#slide-13)
- [14. LQD: constructing a probability law](#slide-14)
- [15. LQD: from the quantile to option prices](#slide-15)
- [16. LQD calibration: one build per step, exact derivatives](#slide-16)
- [17. Two ways to summarise a smile: ATM handles and delta packages](#slide-17)
- [18. SVI and its Jump-Wings reading](#slide-18)
- [19. MCS: a convex base plus local corrections](#slide-19)
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
- [35. Where the reading's variance comes from](#slide-35)
- [36. Series replay and independent calibration lanes](#slide-36)
- [37. Graph state: handle changes against transported priors](#slide-37)
- [38. Three graph operators and what each assumes](#slide-38)
- [39. One relation: amplitude and confidence](#slide-39)
- [40. Calendar and cross-asset relation controls](#slide-40)
- [41. The joint posterior and shared information](#slide-41)
- [42. Layered propagation and residual memory](#slide-42)
- [43. Reconstructing and displaying an inferred smile](#slide-43)
- [44. Validation against a transported baseline](#slide-44)
- [45. Choosing the next observation](#slide-45)
- [46. Where calibration time is spent](#slide-46)
- [47. Reading fit quality and publication state](#slide-47)
- [48. A worked sequence on the 24 September desk](#slide-48)
- [49. One calculation, read in dependency order](#slide-49)

<a id="slide-01"></a>

## 01. Models, calibration and inference

*Vol-Fitter · internal technical presentation*

The construction of a volatility surface from option quotes, and its evolution between observations.

The subject today is one calculation: how we turn option quotes into a volatility surface, and how that surface moves between two sets of quotes. It is a technical session. I will put the equations and the app side by side, and every number I quote comes with the date it was measured.

Three parts, as on the slide. Market inputs: everything that happens before a model sees a quote — forwards, dividends, American exercise, timestamps, bid and ask. Calibration: the smile models, local volatility, the objective we minimise, the tails, and consistency across maturities. Updates: what the surface does between two calibrations — event time, spot moves, the saved prior, the temporal filter, and the graph that fills the expiries we do not observe.

The order follows the calculation, not the menus of the app. Each step uses only what the steps before it produced.

One distinction runs through the whole talk. Observed: a quote we have. Fitted: a parameter the optimiser chose. Inferred: a value we produce where there is no quote. Most questions about a mark come down to which of the three it is.

On screen: the Parametric lens on the left, a smile with its quotes and its fit; the Graph lens on the right, observed and inferred nodes. The screens in the deck are captures from 24 September.

**If asked about the data in the screenshots:** a staging session on Nasdaq 15-minute delayed quotes — SPY, QQQ, AAPL, NVDA, XOM and MSFT, monthly expiries, 47 nodes of which 8 dark. The two data-feed screens come from the live desk the same day.

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

First, the vocabulary. A node is one underlying at one expiry: one smile. A surface is the set of nodes of one underlying, tied together across maturities.

The table is the order of the calculation. Prepare: from raw quotes, exercise style, spot and carry, we get European prices, the forward F, the discount factor D, and total variance. Fit: a model and an objective on those prepared quotes give a smile — or, for local volatility, a whole surface. Constrain: neighbouring expiries and the tail policy give calendar diagnostics and, when needed, a repaired surface. Update: when spot moves, the stored fit is transported, or a prior or a filtered estimate takes over. Infer: changes observed on the lit nodes are carried to the dark nodes through the graph, with an uncertainty.

The units at the bottom. We normalise strikes by the forward: x is K over F, k is its log. Prices are divided by D times F, so the normalised underlying has mean one at every expiry — the calendar and density arguments later rely on that. Total variance w is sigma squared times tau.

Two clocks. Calendar time t drives discounting, carry and early exercise. The variance clock tau defines what a volatility number means. With events on the calendar, tau differs from t; total variance does not. So when two volatilities disagree, first check the clock and the forward behind each of them.

Last, the ATM handles: level, skew and curvature of the smile at k equal to zero. The temporal filter and the graph work on these three numbers. They describe the smile near the money; rebuilding the whole smile still needs a base shape and a model family.

**If asked why we normalise by the forward rather than by spot:** with the forward, carry is already inside F, so comparing two expiries compares shapes only. With spot, every comparison would mix shape with rates and dividends.

**Notation and units.** $x = K/F$; $k = \log(K/F)$; $c = C/(DF)$; $w = \sigma^2\tau$. Calendar time $t$ drives carry and exercise. The variance clock $\tau$ defines the volatility reading. One vol bp is 0.0001 of absolute volatility.

**In the app.** Open one node on the Parametric lens and read the Fit diagnostics card: the three handles, the RMS on the smile and on the surface.

**Sources.** [00_system_overview.md](../../Docs/handoff/notes/00_system_overview.md); [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [10_calendar_unnamed_martingale.md](../../Docs/handoff/notes/10_calendar_unnamed_martingale.md).

<a id="slide-03"></a>

## 03. Universe, observations and fit state

*1 · Market inputs*

The universe selection determines which smiles are observed and which are inferred.

This is the Manage universe dialog: six underlyings, 47 expiries. Each expiry chip is a node.

A filled chip is lit: its quotes enter the calibration. An outlined chip is dark: we still want a mark there, and the graph produces it from the lit nodes. So the universe says two things at once — where we observe, and where we want an answer.

Dark means no current quote is used. It does not mean the node was never seen: a saved prior can still carry an earlier fit of it. That matters for testing. Darkening a node right after fitting it shows how the interface works; it does not test a forecast. The forecast test holds nodes out over time, and it comes in the graph section.

Three operations stay separate. Fetch refreshes the quotes. Calibrate re-estimates the parameters. A spot update moves the stored fit with the chosen spot rule, without solving again. When new quotes arrive and auto-calibrate is off, the fit is marked stale and waits for a Calibrate.

Calibrate has three scopes: parametric, local volatility, or both. LQD is the backbone smile; SVI and MCS can be fitted on the same prepared quotes for comparison. Local volatility is fitted jointly across all the expiries of an underlying.

**Transition:** where do these quotes come from, and how fresh is each of them? That is the next slide.

**Visual.** 24 September capture: six underlyings, 47 selected expiries. Filled and outlined expiry controls identify lit and dark nodes.

**In the app.** Open Manage universe, identify one lit and one dark expiry, then show the Calibrate scope menu and the stale indicator.

**Sources.** [ROADMAP.md](../../ROADMAP.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [README.md](../../Docs/deck/demo_2026-09-24/README.md).

<a id="slide-04"></a>

## 04. Snapshots, streams and vendor limits

*1 · Market inputs*

A request pulls the whole chain at one instant; a stream keeps a local book current, contract by contract. Each vendor caps the live set and fills the rest in its own way.

|  | Massive | Bloomberg |
| --- | --- | --- |
| Request | REST snapshot: 250 contracts per page, 2 expiries in flight | Reference request (bdp): BID and ASK per contract |
| Request limit | None stated on the paid plan; 40 calls in flight (≈ 110 per second) drew no 429 | Metered: hits = contracts × fields; ≈ 4–5k unique securities a month on this account |
| Live channel | Websocket: every NBBO change, no conflation | Terminal subscriptions: conflated to 1 s (focus) or 5 s (the rest) |
| Live set limit | ≈ 1,000 contracts held per connection, one connection; app cap 950 | App budget of 3,000 concurrent subscriptions |
| Over the cap | REST snapshot per ticker every 60 s (floor 15 s) | Rotation through 300 reserved slots, ≈ 15–18 contracts per second |

Two ways to get quotes. A request pulls the whole chain at one instant: on Massive, REST pages of 250 contracts; on Bloomberg, one reference request. A stream subscribes once, the vendor pushes every change into a local book, and reading the chain becomes a memory read instead of a network call.

Massive limits the live set. One quotes connection holds about 1,000 contracts at a time, and a subscribe message that would cross that line is refused in full. We run one connection capped at 950, nearest the money first: the expiry on screen gets its whole strip, every ticker gets a floor of 60, and the rest is shared equally. The REST side has no stated call limit on our plan — the history crawl ran 40 requests in flight, about 110 a second, without a single 429. The snapshot endpoint is the exception: beyond two expiries in parallel it got slower, so we stay at two.

Bloomberg is the other way round. Subscriptions are free but capped per Terminal; we budget 3,000. Reference requests are metered: every contract times every field is a hit, against a daily quota and a monthly count of unique securities — about four to five thousand on this account. Asking for BID and ASK only took a two-expiry SPY pull from 4,152 hits to 1,800. The stream is conflated: one update a second for the ticker on screen, one every five seconds for the rest.

What sits outside the live set is still quoted. On Massive, a background REST snapshot per ticker, once a minute, fills the wings; the Quote Table badge reads LIVE or 1-min REST. On Bloomberg, 300 slots are reserved and the overflow rotates through them in buckets: Bloomberg answers each new subscription with the last known quote, we store it with its time and the spot at that moment, unsubscribe, and move to the next bucket. At 15 to 18 contracts a second, a 1,000-contract overflow is refreshed about once a minute.

The speeds, measured on 23 and 24 September. A request: Massive returns nine SPY expiries, 3,454 quotes, in 1.2 seconds; Bloomberg returns two SPY expiries, 900 contracts, in 5.8 seconds. A stream: reading a full SPY book into a chain takes 42 milliseconds, and 420 NVDA contracts delivered 18,842 quotes in the first 8 seconds. A refit on a stream never waits for the network.

**Transition:** the chain we fit is now a mix of quotes with different ages, quoted at different spots. The next slide puts them all on the current spot before the fit.

**If asked why we do not rotate on Massive:** we tested it, and unsubscribing does release the count. But Massive sends nothing on subscribe — a contract appears only when it next changes — so a rotated bucket would wait for the market, while the one-minute snapshot returns every contract's last quote in one call.

**If asked about more live contracts:** a second Massive connection doubles the budget when the plan allows it (one setting). A separate recorder process can own the socket, so the app restarts without losing the day's ticks.

**Measured, 23–24 September.** Request: Massive returns 9 SPY expiries (3,454 quotes) in 1.2 s; Bloomberg returns 2 SPY expiries (900 contracts) in 5.8 s for 1,800 hits. Stream: a full SPY book reads into a chain in 42 ms; 420 NVDA contracts delivered 18,842 quotes in 8 s.

**Visual.** Live desk, 24 September: NVDA on Massive, 420 of 420 contracts acknowledged under the 950 cap, 98 messages per second; the wings come from the 60 s REST layer.

**In the app.** Universe ▸ Manage universe (Ctrl+Shift+U), Data sources card: hover the Massive row for acknowledged / cap / msg/s / rest 60 s. The Quote Table badge reads LIVE or 1-min REST.

**Sources.** [massive_streaming.md](../../Docs/massive_streaming.md); [bloomberg_setup.md](../../Docs/bloomberg_setup.md); [ROADMAP.md](../../ROADMAP.md); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-05"></a>

## 05. Synchronising quotes to the current spot

*1 · Market inputs*

An older quote was priced against the forward of its own moment. Invert it at that forward, then carry it to the current spot with the app's spot–vol rule.

*1 · The error we avoid: inverting at today's forward*

$$
\varepsilon_i \;=\; \hat\sigma_i-\sigma_i \;\simeq\; -\,\frac{\partial V/\partial F}{\partial V/\partial\sigma}\,\bigl(F_{\mathrm{now}}-F_i\bigr)
$$

*2 · Invert at $F_i$, then move to $F_{\mathrm{now}}$*

$$
w_i^{\mathrm{sync}} \;=\; w_i \;+\; \bar w\bigl(K_i \,\big|\, F_{\mathrm{now}}\bigr) \;-\; \bar w\bigl(K_i \,\big|\, F_i\bigr)
$$

*The reference smile, read at forward $F$*

$$
\bar w(K \,|\, F) \;=\; w_{\mathrm{ref}}\!\left(\log\frac{K}{F} \;+\; R\,\log\frac{F}{F_{\mathrm{ref}}}\right)
$$

*3 · Age allowance*

$$
s_i \;=\; a\,\sqrt{t_{\mathrm{now}}-t_i}\;\cdot\;\frac{\sigma_{\mathrm{ATM}}}{15\%}
$$

| Symbol | Meaning |
| --- | --- |
| $K_i,\ t_i,\ S_i$ | Strike of quote $i$, the time it was made, the spot at that time |
| $t_{\mathrm{now}},\ S_{\mathrm{now}}$ | Time and spot of the chain being fitted |
| $F_i,\ F_{\mathrm{now}}$ | Forwards at $S_i$ and at $S_{\mathrm{now}}$, same carry: $F_i = F_{\mathrm{now}}\,S_i/S_{\mathrm{now}}$ |
| $V;\ \sigma_i,\ \hat\sigma_i$ | Option price; its implied vol inverted at $F_i$ (correct) and at $F_{\mathrm{now}}$ (naive) |
| $w_i$ | Total variance $\sigma_i^2\tau$ of the quote at $F_i$ — bid, mid and ask alike |
| $w_{\mathrm{ref}},\ F_{\mathrm{ref}}$ | The node's last committed fit, a function of $\log(K/F_{\mathrm{ref}})$, and its forward |
| $R$ | Spot–vol rule: 0 sticky moneyness, 1 sticky strike, 2 sticky local vol |
| $a,\ \eta_i$ | Age scale, 3.6 vol bp per $\sqrt{\text{minute}}$ at 15% ATM vol; the quote's half-spread in IV |

The previous slide left us with a chain whose quotes were made at different moments: live ticks now, REST quotes up to a minute old, Bloomberg paints older still. Each of those prices was made against the forward of its own moment.

Line one is what goes wrong if we ignore that. Take an old price and invert it at today's forward. The price has not changed, but the forward has, so the inversion reads the forward move as a volatility move. To first order the error is minus the forward delta over vega, times the forward move. At the money that ratio is root pi over two, over F root tau. One month, forward up ten basis points: 43 vol bp of error. At one day, about 240. Calls and puts have opposite forward deltas, so the error has opposite signs on the two wings: a naive inversion tilts the smile.

The fix has two moves. First, invert each quote at its own forward. F_i is the forward at the spot S_i recorded with the quote, with the same carry as now — proportional to spot, or shifted one for one under a cash-dividend schedule. De-Americanisation runs at that spot too. That gives w_i, the quote's total variance, correct at the moment it was made.

Second, move it to the current spot. That needs a view of how the smile moves with spot: the spot–vol rule R, the same rule the app uses between calibrations — zero is sticky moneyness, one sticky strike, two sticky local vol. We apply the rule to a reference smile, the node's last committed fit, not to the quote. W-bar of K given F is that reference's total variance at strike K when the forward is F. The synchronised quote is its own variance plus the change of the reference at that strike, between F_i and F_now.

Read line two as: the quote keeps its gap to the reference, and only the reference moves. The gap is what the market told us, and it passes through unchanged; bid, mid and ask move by the same amount, so the spread is kept. Two checks. Under sticky strike, R equals one, the correction is exactly zero: the vol at a fixed strike does not move, only its moneyness label. And before a first fit there is no reference, so no correction is applied, and the prepared quotes record that.

Line three is about age. A quote four minutes old is not wrong, but it is less certain: the market may have moved since. We treat that like diffusion — a times root age — scaled by the node's ATM vol over 15 percent. a is 3.6 vol bp per root minute, from the SPY intraday study: 19.5 vol bp of ATM drift over 30 minutes, divided by root 30. Four minutes at 15 percent vol gives 7.2 bp.

How the age enters the fit depends on the target. In a band or haircut fit, the band widens by s_i on each side. In a mid fit, the quote's weight is multiplied by one over one plus s over eta squared, eta the half-spread in IV, floored at 1 bp: a quote whose age allowance equals its half-spread counts half. The weights are then rescaled to mean one, so stale quotes rank lower without changing the slice's total weight.

Total variance is held across those minutes, and tau is the chain's. On a chain whose quotes all share one spot and one time — every plain REST fetch — the step does nothing: the output is identical with the switch on or off.

**Transition:** F_i needs a forward, and the forward itself comes from put–call parity. That is the next slide.

**If asked why a reference smile and not the quote itself:** one quote has no skew of its own, and the rule needs the local shape of the smile. The correction is a difference between two nearby points of the reference curve, so an error in the reference's slope enters multiplied by the forward move — a second-order effect.

**If asked where 3.6 comes from:** the SPY intraday observation-filter campaign measured 19.5 vol bp of ATM drift per 30 minutes; 19.5 over root 30 is 3.6. It is a setting in Options ▸ Calibration, and zero switches the age treatment off.

**If asked whether local volatility gets the same treatment:** synchronisation acts on the prepared quotes, which every model reads. The age factor in the mid-fit weights is not yet wired into the local-volatility, compare and anchoring preparation paths; that is a recorded follow-up.

**Worked numbers.** At the money the ratio in step 1 is $N(d_1)/(F\varphi(d_1)\sqrt{\tau}) \approx \sqrt{\pi/2}/(F\sqrt{\tau})$. Forward up 0.1% since the quote: $\varepsilon \approx -43$ vol bp at one month, $-240$ at one day. A 4-minute-old quote at 15% ATM: $s_i = 3.6\sqrt{4} = 7.2$ vol bp; with $\eta_i = 10$ bp its mid weight falls to $1/(1+0.72^2) \approx 0.66$.

**In the app.** Options ▸ Calibration: the Quote synchronisation switch and the age scale $a$, in vol bp per $\sqrt{\text{minute}}$.

**Sources.** [ROADMAP.md](../../ROADMAP.md); [quote_sync.py](../../backend/volfit/api/quote_sync.py); [transport.py](../../backend/volfit/dynamics/transport.py).

<a id="slide-06"></a>

## 06. Forward and discount from put–call parity

*1 · Market inputs*

Every strike quoted on both sides gives one point on a line: its slope is the discount factor, its zero crossing the forward. On American chains the line is first cleaned of early-exercise premia.

*1 · Regression, one vote per pair*

$$
C_j-P_j \;=\; \alpha+\beta\,K_j+e_j, \qquad \hat D=-\hat\beta,\quad \hat F=\hat\alpha/\hat D
$$

*2 · Trim stale pairs (at most 3 rounds, at least 3 pairs kept)*

$$
\text{drop } j \;\text{ if }\; |e_j| \;>\; 4\,\max\bigl(1.4826\,\operatorname{med}_k |e_k|,\; 10^{-4}S\bigr)
$$

*3 · American chains: re-read $F$ from European prices, $\hat D$ held*

$$
F^{(m+1)} \;=\; \frac{1}{|A|}\sum_{j\in A}\left(K_j+\frac{C^{E}_j\bigl(F^{(m)}\bigr)-P^{E}_j\bigl(F^{(m)}\bigr)}{\hat D}\right)
$$

| Question | In the code |
| --- | --- |
| Which strikes | Every strike where the call and the put both have a two-sided, uncrossed quote; at least 3. No moneyness window; quote edits and fit filters act later. |
| Weights | Equal: one vote per pair. The fit's quote-weighting scheme and the bid–ask widths are not used. |
| Absurd slope | $\hat D$ is kept to rates within $[-5\%, 30\%]$. At a bound, $F$ is re-read from the level $K_j + (C_j - P_j)/D$, favouring tight, near-the-money pairs. |
| American: forward | Step 3 until $F$ moves less than 0.5 bp: a median of 3 rounds on 81 real expiries, 6 at most. |
| American: rate | If call and put vols still differ by more than 5 vol bp at $F$, bisect $r$ in $[-5\%, 30\%]$, rerunning step 3 each time: needed on 33 of the 81, median 4 steps (cap 24). |
| Then, per quote | One de-Americanisation of every quote at the final $(F, D)$: 24 bisections on a 192-step tree. No further loop. |

For each expiry, every strike where both the call and the put are quoted gives one number: call minus put. Parity says that number is D times F minus K — a straight line in the strike. The slope is minus the discount factor, the intercept is D times F, and the line crosses zero at the forward.

Which strikes: all of them. There is no moneyness window in the regression. The only limit upstream is the feed's own fetch window, log K over S within four root T, which keeps nearly every listed strike. The fit's filters and your quote edits act later and do not touch the forward.

Weights: equal, one vote per pair. The fit's quote-weighting scheme is not used here, and neither is the bid–ask width. Stale pairs are handled by the trim instead: a pair whose residual exceeds four robust standard deviations is dropped and the line refitted — at most three times, and never below three pairs. The robust sigma is 1.4826 times the median absolute residual, floored at one basis point of spot, so a clean chain never trims.

The slope is the weak parameter. If it implies a rate outside minus 5 to 30 percent, D is clamped to the bound and the forward is re-read from the price level, K plus C minus P over D. That is the one place where spreads matter: tight, near-the-money pairs get the weight.

American chains add a loop. On American prices, call minus put also carries the difference of the two early-exercise premia, and that difference grows with the strike, so it tilts the line. To remove the premia we need the carry — and the carry comes from the very forward we are estimating. So we iterate. From the current forward, set the carry; de-Americanise the call and the put at the pairs nearest the money, at most eleven; reprice them European; re-read the forward at the fixed D. That is line three. It stops when the forward moves less than half a basis point. Measured on 81 real expiries — twelve stored SPY, NVDA, AAPL and QQQ chains — the median is three rounds; the cap of six was reached twice.

Then a check at the money. After de-Americanising, the call and the put at the same strike must share one vol. If they still differ by more than 5 vol bp, the slope was contaminated too, and we bisect the rate between minus 5 and 30 percent until they meet, each step rerunning the forward loop. On the same 81 expiries the check passed on 44, a full-depth refit of the forward was enough on 4, and the bisection ran on 33, with a median of four steps against a cap of 24. When the check passes, D stays exactly as regressed.

Only after that does quote preparation de-Americanise every quote, once, at the final forward and discount: 24 bisections on a 192-step tree per quote. There is no further loop at the quote level. On SPY's nine-expiry ladder the whole forward de-bias took 182 milliseconds.

**Transition:** the regression tells us where the forward is, not why. The why is carry — dividends and borrow — on the next slide.

**If asked why the pairs are not weighted by bid–ask like the fit:** parity holds at every strike, so every pair carries the same information about the line, and the trim removes the stale ones. Spreads enter only when the slope is clamped and the forward is read from the level instead.

**If asked whether the rate from the bisection is a funding rate:** no. A ridge of rate-and-forward pairs closes the gap almost equally well, within one to two percent of rate. The target is the join at the money, not the rate itself. On SPY June 2027 it landed at 6.2 percent and closed the jump from 28 to 1.1 vol bp.

**Recorded, SPY June 2027 (0.93 years).** Raw parity gave $\hat D = 1.0039$, a negative rate, and a 28 vol bp jump between puts and calls at the money. After step 3 and the rate search the jump is 1.1 vol bp. The whole de-bias of SPY's nine forwards took 182 ms.

**In the app.** Forwards lens (Alt+2): the ladder's Parity, Theo and Active columns and the residual count per expiry. On the smile, puts and calls should join at the money.

**Sources.** [06_forwards_dividends_inference.md](../../Docs/handoff/notes/06_forwards_dividends_inference.md); [forwards.py](../../backend/volfit/data/forwards.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-07"></a>

## 07. Dividends, borrow and the joint carry fixed point

*1 · Market inputs*

The theoretical forward is built from the rate and dividend inputs; the borrow is what makes it match the parity forward. On American chains the two depend on each other, so they are solved together.

*1 · Theoretical forward, from the inputs*

$$
F_{\mathrm{theo}}(b) \;=\; \bigl(S-\mathrm{PV}_{\mathrm{cash}}\bigr)\,e^{(r-q-b)\,t}, \qquad \mathrm{PV}_{\mathrm{cash}}=\sum_{t_k<t} d_k\,e^{-r\,t_k}
$$

*2 · Parity forward, after de-Americanising at carry $q + b$*

$$
C^{E}_j(b)-P^{E}_j(b) \;=\; D\,\bigl(F_{\mathrm{par}}(b)-K_j\bigr)+e_j
$$

*3 · Update until the two forwards agree*

$$
b_{n+1} \;=\; b_n+\frac{1}{t}\,\log\frac{F_{\mathrm{theo}}(b_n)}{F_{\mathrm{par}}(b_n)}
$$

*4 · What the read is worth*

$$
\sigma_b \;\approx\; \frac{\mathrm{rms}(e)}{S\,t\,\sqrt{n}}, \qquad \Bigl|\frac{\partial \sigma_{\mathrm{ATM}}}{\partial b}\Bigr| \;\approx\; \sqrt{\tfrac{\pi}{2}}\,\sqrt{t} \;\approx\; 1.25\,\sqrt{t}
$$

| Symbol | Meaning |
| --- | --- |
| $S,\ t$ | Spot; calendar time to expiry in years (ACT/365) |
| $r,\ q$ | Risk-free rate and continuous dividend yield, both inputs |
| $d_k,\ t_k$ | Cash dividend amounts and their ex-dates before expiry, inputs |
| $b$ | Borrow (stock-loan) cost, continuous: the unknown; positive means hard to borrow |
| $C^E_j(b),\ P^E_j(b)$ | Call and put at strike $K_j$, de-Americanised on the tree at $(r,\ q + b)$ with the cash schedule, then repriced European |
| $F_{\mathrm{par}}(b),\ D$ | Forward and discount factor of that parity regression |
| $\mathrm{rms}(e),\ n$ | Residual size and number of pairs of the regression |

The parity forward is measured. The theoretical forward is built: spot, minus the present value of the cash dividends before expiry, grown at the rate minus the dividend yield minus the borrow. Rate and dividends are inputs. Borrow is the unknown — that is line one.

If the two forwards disagree, the borrow that reconciles them is one over t times the log of their ratio. That is the simple read, the Borrow column in the Forwards lens. On a European chain it is exact in one step.

On an American chain it is not, because the borrow changes the early-exercise premia, and the premia move the parity forward. So the parity forward is a function of b — line two: de-Americanise the pairs at carry q plus b, with the cash schedule on the tree, reprice them European, and regress parity again. Line three updates b by the remaining log gap. We start from zero and stop when b moves less than a tenth of a basis point a year. On 81 real expiries that took a median of five passes with a 4 percent rate input, six with a zero rate; a handful hit the cap of eight without converging and are reported as such. At the solution the de-Americanised call and put vols agree and parity holds at the theoretical forward.

Line four is what the read is worth. The noise on b is the parity residual over root n, divided by S times t. The division by t is why a three-week expiry cannot pin a borrow and a six-month one can. The second factor turns borrow into vol: 100 bp of borrow moves the ATM vol by about 125 root t vol bp. It is the same root pi over two as on the synchronisation slide, because borrow acts only through the forward.

The XOM example, recorded on 24 September with the rate and the dividends left at zero: minus 331 plus or minus 18 bp at three weeks, minus 124 plus or minus 3 at six months. That is not a borrow. With zero inputs, b absorbs the missing rate and the missing dividends. The borrow is a residual: it is only as good as the rate and the dividend schedule behind it.

In the fit this is opt-in. With Joint carry on, an expiry uses the joint forward only when the converged borrow is at least 25 bp; below that the parity forward is kept exactly, so ordinary names do not change.

**Transition:** the next slide opens the de-Americanisation itself — how one American price becomes a European one.

**If asked about proportional dividends:** the joint solve needs cash amounts on the tree. With proportional dividends it stands down, and the one-step read is shown instead.

**If asked which rate is used:** one flat continuous rate per ticker. A rate error passes one for one into the borrow; a term-matched rate curve is a recorded follow-up.

**Recorded, XOM, 24 September.** Rate and dividends left at 0: $b = -331 \pm 18$ bp at 3 weeks, $-124 \pm 3$ bp at 6 months. That is a carry mismatch, not a borrow: $b$ absorbs the missing rate and dividends. The uncertainty shrinks like $1/t$.

**In the app.** Forwards lens: tick Joint carry — the Joint and ±σ columns appear; hover a cell for the passes and the ATM-vol sensitivity per 100 bp of borrow. Options ▸ Calibration ▸ Joint carry routes it into the fits.

**Sources.** [06_forwards_dividends_inference.md](../../Docs/handoff/notes/06_forwards_dividends_inference.md); [carry_solve.py](../../backend/volfit/data/carry_solve.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-08"></a>

## 08. Removing the early-exercise premium

*1 · Market inputs*

Find the volatility at which the American tree reprices the quoted mid. At that volatility, the premium is the American price minus the European one.

*1 · Invert the American mid on the tree*

$$
A^{\mathrm{tree}}_i\bigl(\sigma^{*}_i\bigr) \;=\; A^{\mathrm{mid}}_i
$$

*2 · The premium, removed from bid, mid and ask alike*

$$
\widehat{\mathrm{EEP}}_i \;=\; \max\bigl(A^{\mathrm{mid}}_i - V^{\mathrm{Black}}_i(\sigma^{*}_i),\ 0\bigr), \qquad X^{E}_i \;=\; X_i-\widehat{\mathrm{EEP}}_i
$$

*3 · Cash dividends: the escrowed spot at tree step $m$, node $j$*

$$
S_{m,j} \;=\; \bigl(S-\mathrm{PV}(0)\bigr)\,u^{\,2j-m} + \mathrm{PV}(t_m), \qquad \mathrm{PV}(s)=\sum_{s<t_k\le t} d_k\,e^{-r\,(t_k-s)}
$$

An American price is a European price plus the value of the right to exercise early. That second part is not quoted anywhere, so we need a model for it: the binomial tree.

Line one: for each quote, find the volatility sigma-star at which the American tree reproduces the quoted mid. Line two: price a European option at that same volatility with Black, at the resolved forward and discount. The difference is the early-exercise premium, floored at zero because quote noise can push it slightly negative. We subtract the same dollar premium from the bid, the mid and the ask, then invert those European prices as usual.

Why the same volatility for both prices: the tree and Black agree on the European part, so the volatility that makes the tree match the American mid is already the European-equivalent volatility. The tree's discretisation error enters once, through sigma-star, and the next slide measures it.

Which quotes: only the out-of-the-money side — puts below the forward, calls above. One inversion per strike, on the mid. In-the-money options are never fitted.

Line three is the escrowed-spot convention for cash dividends. Split the stock into two parts: the present value of the dividends still to be paid before expiry — known amounts, treated as riskless — and the rest. The tree diffuses only the rest, with the usual up and down factors, so it recombines. At every node, the actual stock price is that diffused part plus the dividends still ahead, discounted to the node's date. Early exercise is tested against that actual price, so a call just before an ex-date sees the dividend it would capture by exercising.

Why not subtract each dividend from the tree directly: after a cash drop, up-then-down and down-then-up no longer land on the same node, and the tree grows exponentially. The escrow keeps it recombining — 192 steps, about nineteen thousand nodes — at the cost of one approximation: the volatility applies to the escrowed part, not to the whole stock.

In the app the cash amounts are rescaled so that the escrowed forward reproduces the resolved forward exactly: the timing is your schedule, the level is the market's. The tree then uses the physical rate. Without a cash schedule it runs on the carry of the resolved forward.

The figure is a recorded SPY chain. Red is the American mid inverted as if it were European; green is de-Americanised. The wide wedge right of the money is deep in-the-money puts, worth hundreds of vol bp, but those are never fitted. On the quotes we do fit, the correction was a median 4.2 vol bp, at most 60 in the put wing.

**Transition:** how accurate is the tree, and how can we afford it on every quote? Next slide.

**If asked about proportional dividends:** they are a fraction of spot, so they fold into a continuous yield; the tree then runs on the continuous carry, with no escrow.

**If asked why not a finer tree:** at 501 steps the error roughly halves, but the cost grows with the square of the steps — about seven times the work per quote.

**Visual.** Recorded SPY chain, put strikes in % of spot: red, American mids inverted as if European; green, de-Americanised. The wide wedge is deep in-the-money puts, never fitted. On the fitted quotes the correction was a median 4.2 vol bp, at most 60.

**In the app.** Forward panel: switch the Dividend model to continuous with q = 0 and Apply — call and put markers split at the money; restore the schedule and Calibrate.

**Sources.** [05_deamericanization_stopping.md](../../Docs/handoff/notes/05_deamericanization_stopping.md); [american.py](../../backend/volfit/core/american.py); [dividends.py](../../backend/volfit/data/dividends.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [deam_real_numbers.json](../../Docs/notes/figures/deam_real_numbers.json).

<a id="slide-09"></a>

## 09. Exercise correction: numerical cost and accuracy

*1 · Market inputs*

The root is solved about a thousand times finer than the tree's own error, and a compiled, parallel kernel makes that affordable on every quote.

*1 · Up factor and probability*

$$
u=e^{\sigma\sqrt{\Delta t}}, \qquad p=\frac{e^{(r-q)\Delta t}-u^{-1}}{u-u^{-1}}
$$

*2 · Backward step: continue or exercise*

$$
V_{m,j} \;=\; \max\Bigl(e^{-r\Delta t}\bigl[p\,V_{m+1,j+1}+(1-p)\,V_{m+1,j}\bigr],\ \Pi\bigl(S_{m,j}\bigr)\Bigr)
$$

*3 · Root by bisection (dichotomy), 24 halvings*

$$
\sigma_{\mathrm{mid}}=\tfrac12(\sigma_{\mathrm{lo}}+\sigma_{\mathrm{hi}}):\quad A^{\mathrm{tree}}(\sigma_{\mathrm{mid}})<A^{\mathrm{mid}} \;\Rightarrow\; \sigma_{\mathrm{lo}}\leftarrow\sigma_{\mathrm{mid}},\ \text{else}\ \sigma_{\mathrm{hi}}\leftarrow\sigma_{\mathrm{mid}}
$$

*4 · Discretisation check: a round trip from a near-exact price*

$$
\varepsilon_{\mathrm{tree}}(K) \;=\; \sigma^{*}_{192}\Bigl(A^{\mathrm{tree}}_{2001}(\sigma_0;K)\Bigr)-\sigma_0
$$

| Step | How often | Cost |
| --- | --- | --- |
| Screen, escrow $\mathrm{PV}(t_m)$, $e^{(r-q)\Delta t}$, $e^{-r\Delta t}$, $\sigma_{\mathrm{lo}}$ | Once per expiry | Shared by all its quotes |
| Scratch arrays for $V_{m,\cdot}$ and $u^{k}$ | Once per quote | Reused by its 26 tree prices: floor, bracket, 24 halvings |
| $u$, $p$ and the powers $u^{k-N}$ | Once per tree price | Two exps, $2N$ multiplies |
| Backward step | 18,721 nodes per tree | Multiply, add, max: no exp |
| Quotes | In parallel | 20 threads on this machine |
| Prepared quotes | Per new chain, forward, carry or clock | Cached: a fit-setting change reuses them |

Three things set the accuracy of the exercise correction: the root, the tree and the quote itself. This slide separates the first two and shows what they cost.

The tree, lines one and two: Cox–Ross–Rubinstein with 192 steps. The up factor is e to the sigma root delta-t, the down factor its inverse, and p the risk-neutral probability of an up-move. Walking backward from expiry, each node keeps the larger of two values: continuing — the discounted average of its two children — or exercising now. The depth is fixed: no adaptation per maturity, no smoothing, no extrapolation.

The root, line three. Yes, it is a dichotomy — plain bisection. Start from a bracket: a floor just above zero volatility, where the tree price sits below the quote, and 50 percent, doubled until the tree price is above it. Then halve the bracket 24 times, each time keeping the half where the tree price crosses the quote. Two to the 24 is about sixteen million, so the bracket ends below 0.002 vol bp.

Why not Newton or Brent: the tree price rises with volatility, but not smoothly — its slope jumps as lattice nodes cross the strike — and bisection needs only the rise, so it cannot misstep. It also costs exactly the same for every quote, which keeps the parallel threads evenly loaded. And a finer root would buy nothing: the tree's own error is about a thousand times larger.

The discretisation check, line four, measures that tree error. Take a known volatility, 25 percent. Price American options at nine strikes on a 2,001-step tree — close to the exact continuous-time price. Hand those prices to the production inverter, 192 steps and 24 bisections, and read the volatility back. The difference is what the depth costs: within 5.4 vol bp, largest on the far 70 put, 3.6 at the money, most strikes under 2. At 501 steps it falls to 2.1, for about seven times the work.

The batch, the table. Everything that depends only on the expiry is computed once: the static screen, the escrowed dividend value at each tree step, the growth and discount factors, the floor of the bracket. Each quote then gets two scratch arrays — one layer of option values, 193 numbers, overwritten in place as the induction walks back, and the table of powers of the up factor, 385 numbers — and runs 26 tree prices: one at the floor of the bracket, one at its top, and 24 halvings. A quote above 50 percent vol needs one to three extra doublings of the top, so up to 29. For each tree price the powers of the up factor are built once — two exponentials and 384 multiplications — so the nineteen thousand node updates are only multiply, add and max. Quotes are independent, so they run in parallel: 20 threads on this machine. Measured today: 300 quotes in 17 milliseconds, 0.056 ms each. The NumPy version of the same algorithm takes 1.3 seconds and returns identical volatilities.

When it compiles: Numba compiles the kernel the first time a process calls it, about one and a half seconds. The machine code is cached on disk, so later processes — a restart, a calibration-pool worker — load it in about 0.2 seconds. It is compiled for the argument types only. Tree depth, bisection count, strikes and chain size are values, so changing them never recompiles; a change of the kernel's source, of Numba, of Python or of the CPU does.

Last row: prepared quotes are cached by content. A new chain, forward, carry or clock recomputes them; changing a fit setting reuses them, so a refit does not pay for the de-Americanisation again.

**Transition:** that closes the market inputs. The prepared quotes are ready; next, the objective we fit them with.

**If asked why 192 steps:** on real SPY, 128 steps moved the de-Americanised vols by about 15 vol bp; 192 brings the tree error down to a few bp at a cost we can pay on every quote. The depth is an accuracy target, not a speed setting.

**If asked whether the compiled kernel changes results:** no. It runs the same bracket and the same bisection as the NumPy version; the difference measured today was zero.

**Measured, 29 September.** Round trip at $\sigma_0 = 25\%$ ($S = 100$, $r = 4.5\%$, $q = 1.2\%$, $t = 0.5$, strikes 70–130): within $\pm 5.4$ vol bp at $N = 192$ (the 70 put $+5.4$, ATM $+3.6$, most under 2), within $\pm 2.1$ at $N = 501$. Speed: 300 quotes in 17 ms, 0.056 ms each; the NumPy version of the same algorithm takes 1.29 s, same results.

**Sources.** [american.py](../../backend/volfit/core/american.py); [american_numba.py](../../backend/volfit/core/american_numba.py); [deam_check.py](../../Docs/deck/prep_2026-09-23/deam_check.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [deamericanization_calibration_speed_note.md](../../Docs/deamericanization_calibration_speed_note.md).

<a id="slide-10"></a>

## 10. The units of a calibration residual

*2 · Objective and smile models*

Every model is fitted by least squares on per-quote residuals. Dividing each price error by the quote's vega makes every residual read in vol units, at every strike.

*1 · Residual: model price error over vega, floored*

$$
r_i(\theta) \;=\; \frac{c_\theta(k_i)-B(k_i,w_i)}{\partial_\sigma B(k_i,w_i)+\eta}
$$

*2 · What it reads: the vol miss, plus a vomma term far from the fit*

$$
r_i \;=\; \Delta\sigma_i\Bigl(1+\tfrac12\,\frac{d_+d_-}{\sigma_i}\,\Delta\sigma_i+O\bigl(\Delta\sigma_i^2\bigr)\Bigr), \qquad \Delta\sigma_i=\sigma_\theta(k_i)-\sigma_i
$$

*3 · Objective (mid target; bands on the next slide)*

$$
\min_\theta\ \sum_i \lambda_i\,r_i(\theta)^2 \;+\; \text{model penalties}
$$

| Symbol | Meaning |
| --- | --- |
| $k_i$ | Log-moneyness $\log(K_i/F)$ of quote $i$ |
| $\sigma_i,\ w_i$ | Market implied vol and total variance $w_i = \sigma_i^2\tau$ |
| $B(k, w)$ | Black call price in forward units: price $/\,(DF)$ |
| $c_\theta(k),\ \sigma_\theta(k)$ | Model call price in the same units, and its implied vol |
| $\partial_\sigma B$ | Black vega at the market vol, $\varphi(d_+)\sqrt{\tau}$; fixed per quote during the fit |
| $d_\pm$ | $-k/\sqrt{w} \pm \sqrt{w}/2$ |
| $\eta$ | Vega floor, $10^{-4}$ |
| $\lambda_i$ | Quote weight: one vote per quote by default |

Every model in the app is fitted the same way: a vector of residuals, one per quote, squared, weighted and summed, plus the model's own penalty rows. This slide is about the unit of one residual.

Line one. The density models, LQD and local volatility, produce prices. c-theta is the model's call price at the quote's log-moneyness, in forward units — price divided by D times F. B of k and w is Black's price of the market quote in the same units. Their difference is a price error, and we divide it by the Black vega at the market vol, plus a small floor eta.

Why divide: least squares assumes the noise has the same size everywhere, in the units of the residual. In price units, a 50 vol bp miss is worth about ten times less in the wings than at the money, so a price fit would all but ignore the wings. After the division, every residual reads in vol units at every strike.

Line two says how exact that is. Expand the price in sigma: the first term is vega times the vol miss, so the residual is the vol miss. The next term is the vomma-to-vega ratio, d-plus times d-minus over sigma, times half the miss. At the money it vanishes. In the wing it grows: a 100 vol bp miss at k equal to 0.2, with 25 percent vol and three months, reads as 105. Near the optimum the misses are small and the residual is the vol error; early in a cold fit it is only approximately so.

SVI and MCS produce vols directly, so their residual is exactly the vol miss. The result is one unit for every model: an RMS of 20 bp means the same thing on all four.

The floor eta. Where vega is tiny — several standard deviations out, or in the last days of an expiry — a small price error would become a huge vol error. The floor stops that: below it the residual behaves like a scaled price error, which is all such a quote can tell us.

The strip is the same arithmetic in dollars: a four-cent price error on an option with 20 dollars of vega per unit of volatility — 20 cents per vol point — gives 0.002, which is 20 vol bp. The currency cancels.

Line three: the objective sums the lambda-weighted squared residuals, plus the model's penalties. Two choices are left, and they are the next two slides: what target inside the bid–ask the residual is measured from, and the weights lambda.

**Transition:** next, the mid in line one is replaced by a band — mid, bid–ask, or haircut targets.

**If asked why LQD is not fitted on implied vols directly:** the model lives in price space, which is what keeps every iterate a valid density. Dividing by vega gives vol units without inverting the model's price at every step.

**If asked whose vega is in the denominator:** the market's — the Black vega at the quote's own vol — so it stays fixed while the parameters move.

**Illustrative calculation.** A 0.04 USD price error on an option with a vega of 20 USD per unit of volatility (0.20 USD per vol point): $r = 0.04/20 = 0.002$, that is 20 vol bp. The currency cancels. Far from the fit the vomma term appears: a 100 vol bp miss at $k = 0.2$ ($\sigma = 25\%$, $\tau = 0.25$) reads as 105 vol bp; at the money it reads as 100.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md); [calibrate.py](../../backend/volfit/models/lqd/calibrate.py); [black.py](../../backend/volfit/core/black.py).

<a id="slide-11"></a>

## 11. Mid, bid–ask and haircut targets

*2 · Objective and smile models*

A band target allows a range of fitted values, with a weak mid anchor selecting among them.

$$
L_i=(m_i-u_i)_+^2+(l_i-m_i)_+^2+\theta_{\mathrm{mid}}(m_i-\bar m_i)^2
$$

The residual of the previous slide measured the model against one number, the mid. But the market quotes an interval, bid to ask, and any value inside it is consistent with the quote. This slide shows the three targets the app offers.

The formula, per quote. m_i is the model's value; l_i and u_i are the lower and upper edges of the target band; m-bar is the mid — all in the residual units of the previous slide, so in vol units. The first two terms are zero inside the band and grow quadratically outside it. The third is a weak pull toward the mid, theta-mid, 0.05 by default.

Mid mode is the plain parabola, the grey curve: every quote is treated as known exactly at its mid. It is the default.

Bid–ask mode is the blue curve: nearly flat inside the spread, quadratic outside. Why keep the weak anchor at all: with the bands alone, a whole family of curves has zero cost — on a clean chain Note 07 measured a flat valley 126 vol bp wide — and the solver would stop wherever it first entered it. The anchor picks one answer: of all the curves the bands accept, the one closest to the mids.

Haircut mode, the orange curve, trims each side toward the mid by h — half a vol point by default — and never past the mid. A spread narrower than two h collapses to a mid target. So tight at-the-money quotes behave as mids, while wide wing quotes keep a real tolerance. On the slide's 19 to 21 percent quote, a half-point haircut leaves 19.5 to 20.5.

Worked through: a model at 20.4 percent sits inside both intervals and pays only the anchor. A model at 20.8 is inside the raw band but 0.3 vol point above the trimmed one, so the haircut target charges it.

What a band buys. Inside the band the data term is twenty times weaker, so the model's own regularisation wins there. On a rigid model, mid and band fits stay close — 6 vol bp apart in Note 07's example. On a flexible model with a smoothness penalty they separate by 47 vol bp: the mid fit follows the tick bounce, the band fit cuts through it. With no smoothness penalty at all the band gains nothing, because the anchor points back at the mids.

Reading the RMS: it measures the objective actually minimised. In bid–ask mode that is the distance outside the band, so a fit sitting inside every band reports close to zero even when it is far from the mids. Compare models only under the same target.

One link back to synchronisation: in band and haircut modes, a stale quote's band is widened by its age allowance on each side.

**Transition:** the target says what each residual is measured against. Next: how much each quote counts — the weights.

**If asked which target to use:** mid is the default and suits a tight, clean chain. Bid–ask or haircut pay off on wide or noisy quotes with a flexible model, where they let the smoothness penalty do its job; the haircut moves continuously between the two.

**If asked whether the band is a hard constraint:** no, a soft one. Outside the band the cost grows quadratically, so a strong pull elsewhere can still push the fit past an edge — by about a twentieth of what the same pull would do in mid mode.

**Visual.** Illustrative 19% / 21% quote. A 0.5 vol-point haircut leaves [19.5%, 20.5%]. The band includes a 0.05 mid-anchor weight.

**In the app.** Show the target shading on the Smile, then the Mid / Bid–Ask / Haircut controls in Calibration options.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-12"></a>

## 12. Quote weights and strike spacing

*2 · Objective and smile models*

The weights decide which parts of the smile the fit cares about: the exchange's listing (equal weights), or a chosen target.

*1 · Target schemes: target shape × spacing, capped, mean one*

$$
\lambda_i \;\propto\; f(k_i)\,\min\!\Bigl(\frac{s_i}{\bar s},\,10\Bigr), \qquad \frac1n\sum_i\lambda_i=1
$$

*2 · Spacing: width of the quote's Voronoi cell*

$$
s_i \;=\; \tfrac12\,\bigl(k_{i+1}-k_{i-1}\bigr)
$$

*3 · Equal weighting, the default: one vote per quote*

$$
\lambda_i \;=\; 1
$$

Line one: every scheme except equal is a target times a spacing correction. The target f is the shape we want the summed weight to follow along the smile — flat, time value, vega or OTM delta. The spacing s_i is the width of the quote's Voronoi cell: the stretch of log-moneyness closer to that quote than to any other. In one dimension that is simply half the gap to the left neighbour plus half the gap to the right, line two; the two end quotes take their one gap.

Why the spacing: think of the objective as an integral of squared error along the smile, weighted by f. On an irregular grid, the sum that approximates it multiplies each quote by the width it stands for. Without that width, listing more strikes in one area would change the objective even though the smile had not moved.

Two safeguards. The spacing multiplier is capped at ten times the average cell, so an isolated far-wing quote cannot dominate. And the weights are rescaled to mean one, so switching scheme does not change the balance between the data and the regularisation.

Equal weighting, line three, is the default and the odd one out: one vote per quote, no correction. The fit then emphasises wherever the exchange lists the most strikes, usually near the money. That emphasis is set by the listing, not by a choice of ours; only on a grid evenly spaced in log-strike does it coincide with the flat target. The figure compares it, in grey, with the time-value target in green.

The strip makes it concrete. Near the money, three quotes a hundredth apart; in the wing, one quote alone in a stretch of 0.03. Equal weights give the cluster three votes to one. With the flat target and the spacing correction, each clustered quote stands for 0.01 and the lone quote for 0.03, so both stretches of the smile weigh the same.

Weights are independent of the target on the previous slide: the fit mode chooses what each residual is measured against, the scheme chooses how much each residual counts.

**Transition:** with residuals, targets and weights defined, the next slide turns to the models themselves — what each one parameterises.

**If asked which scheme to use:** equal is the default. The flat target makes every stretch of the smile count the same when strikes are unevenly listed. Vega, delta and time value fade the wings at increasing speed: vega keeps the most wing weight, time value the least.

**Illustrative calculation.** Near the money, three quotes 0.01 apart; in the wing, one quote alone in a stretch of 0.03. Equal weights give the cluster 3 votes to 1. With the flat target, each clustered quote stands for 0.01 and the lone quote for 0.03, so both stretches of the smile weigh the same.

**Visual.** Reference-note chain: grey, equal weights, 1 per quote; green, the time-value target with the spacing correction. Isolated strikes gain weight, clustered ones share it, and the target fades the far wings.

**In the app.** Smile view: switch the Weights layer on in the layer rail — the strip under the chart shows the target beside the weight the fit sums; hover a bar for k · target · ×spacing · weight.

**Sources.** [07_calibration_objective_measure.md](../../Docs/handoff/notes/07_calibration_objective_measure.md); [weights.py](../../backend/volfit/calib/weights.py); [ROADMAP.md](../../ROADMAP.md).

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

Four models, and what separates them is not the number of parameters. It is the mathematical object each one describes.

LQD describes a probability law, through the log of its quantile slope. It prices by integrating that law, so every fit is arbitrage-free by construction; the only condition is a finite forward — A-R below one, as the next slide shows.

SVI in jump-wing coordinates describes total implied variance as a function of log-moneyness: a tilted hyperbola, read through five desk handles — ATM variance, ATM skew, the two wing slopes and the minimum variance. It prices through Black. Its wings are bounded by construction, but an SVI slice that passes the usual screens can still carry a negative density, so the app checks the density of every displayed slice explicitly.

MCS, the multi-core sigmoid, adds detail in the body. A convex base owns the wings and the overall skew; up to two signed corrections — humps or notches — are built to vanish in both tails. That is how it fits a W-shaped smile ahead of an event without moving the wing slopes.

Local volatility describes the instantaneous diffusion coefficient: a local variance nu of time and normalised strike, continuous and piecewise affine on a grid. It prices every quote by marching the forward Dupire equation through all expiries at once, so it is fitted per underlying, not per expiry. Its controls are positive grid values, a roughness penalty, and checks on the pricing lattice.

Two consequences. The regularisers are not interchangeable: an LQD spectral penalty, an MCS correction penalty and an LV roughness penalty act on different objects, even though each is one coefficient in the options. And LQD is the backbone of the app: the prior, the temporal filter and the graph all work on its handles, even when another model is on screen.

The strip is the rule for a fair comparison: the same prepared quotes, forward, variance clock, target and weights — and the tail and regularisation settings recorded next to the error. Even then, an in-sample RMS says nothing about the curve between or beyond the quotes: compare densities, tails, and behaviour on held-out strikes.

**Transition:** the next slides open each family, starting with how LQD builds its law.

**If asked why keep four models:** they fail differently. SVI is rigid and fast but cannot turn twice; MCS adds body detail with fixed wings; LQD guarantees a valid law at every iterate; local volatility ties all the expiries of an underlying together. Side by side on the same quotes, their differences show the model risk.

**If asked which one the app relies on:** LQD, the backbone that feeds the prior, the filter and the graph. SVI and MCS are comparators on the same prepared quotes; local volatility has its own lens and fits the whole ladder.

**Comparison convention.** Use the same prepared quotes, forward, variance clock, target mode and weighting. Record the tail and regularisation choices alongside the fit error.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [02_svi_jw_rewrite.md](../../Docs/handoff/notes/02_svi_jw_rewrite.md); [03_multicore_mcs_corrections.md](../../Docs/handoff/notes/03_multicore_mcs_corrections.md); [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md).

<a id="slide-14"></a>

## 14. LQD: constructing a probability law

*2 · Objective and smile models*

LQD models the distribution of the log-return through the slope of its quantile. Any real function $g$ gives a valid law: one shift and one inequality do the rest.

*1 · Quantile slope: positive for every $g$, so the density is too*

$$
Q'(u)=q(u)=\frac{e^{g(u)}}{u\,(1-u)}>0, \qquad f_X\bigl(Q(u)\bigr)=\frac{1}{q(u)}
$$

*2 · The smooth part $g$: endpoint terms and a Legendre body*

$$
g(u)=(1-u)\,L+u\,R+\sum_{n=2}^{N}a_n\,P_n(1-2u)
$$

*3 · One shift makes the forward the mean*

$$
Q(u)=\mu+\int_{1/2}^{u}q(v)\,dv, \qquad \mathbb{E}\bigl[e^{X}\bigr]=\int_0^1 e^{Q(u)}\,du=1
$$

*4 · Tail scales: the quantile's slope in log-odds at each end*

$$
A_L=e^{g(0)},\ \ A_R=e^{g(1)}: \qquad \mathbb{P}(X<x)\asymp e^{\,x/A_L},\ \ \mathbb{P}(X>x)\asymp e^{-x/A_R}
$$

| Symbol | Meaning |
| --- | --- |
| $X,\ S_T,\ F_T$ | Log-return to expiry: terminal spot over the forward |
| $u,\ Q(u)$ | Rank in $(0,1)$ and the quantile: $\mathbb{P}(X \le Q(u)) = u$ |
| $q(u),\ f_X$ | Quantile slope, and the density of $X$: at matching ranks $f_X = 1/q$ |
| $g(u)$ | Any real function: the model's parameters live here |
| $L,\ R$ | Endpoint terms of $g$; alone they are not the tail scales |
| $a_n,\ P_n$ | Body coefficients on Legendre polynomials, $n = 2 \ldots N$; $N = 16$ by default |
| $\mu$ | Shift fixing $\mathbb{E}[e^{X}] = 1$ |
| $A_L,\ A_R$ | Left and right tail scales: $A_L = e^{L+\sum_n a_n}$, $A_R = e^{R+\sum_n (-1)^n a_n}$ |

LQD does not model the smile; it models the distribution, through its quantile. X is the log-return to expiry, the log of terminal spot over the forward. Q of u is its quantile: the level X stays below with probability u. u is the rank, between zero and one.

Line one: we model the slope of the quantile, q. It is a fixed skeleton, one over u times one minus u, times e to the g. Because of the exponential, q is positive for every g, so the quantile increases, and the density — which at rank u is one over q — is positive. That is the whole no-arbitrage mechanism: no constraint and no penalty, for any parameters.

Line two: g is the model. Two endpoint terms, L and R, and a Legendre expansion for the body, from a-two up to a-N — sixteen by default. The low modes read like desk quantities: a-two bends the smile symmetrically, the butterfly; a-three tilts it, the risk reversal; a-four works the shoulders.

Line three: integrating q gives the quantile up to a constant, mu. Mu is set so the mean of e to the X is one — the forward is the expected terminal spot. Shifting X by a constant multiplies that mean by e to the mu, so one scalar solves the condition exactly.

Line four, the tails. Near the ends the quantile grows like the log-odds of the rank, and its slope there is e to the g at that end. Those slopes are A-L and A-R, the left and right tail scales. In return space they are exponential tails: in the left tail, every further A-L of log-return down divides the probability by e; in the right tail, every further A-R up does the same.

Why A-R must be below one. The forward is the mean of e to the X. In the right tail the density falls like e to the minus x over A-R; multiplied by e to the x, that is integrable only if A-R is below one. At one or above, the forward would be infinite. The left tail needs nothing, because e to the x vanishes there. This is the only condition on the whole parameter space, and the fit removes even that: it moves rho, with A-R the logistic of rho, so every point it visits is admissible.

One caution on reading L and R: every body mode also moves g at the endpoints, so L and R alone are not the tail scales — the last row of the table gives the exact relation. That is why the fit uses the tail scales themselves as coordinates, with body modes that vanish at both ends.

The strip: switch off the body and set L equal to R, log s. Then g is constant, the quantile is linear in the log-odds, and X is a logistic variable with both tail scales equal to s. A real SPX-like fit gives A-L 0.157 and A-R 0.038: a much heavier left tail than right, which is the skew.

**Transition:** next, from this quantile to option prices, in one integral.

**If asked how the tail scales relate to Lee's wing slopes:** directly. The last finite moments are one over A-R minus one on the right and one over A-L on the left, and Lee's formula maps them to the asymptotic slopes of total variance. For the SPX-like fit those slopes are 0.019 and 0.073, far below Lee's ceiling of 2.

**If asked about the generalised tails:** these formulas are the exponential-tail case, alpha zero. The generalised family adds a per-underlier tail exponent, fixed outside the optimiser; alpha zero reproduces this slide exactly.

**Worked example.** All $a_n = 0$ and $L = R = \log s$: then $g \equiv \log s$ and $X = \mu + s\log\frac{U}{1-U}$ with $U$ uniform, a logistic law with $A_L = A_R = s$. An SPX-like fit has $A_L = 0.157$, $A_R = 0.038$: each further 0.157 of log-return down divides the probability by $e$, each 0.038 up does the same. The heavier left tail is the skew.

**In the app.** Parametric ▸ Density ▸ Log Q-density: the two logarithmic walls at the ends and the Legendre body between them; Density and CDF are one click away.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [schemas.py](../../backend/volfit/api/schemas.py).

<a id="slide-15"></a>

## 15. LQD: from the quantile to option prices

*2 · Objective and smile models*

A call is exercised on every rank above its strike's rank. Its price is the stock those outcomes deliver minus the strike they pay: two running sums along the quantile.

*1 · The payoff, rank by rank: exercised on the ranks above $u_k$*

$$
c(k)=\mathbb{E}\bigl[(e^{X}-e^{k})^{+}\bigr]=\int_{u_k}^{1}\bigl(e^{Q(u)}-e^{k}\bigr)\,du
$$

*2 · Split: asset share minus strike cash*

$$
c(k)=G(u_k)-e^{k}\,(1-u_k)
$$

*3 · The asset share: the stock delivered above rank $u$*

$$
G(u)=\int_{u}^{1}e^{Q(v)}\,dv=\mathbb{E}\bigl[e^{X}\,\mathbf{1}\{X>Q(u)\}\bigr],\qquad G(0)=1
$$

*4 · If $X$ is normal with variance $w$: the two legs are Black's*

$$
G(u_k)=\Phi(d_+),\qquad 1-u_k=\Phi(d_-)\qquad\Longrightarrow\qquad c=B(k,w)
$$

| Symbol | Meaning |
| --- | --- |
| $c(k)$ | Call price in forward units, $C/(DF)$, at $k = \log(K/F)$ |
| $X,\ Q(u)$ | Log-return $\log(S_T/F_T)$ and its quantile at rank $u$ |
| $u_k$ | The strike's rank: outcomes below it expire worthless |
| $1-u_k$ | Probability that the call finishes in the money |
| $e^{Q(u)}$ | $S_T/F_T$ in the outcome of rank $u$ |
| $G(u)$ | Asset share: the forward's value delivered above rank $u$ |
| $e^{k}$ | Strike in forward units, $K/F$ |
| $\Phi(d_\pm)$ | Black's two legs, $d_\pm = -k/\sqrt{w} \pm \sqrt{w}/2$; $B = \Phi(d_+) - e^{k}\Phi(d_-)$ |

The previous slide built the law of the log-return. This one prices an option with it, and the whole calculation fits in one line.

Line one. A call pays S_T minus K when it finishes above the strike. In forward units that is e to the X minus e to the k, when X is above k. Write the expectation rank by rank: the rank u is uniform between zero and one, and the outcome at rank u is Q of u. The call is exercised exactly on the ranks above u-k, the strike's own rank — the rank where the quantile equals k. So the price is the integral, from u-k to one, of e to the Q minus e to the k.

Line two splits that integral in two. The first piece, G at u-k, is the asset share. The second, e to the k times one minus u-k, is the strike cash. The price is the first minus the second.

Line three: what the asset share is. G of u adds up e to the Q over the ranks above u, and e to the Q is terminal spot over forward in that outcome. So G is the part of the forward's value delivered by the outcomes above rank u: the value of receiving the stock in those outcomes only. At u equal to zero that is every outcome, and G is one, because the forward is the mean. At u equal to one it is none, and G is zero. On a desk this is an asset-or-nothing digital.

The strike cash. When the call is exercised the holder pays the strike: in forward units e to the k, which is K over F. It is paid in a fraction one minus u-k of the outcomes, so its value is the strike times that probability — a cash-or-nothing digital times the strike. So 'subtract the strike cash from the asset share' means exactly: what the call receives on exercise, minus what it pays on exercise.

Line four ties this to Black–Scholes. If X is normal, the asset share at the strike's rank is N of d-plus and the exercise probability is N of d-minus: the two terms of Black's formula. LQD keeps exactly the same two legs, for any law.

Why it is fast: Q and G are running sums, built once per parameter set. Every strike then needs one root — the rank where Q equals k — and two look-ups. The next slide shows the build.

The worked example. Switch the body off and keep g constant: the logistic law, both tail scales 0.0813, solved so that the ATM vol is exactly 20 percent at six months. Take a strike 10.5 percent above a forward of 100, so k is 0.10. Its rank is 0.7965: the call is exercised in 20.35 percent of outcomes. The stock those outcomes deliver is worth 24.72. The strike, 110.52, paid 20.35 percent of the time, is worth 22.49. The price is the difference, 2.23 — an implied vol of 20.60 percent, six-tenths of a point above the money. Even this symmetric law has a smile: its exponential tails are heavier than the lognormal's.

**Transition:** the fit needs these prices, and their derivatives in every parameter, many times per second. Next: how one build of the slice gives both.

**If asked why the exercise probability is not Black's N of d-minus at the implied vol:** Black at 20.60 percent says 22.4 percent; the law says 20.35 percent. N of d-minus ignores the slope of the smile. The true probability is minus the strike derivative of the price, and that derivative carries a vega-times-smile-slope term. The two legs differ from Black's one by one; their difference, the price, is the same.

**If asked about the closed form behind the example:** for a constant g the shift is exact, mu equals minus the log of pi s over sine of pi s, minus 0.01088 here; and the asset share is the upper tail of a beta law with parameters one plus s and one minus s — 0.24722 both ways. The forward's own rank is 53.3 percent: more than half the outcomes end below the forward, because the mean of e to the X is held at one.

**Worked example.** Logistic law, $A_L = A_R = 0.0813$: ATM vol exactly 20% at $\tau = 0.5$. Strike 110.52 on a forward of 100 ($k = 0.10$): rank $u_k = 0.7965$, so exercised in 20.35% of outcomes. Asset share 24.72, strike cash $110.52 \times 0.2035 = 22.49$: price 2.23, implied vol 20.60%.

**In the app.** Parametric ▸ Density ▸ CDF: hover at $x = k$ to read the strike's rank $u_k$; one minus it is the chance that the call is exercised.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [quadrature.py](../../backend/volfit/models/lqd/quadrature.py); [DistributionChart.tsx](../../frontend/src/components/DistributionChart.tsx).

<a id="slide-16"></a>

## 16. LQD calibration: one build per step, exact derivatives

*2 · Objective and smile models*

At each step the solver needs every quote's price and its derivative in every parameter. Both come from one build of the slice: running sums on a fixed grid, read at each strike. The strike's rank moves with the parameters, but that move adds nothing.

*1 · A price's derivative: the moving lower limit contributes nothing*

$$
\frac{\partial c(k)}{\partial\theta_j}=\int_{u_k}^{1}e^{Q(u)}\,\frac{\partial Q(u)}{\partial\theta_j}\,du\;-\;\underbrace{\bigl(e^{Q(u_k)}-e^{k}\bigr)}_{=\,0}\,\frac{\partial u_k}{\partial\theta_j}
$$

*2 · The quantile's derivative: one more running sum per parameter*

$$
\frac{\partial Q(u)}{\partial\theta_j}=\frac{\partial\mu}{\partial\theta_j}+D_j(u),\qquad D_j(u)=\int_{1/2}^{u}q(v)\,\varphi_j(v)\,dv
$$

*3 · The shift's derivative: the forward stays the mean*

$$
\frac{\partial\mu}{\partial\theta_j}=-\int_{0}^{1}e^{Q(u)}\,D_j(u)\,du
$$

| Stage | What the code does |
| --- | --- |
| Start | Logistic law: $a_n = 0$, $L = R = \log s$, $s = \sqrt{3w_0}/\pi$ from the quotes' ATM variance $w_0$; in a surface sweep, the previous expiry's fit |
| Build, each trial $\theta$ | 2,001 nodes even in log-odds $\log\frac{u}{1-u}$, from $-40$ to 40, where the quantile's slope is $e^{g}$: running sums give $Q$, then $\mu$, then $G$ |
| Price, each quote | Newton on the interpolated $Q$ for the rank $u_k$, then $G(u_k) - e^{k}(1-u_k)$ |
| Derivatives | Lines 1–3 for all $N+1$ parameters, on the same grid, read at the same ranks |
| Solve | Trust-region least squares on the quote residuals, the ridge and the $A_R$ barrier; stops at relative changes of $10^{-10}$ |
| Accept | One rebuild on 8,001 nodes for the prices, the density and the variance swap |

Calibration is the least-squares problem of slide 10: one vega-scaled price residual per quote, plus a small ridge and the A-R barrier. A trust-region solver needs two things at every trial parameter vector: the residuals — every quote's model price — and the Jacobian — the derivative of each price in each parameter. This slide is how LQD gets both from one build.

The build, second row of the table. g is linear in the parameters, so on a fixed grid it is one matrix product. The grid is even in log-odds — the log of u over one minus u — from minus 40 to 40, because in that coordinate the quantile's slope is simply e to the g: the singular ends of the rank interval are gone. Three running sums follow: integrate e to the g for the quantile; one integral for the shift mu that makes the mean of e to the X one; integrate e to the Q from the right for the asset share G. During the fit the grid has 2,001 nodes.

Pricing a quote: find its rank by Newton on the interpolated quantile — a linear seed and four steps reach machine precision — then asset share minus strike cash, as on the previous slide.

Line one: the derivative of a price. The price is an integral whose lower limit, the strike's rank, moves when the parameters move. Leibniz's rule gives two terms: the integral of the derivative of the integrand, and the integrand at the limit times the speed of the limit. At the limit the integrand is the payoff at the exercise boundary, e to the Q of u-k minus e to the k, which is zero by the definition of u-k. So the second term drops: there is no need to differentiate the root. It is the same reason the exercise boundary drops out of American option Greeks.

Line two: what remains is the derivative of the quantile. Because g is linear in theta, the derivative of the quantile slope q in parameter j is q times a fixed function, phi-j: one minus u for L, u for R, the Legendre polynomial for a-n. So D-j, the derivative of the unshifted quantile, is one more running sum, of q times phi-j, on the same grid.

Line three: the shift. The mean of e to the X stays one for every theta. Differentiate that: the change in mu must cancel the average change of the unshifted quantile, weighted by e to the Q. One integral per parameter.

Put together, the derivative of each price is the derivative of G, read at the quote's rank: two extra running sums per parameter on the grid already built. Finite differences would rebuild the slice once more per parameter and re-solve every strike's rank.

Around the solve. The start is the logistic law of the previous slide's example, scaled to the quotes' ATM variance; in a surface sweep each expiry starts from the previous expiry's fit when the orders match. Capacity: the order is capped at two quotes per parameter, never below six — 24 quotes give order 11, and 34 quotes or more keep the default 16. The ridge, ten to the minus six times n squared times a-n squared from n equal to four, leaves the two lowest body modes free. The accepted fit is rebuilt once on 8,001 nodes for everything displayed.

The strip. Real SPY, the 16 October expiry, 121 quotes, measured on 23 September: the default order-16 fit takes 26 milliseconds, 14 evaluations, 2.06 vol bp RMS. Today, on a 24-quote synthetic strip: 9 milliseconds with the exact derivatives, 23 with finite differences, the same optimum, and the two Jacobians agree to four parts in a hundred thousand.

**Transition:** the same law gives exact ATM handles. Next: the two ways we summarise a smile in three numbers, and which part of the app uses which.

**If asked when the exact Jacobian is not used:** when an active saved prior adds strike anchors or operator rows, the whole fit falls back to finite differences — the same answer, slower. A variance-swap target on its own keeps the exact path.

**If asked about the solver's coordinates:** it moves log A-L, a logistic coordinate for A-R and body modes that vanish at both ends — the chart of slide 14 — and multiplies the Jacobian by the chart's derivative. The optimum does not depend on the chart.

**Measured, 23 and 29 September.** SPY 16 October expiry, 121 quotes (23 September): the default order-16 fit takes 26 ms, 14 evaluations, 2.06 vol bp RMS. On a 24-quote synthetic strip today ($N = 11$): 9 ms with the exact derivatives, 23 ms with finite differences, same optimum; the two Jacobians agree to $4 \times 10^{-5}$.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [calibrate.py](../../backend/volfit/models/lqd/calibrate.py); [jacobian.py](../../backend/volfit/models/lqd/jacobian.py); [interp.py](../../backend/volfit/models/lqd/interp.py); [service.py](../../backend/volfit/api/service.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-17"></a>

## 17. Two ways to summarise a smile: ATM handles and delta packages

*2 · Objective and smile models*

Three derivatives at the money, or three option packages at fixed deltas. They agree to first order but are different coordinates: the filter and the graph carry the first, the prior's default persists the second.

*1 · ATM handles: level, skew, curvature — exact on LQD*

$$
(\sigma_0,\ s_0,\ \kappa_0)=\bigl(\sigma(0),\ \sigma'(0),\ \sigma''(0)\bigr)
$$

*2 · Delta packages: risk reversal and butterfly*

$$
\mathrm{RR}_d=\sigma(k_c)-\sigma(k_p),\qquad \mathrm{BF}_d=\tfrac12\bigl[\sigma(k_c)+\sigma(k_p)\bigr]-\sigma_0
$$

*3 · The link: a Taylor expansion at the money, exact only for a quadratic smile*

$$
\begin{aligned}\mathrm{RR}_d&\approx s_0\,(k_c-k_p)+\tfrac12\,\kappa_0\,(k_c^2-k_p^2)\\ \mathrm{BF}_d&\approx \tfrac12\,s_0\,(k_c+k_p)+\tfrac14\,\kappa_0\,(k_c^2+k_p^2)\end{aligned}
$$

| Consumer | Carries | Why this set |
| --- | --- | --- |
| Kalman filter | $\sigma_0, s_0, \kappa_0$ of the LQD fit | Measured on every chain; exact, so the fit's information gives its noise; a spot move shifts it in closed form |
| Graph | $\sigma_0, s_0, \kappa_0$, as three fields | Same carrier as the filter; the posterior is written back into an LQD smile, the node's other modes held |
| Prior, Hybrid (default) | ATM, RR25, BF25, var swap; tail anchors at $2, 5, 10\Delta$ | Acts only where unquoted; legs reach the wings; RR and BF weights sum to zero, so a level move passes through |
| Prior, Smile factors | ATM, skew, curvature from $\sigma$ at $0, \pm 0.06$ | Available; on liquid chains these legs are quoted, so the gates close |

Two ways to put a smile into three numbers. Different parts of the app use different ones, and the question is why.

Line one, the ATM handles. Sigma-zero is the ATM vol; s-zero is the slope of the vol curve in log-moneyness at the money, the skew; kappa-zero is its second derivative, the curvature. On an LQD slice all three are exact, in closed form: the level from the ATM price, the skew from the ATM digital — the probability of finishing above the forward — and the curvature from the density at the forward, each pushed through Black's formula. No finite difference of a plotted curve.

Line two, the packages. The risk reversal is the vol at the call leg minus the vol at the put leg. The butterfly is the average of the two leg vols minus the ATM vol. A 25-delta call leg is the strike where the forward Black call delta is 0.25; the put leg is where it is 0.75. The strike depends on the smile's own vol there, so it is solved by a short fixed point. The sign is call minus put by default; the Collar sign setting flips it.

Line three, the link. Expand the smile to second order at the money and read it at the legs. The risk reversal is essentially the skew times the distance between the legs. The butterfly is a quarter of the curvature times the squared legs, plus a skew term, because the legs are not symmetric in k. To first order, the packages are the handles rescaled by the leg width.

But only to first order, for three reasons. The leg width is proportional to sigma root tau, so the same handles give different packages at different maturities. The legs are solved on the smile, so they move when the smile moves. And past second order, at 10 delta especially, the wings enter. The strip: an SPX-like smile at nine months has a 25-delta risk reversal of minus 4.28 vol points; the quadratic says minus 4.34. Read the same curve at one month: the legs move in to plus or minus 0.042 and the risk reversal is minus 1.50. Same three handles, different packages. The LQD library can even move RR or BF with the three handles held fixed. So neither set is a function of the other: this is not a linear change of coordinates.

Why the ATM handles for the filter? The filter's job is a state that is observed but noisy. Every chain quotes the money densely, so the three handles are measured at every snapshot. They are exact functions of the fit, so their covariance follows from the fit's own information matrix. And they move in closed form when spot moves: the ATM vol by SSR times skew times the log-forward move, the skew by curvature times the move. A 10-delta leg has none of that: it can be unquoted, and it moves with the forward.

The graph carries the same three, as three separate fields, so the filter, the prior's baseline and the graph share one vocabulary. After the solve, each node's handles are written back into an arbitrage-free LQD smile by moving only three primary directions: the node keeps its own shape in the other modes.

Why packages for persistence? Persistence acts where today's quotes are silent. It needs coordinates whose legs reach the wings, and that do not fight a level move: RR and BF weights sum to zero, so an overnight jump of the whole smile passes through while yesterday's shape is kept. ATM is in the default set too, but its gate is closed whenever the money is quoted.

Could we use both everywhere? In part the app already does. The Smile factors mode persists ATM, skew and curvature, as vol differences at zero and plus or minus 0.06. On a liquid chain those legs are quoted, so the gates close and nothing is persisted: in the stored August-2024 backtest both pure modes had a median gain of zero, against 32 vol bp for the default Hybrid. In the other direction, the filter's active prior is already written as three such rows through the same plumbing, so RR and BF rows could be added — Note 15 lists it as an extension. The costs: a larger state, legs that move with the forward so no closed-form transport, and 10-delta legs that are often unquoted — a gap, which is persistence's job, not the filter's.

**Transition:** next, SVI in its jump-wing reading. Its ATM skew handle, psi, divided by root tau, is exactly s-zero.

**If asked whether the code treats the two sets as overlapping:** yes. With the filter active, the RR and BF persistence rows are switched off, because they would count yesterday's skew and curvature twice; only the deep-tail rows stay.

**If asked about kurtosis:** the third handle in the code is curvature, the second derivative of the vol curve at the money. It reads the density at the forward, a local quantity. Kurtosis is a moment of the whole law; the curvature is its local counterpart on the smile, not the same number.

**Worked numbers.** SPX-like smile: $\sigma_0 = 21.8\%$, $s_0 = -0.178$, $\kappa_0 = 0.024$. At $\tau = 0.75$ the $25\Delta$ legs sit at $k = +0.127$ and $-0.118$: RR25 $= -4.28$ vol points, line 3 gives $-4.34$. The same curve at one month: legs at $\pm 0.042$, RR25 $= -1.50$.

**In the app.** Options ▸ Prior: the Hybrid, Quote operators and Smile factors modes, the Operators chips and the Collar sign; Options ▸ Kalman filter; the Fit diagnostics card shows ATM, skew and curvature.

**Sources.** [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [15_kalman_computed_trust.md](../../Docs/handoff/notes/15_kalman_computed_trust.md); [atm.py](../../backend/volfit/models/lqd/atm.py); [packages.py](../../backend/volfit/models/lqd/packages.py); [operators.py](../../backend/volfit/calib/operators.py); [factors.py](../../backend/volfit/calib/factors.py); [observation_filter.py](../../backend/volfit/calib/observation_filter.py); [prior_mode.py](../../backend/volfit/api/prior_mode.py).

<a id="slide-18"></a>

## 18. SVI and its Jump-Wings reading

*2 · Objective and smile models*

Raw SVI draws total variance as a tilted hyperbola with two straight wings; Jump-Wings reads the same curve as five desk quantities.

*1 · Raw SVI: a V with a rounded bottom, shifted and tilted*

$$
w(k)=a+b\,\bigl[\rho\,(k-m)+\sqrt{(k-m)^2+\xi^2}\,\bigr],\qquad b>0,\ |\rho|<1,\ \xi>0
$$

*2 · Its wing slopes and its lowest point*

$$
\beta_L=b\,(1-\rho),\qquad \beta_R=b\,(1+\rho),\qquad w_*=\min_k w=a+b\,\xi\sqrt{1-\rho^2}
$$

*3 · Jump-Wings: five readings of the same curve*

$$
v=\frac{w_0}{\tau},\quad \psi=\frac{w'(0)}{2\sqrt{w_0}},\quad p=\frac{\beta_L}{\sqrt{w_0}},\quad c=\frac{\beta_R}{\sqrt{w_0}},\quad \tilde v=\frac{w_*}{\tau}
$$

SVI is the market's standard one-expiry parametrisation. It draws total variance, w — vol squared times time — against log-moneyness.

Line one. Start from a V with a rounded bottom: b times the square root of k squared plus xi squared. Then a lifts the whole curve, m slides the rounded corner sideways, rho tilts the two arms in opposite directions, and xi sets how round the bottom is. Five numbers: a, b, rho, m and xi.

Line two. Far from the money the square root is just the distance to m, so both wings are straight lines: slope b times one minus rho on the put side, b times one plus rho on the call side — beta-L and beta-R. Lee's moment formula says no distribution has a total-variance wing steeper than 2. The curve bottoms out at w-star. Note that m is the centre of the square root, not the minimum: the tilt moves the minimum away from it.

Why a second language? The raw coefficients move several desk features at once: b raises both wings and the floor; rho shifts the minimum and trades one wing against the other.

Line three, Jump-Wings. v is the ATM total variance over tau, so root v is the ATM vol. Psi is the slope of root w at the money; divided by root tau it is exactly the ATM skew, s-zero, of the previous slide. p and c are the put and call wing slopes, divided by the ATM total vol, root w-zero — c is Jump-Wings' own name here, not a call price. v-tilde is the minimum total variance over tau, so root v-tilde is the lowest vol on the curve. The figure shows where each one lives: level, tangent and floor on the vol chart; the wing slopes only in total variance, in the inset.

How the app uses it. The fit stores raw SVI. The solver works in a structural chart: the two wing slopes, the location and height of the bottom, and the curvature there, each mapped so that every trial point has both wings under 1.95 — a small buffer under Lee's 2, because the boundary itself allows a negative tail density — and a positive floor. Jump-Wings is a reading of the result; the app has no five-handle input.

Convex is not arbitrage-free. w is strictly convex by construction, but the density depends on w, its slope and its curvature together, through Durrleman's function g. The classic counterexample passes both screens — lowest total variance 0.0116, steeper wing 0.174 — and still has g equal to minus 0.033 near k equal to 0.88: a negative density. So every displayed slice is checked on 801 points across the quoted strikes, and a failing fit is refitted once with a penalty on negative g, kept only if it passes.

The strip: the SPX-like smile of the previous slide is an exact SVI slice. Its Jump-Wings reading: ATM vol 21.8 percent; skew minus 0.178, the same s-zero; wing slopes 0.072 on the put side and 0.014 on the call side; lowest vol 16.0 percent at k equal to 0.57, well beyond the quotes on the call side.

**Transition:** SVI has one minimum; it cannot turn twice. Next: MCS, which adds local bumps to a convex base without moving its wings.

**If asked how well the handles are identified:** take the same smile with a two-bp ripple, quoted from k minus 0.5 to plus 0.32. An SVI fit matches the quotes to 0.43 vol bp RMS with rho minus 0.32 instead of minus 0.68. The ATM vol, the skew and the put wing come back; the call wing, 0.037 instead of 0.014, and the floor, which sit beyond the last quote, do not. Read the handles where the quotes are.

**If asked why the structural chart is the default:** a benchmark run before the switch — equal or better precision in all twelve regime medians, no breaks, and about three times faster than the raw chart.

**If asked about psi equal to zero:** when the ATM is the minimum, the five handles lose the curvature of the bottom and many raw slices share them; the checked conversion from Jump-Wings to raw refuses that point.

**Worked example.** SPX-like smile, $\tau = 0.75$: $a = 0.0096$, $b = 0.0427$, $\rho = -0.68$, $m = 0.283$, $\xi = 0.306$. Read in JW: $\sqrt{v} = 21.8\%$, $\psi/\sqrt{\tau} = -0.178$, $p = 0.380$, $c = 0.072$, $\sqrt{\tilde v} = 16.0\%$.

**Visual.** Reference-note curve read in Jump-Wings: ATM vol $\sqrt{v}$, ATM tangent of slope $\psi/\sqrt{\tau}$ and lowest vol $\sqrt{\tilde v}$ on the vol chart; the wing slopes $p\sqrt{v\tau}$ and $c\sqrt{v\tau}$ only in total variance (inset).

**In the app.** Parametric ▸ Compare: the SVI chip beside LQD — RMS, Lee slopes, tails; + reference adds eSSVI.

**Sources.** [02_svi_jw_rewrite.md](../../Docs/handoff/notes/02_svi_jw_rewrite.md); [02_svi_jw_moments.md](../../Docs/handoff/notes/02_svi_jw_moments.md); [svi.py](../../backend/volfit/models/svi_jw/svi.py); [structural.py](../../backend/volfit/models/svi_jw/structural.py); [calibrate.py](../../backend/volfit/models/svi_jw/calibrate.py); [display.py](../../backend/volfit/models/display.py); [diagnostics.py](../../backend/volfit/models/diagnostics.py); [schemas.py](../../backend/volfit/api/schemas.py).

<a id="slide-19"></a>

## 19. MCS: a convex base plus local corrections

*2 · Objective and smile models*

A convex base owns the wings and the overall skew; up to two signed hats add a shoulder or a notch in the body and vanish in both wings. Not arbitrage-free by construction: the core count, a ridge, a wing penalty and the density check govern it.

*1 · Log-cosh: a rounded absolute value, straight far out*

$$
\Phi_\gamma(x)=\frac{4}{\gamma^{2}}\log\cosh\frac{\gamma x}{2}\;\approx\;\tfrac12x^{2}\ \text{near }0,\qquad \Phi_\gamma'(x)\to\pm\frac{2}{\gamma}
$$

*2 · Model: base (value, slope, curvature at $z_0$) plus $n_c \le 2$ signed hats*

$$
v(z)=\underbrace{v_0+v_1\,(z-z_0)+v_2\,\Phi_{\gamma_\pm}(z-z_0)}_{\text{base}}\;+\;\sum_{j=1}^{n_c}\alpha_j\,B_j(z)
$$

*3 · Hat: a second difference of the same log-cosh, height 1 at $m_j$*

$$
B_j(z)=\frac{\Phi_{\gamma_j}(z-m_j-h_j)-2\,\Phi_{\gamma_j}(z-m_j)+\Phi_{\gamma_j}(z-m_j+h_j)}{2\,\Phi_{\gamma_j}(h_j)}
$$

MCS, the multi-core sigmoid, answers what SVI cannot: a smile that turns twice — the W before an event, a shoulder on each side of a central trough. A convex curve has one minimum and no interior maximum, so no convex model can draw it.

Units first. MCS models the annualised implied variance v, sigma squared, against z: log-moneyness divided by sigma-ref root tau, where sigma-ref is the quoted vol nearest the money. So z counts standard deviations, and one unit of z means the same thing at every maturity.

Line one, the building block: the log-cosh. It is a rounded absolute value — a parabola, x squared over two, near zero, and a straight line of slope two over gamma far out. Gamma sets how fast it straightens.

Line two, the model. The base is v-zero, plus v-one times the distance to the centre z-zero, plus v-two times the log-cosh. The log-cosh and its slope vanish at zero and its curvature there is one, so v-zero, v-one and v-two are simply the base's value, slope and curvature at its centre. Gamma-minus and gamma-plus let the two wings straighten at different rates. Six numbers. The base is convex, like SVI: it owns the wings and the overall skew. Careful: z-zero is fitted, so these are not the ATM level and skew — those are read from the full curve.

Then the corrections: up to two signed hats, alpha-j times B-j. A positive alpha raises a shoulder; a negative alpha digs a notch.

Line three, the hat. Evaluate the same log-cosh at three points — the centre m-j, and h-j either side of it — and form the second difference: left, minus twice the middle, plus right. Divide by two Phi of h so that the height at the centre is exactly one. Four numbers per hat: height, centre, half-width, sharpness. With two cores the model has fourteen parameters.

Why the wings never move: a second difference of any straight line is zero, and the log-cosh is a straight line far out. So each hat, its slope and its curvature all vanish in both wings, and the wing slopes stay the base's: v-one minus two v-two over gamma-minus on the left, v-one plus two v-two over gamma-plus on the right. Adding cores changes the body, never the tails.

The figure: the orange base, two dashed hats of height 0.019 at plus and minus 0.2 in log-moneyness, and their grey sum, a W. Far out, the sum rejoins the base.

The strip: on a base variance of 0.09 — a 30 percent vol — a hat of height 0.019 lifts the vol at its centre to 33.0 percent, three points; alpha over two sigma, 3.2, is the quick estimate. With the starting shape the fit uses, half-width 0.4 and sharpness 5, a hat keeps 4 percent of its height one unit of z from its centre, and 0.03 percent two units away.

Flexibility is governed. MCS is not arbitrage-free by construction: a hat can bend the density negative. So: at most two cores, and fewer on short chains, never more parameters than quotes; a small ridge on the heights; hats smaller than the fit's own noise are pruned and the fit is redone once without them; a penalty on negative g beyond the quotes, doubled on the put side; and, as for SVI, the 801-point density check with one repair refit.

**Transition:** that closes the smile models. Next chapter, the surface — starting with the tails and the generalised LQD tail exponents.

**If asked why not three cores:** in the stored backtest a third core cut the out-of-sample RMS only from 13.99 to 13.58 vol bp, for about four times the fit time and more butterfly arbitrage. Two is the cap.

**If asked whether the hat parameters mean anything:** not one by one. Two overlapping hats can trade height, so only the curve is identified; the ATM level, skew and curvature shown for MCS are read from the full curve.

**Illustrative calculation.** A hat of height $\alpha = 0.019$ on a 30% vol lifts its centre to $\sqrt{0.09 + 0.019} = 33.0\%$. Seed shape $h = 0.4$, $\gamma = 5$: 4% of it is left one unit of $z$ away, 0.03% at two.

**Visual.** Reference-note decomposition: the convex base (orange) and two hats of height $+0.019$ (dashed) add up to the W-shaped total (grey, $v_R$ in the figure); far out the total rejoins the base.

**In the app.** Parametric ▸ Compare: MCS chip; Options ▸ Parametric: MCS cores R ($n_c$), wing penalty %.

**Sources.** [03_multicore_mcs_corrections.md](../../Docs/handoff/notes/03_multicore_mcs_corrections.md); [kernels.py](../../backend/volfit/models/sigmoid/kernels.py); [sigmoid.py](../../backend/volfit/models/sigmoid/sigmoid.py); [calibrate.py](../../backend/volfit/models/sigmoid/calibrate.py); [seeding.py](../../backend/volfit/models/sigmoid/seeding.py); [penalties.py](../../backend/volfit/models/sigmoid/penalties.py); [display.py](../../backend/volfit/models/display.py); [schemas.py](../../backend/volfit/api/schemas.py); [HyperparamPanel.tsx](../../frontend/src/components/HyperparamPanel.tsx); [ParametricSection.tsx](../../frontend/src/components/options/ParametricSection.tsx).

<a id="slide-20"></a>

## 20. Generalised LQD tail exponents

*3 · Tails and maturity consistency*

One exponent per side moves each LQD tail from exponential to Gaussian decay. The quoted strikes barely see it; the moments and the far wings do.

*1 · Quantile speed: slide 14's $e^{g}$ times one gauge per side*

$$
\frac{dQ}{dz}=e^{g(u)}\,\bigl(1-\log u\bigr)^{-\alpha_-}\,\bigl(1-\log(1-u)\bigr)^{-\alpha_+},\qquad 0\le\alpha_\pm\le\tfrac12
$$

*2 · Right tail of $X$, to leading order as $x \to \infty$ (the left mirrors it with $A_L$, $\alpha_-$)*

$$
\log\mathbb{P}(X>x)\;\sim\;-\Bigl(\frac{(1-\alpha_+)\,x}{A_R}\Bigr)^{\frac{1}{1-\alpha_+}}
$$

*3 · Far right wing of total variance, for $\alpha_+ > 0$*

$$
w(k)\;\sim\;\frac12\Bigl(\frac{A_R}{1-\alpha_+}\Bigr)^{\frac{1}{1-\alpha_+}}\,k^{\frac{1-2\alpha_+}{1-\alpha_+}}
$$

| $\alpha$ · preset | Log-return tail (right side) | Far-wing total variance |
| --- | --- | --- |
| $0$ · Exp | Exponential, $e^{-x/A_R}$: $\mathbb{E}[Y^r]$ finite only for $r < 1/A_R$ | Linear in $k$, at the Lee slope of the next slide |
| $0.25$ · Int | $e^{-c\,x^{4/3}}$ with $c = (0.75/A_R)^{4/3}$: every $\mathbb{E}[Y^r]$, $r > 0$, finite | Sublinear, $\propto k^{2/3}$; Lee slope 0 |
| $0.5$ · Gauss | Gaussian rate, $e^{-x^2/(4A_R^2)}$: a normal tail of variance $2A_R^2$ | Tends to the constant $2A_R^2$; Lee slope 0 |

Slides 14 and 15 built the LQD law with exponential tails. This is the one extension of that construction: a tail exponent per side, alpha-minus on the left and alpha-plus on the right, each between zero and one half.

Line one. z is the log-odds of the rank, log of u over one minus u, and the quantile's speed in z is e to the g, as on slide 14. We multiply it by two gauges: one minus log u, to the power minus alpha-minus, and one minus log of one minus u, to the power minus alpha-plus. Each gauge is about one plus the absolute value of z in its own tail and tends to one in the other, so each exponent slows only its own tail. At alpha zero both factors are one and we are back on slide 14 exactly; the code skips the multiplication, so default fits are bit-identical.

Line two: what the slowdown does to the log-return. Integrate the speed and the quantile grows like z to the power one minus alpha instead of linearly. Invert that: the log-probability of a return above x falls like minus the quantity one minus alpha, times x, over A-R, raised to the power one over one minus alpha. At alpha zero that is the exponential tail, e to the minus x over A-R. At one quarter the power is four-thirds. At one half it is two: the Gaussian rate, the tail of a normal law with variance two A-R squared. These are leading-order statements, reached far out in the tail.

Line three: what it does to the smile far out. Total variance grows like k to the power one minus two alpha over one minus alpha: linear at alpha zero, k to the two-thirds at one quarter, and flat at one half, where it tends to two A-R squared. So any positive alpha gives a Lee slope of zero on that side, because every moment is finite there. The table lists the three presets of the panel: Exp, Int and Gauss.

Gaussian rate describes the far tail only. The body is still the Legendre expansion of g, and it can be skewed or bimodal. A zero limiting slope does not mean a flat smile at traded strikes either: the wing can be steep over the quoted range and bend only far beyond it.

Policy. The exponents are chosen, not fitted: one pair per underlying, shared by every expiry of that underlying, set in the Options panel globally or per ticker. They sit beside the parameter vector, not inside it, so priors, the filter and the graph see the same number of parameters at any alpha.

Why not fit them: a small positive alpha is almost invisible on a finite strike strip, yet it changes the moment domain from 'finite up to some order' to 'all finite'. The strip is a recorded scenario run on AAPL September. Refitted with Gaussian-rate tails on both sides, the strip error moves from 12.6 to 12.5 vol bp and the var-swap vol from 32.06 to 32.01 percent. But at alpha zero the moments of Y are finite only between minus 3.95 and 19; at one half, all of them are. Same quotes, same fit quality, a different tail class. The desk makes that choice, and the scenario report compares its consequences.

**Transition:** the next slide makes the link between tails and wings exact, for any model: Lee's moment formula.

**If asked why the range stops at one half:** from zero to one half the family runs from the exponential class to the Gaussian rate. Beyond one half the exponent in line three turns negative, so far-wing total variance would fall towards zero: tails thinner than Gaussian. The code rejects any value outside zero to one half.

**If asked what replaces the condition A-R below one:** with a positive alpha-plus the forward is finite for any A-R. What remains is a numerical guard at the edge of the grid, z equal to 40: the speed there, A-R times 41 to the minus alpha-plus, must stay below 0.999. At alpha one half that allows A-R up to about 6.4.

**If asked how the exponents interact with calendar order:** with a common alpha, the far expiry's tail scales must be at least the near one's, on each side; the certificate of slide 24 reports that clause. Different exponents across expiries are outside the policy: a lighter far tail cannot be repaired by any fit.

**Recorded scenario run · 13 August 2026.** AAPL 18-Sep-26 (0.17 y), same quotes, refitted with $\alpha_\pm = 0$ and with $\alpha_\pm = 1/2$: strip RMS 12.6 vs 12.5 vol bp, var-swap vol 32.06% vs 32.01%. The moments $\mathbb{E}[Y^r]$ are finite only for $-3.95 < r < 19.0$ at $\alpha = 0$, for every $r$ at $\alpha = 1/2$.

**In the app.** Options ▸ Parametric ▸ Tail $\alpha_-$ · $\alpha_+$: presets Exp · Int · Gauss, scope Global or per ticker. Compare's Tails L/R column and Quality's Tail order read the result.

**Sources.** [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [quadrature.py](../../backend/volfit/models/lqd/quadrature.py); [basis.py](../../backend/volfit/models/lqd/basis.py); [tails.py](../../backend/volfit/models/lqd/tails.py); [schemas.py](../../backend/volfit/api/schemas.py); [tail_scenarios.py](../../backend/backtest/tail_scenarios.py); [tail_scenarios.json](../../backend/backtest/results/tail_scenarios/tail_scenarios.json).

<a id="slide-21"></a>

## 21. Wing slopes and finite moments

*3 · Tails and maturity consistency*

How steeply total variance grows in the far wings is set by how many moments the terminal price has. Lee's formula makes the link exact, for any model.

*1 · Wing slopes: growth of total variance per unit of $|k|$, far out*

$$
\beta_R=\limsup_{k\to+\infty}\frac{w(k)}{k},\qquad \beta_L=\limsup_{k\to-\infty}\frac{w(k)}{|k|}
$$

*2 · Critical moments: how far the moments of $Y$ stay finite*

$$
p^*=\sup\bigl\{p\ge0:\ \mathbb{E}[Y^{1+p}]<\infty\bigr\},\qquad q^*=\sup\bigl\{q\ge0:\ \mathbb{E}[Y^{-q}]<\infty\bigr\}
$$

*3 · Lee's moment formula*

$$
\beta_R=\psi(p^*),\quad \beta_L=\psi(q^*),\qquad \psi(p)=2-4\bigl(\sqrt{p^2+p}-p\bigr)
$$

*4 · LQD with exponential tails: read off the tail scales*

$$
p^*=\frac{1}{A_R}-1,\qquad q^*=\frac{1}{A_L}
$$

| Symbol | Meaning |
| --- | --- |
| $Y = S_T/F_T$ | Terminal price over the forward; its mean is one |
| $k,\ w(k)$ | Log-moneyness $\log(K/F)$; total implied variance $\sigma^2\tau$ at $k$ |
| $\beta_R,\ \beta_L$ | Right (call) and left (put) wing slopes of $w$; always between 0 and 2 |
| $p^*$ | Right critical moment: $\mathbb{E}[Y^{1+p}]$ finite for $p < p^*$. The count starts after the mean, which is always finite |
| $q^*$ | Left critical moment: $\mathbb{E}[Y^{-q}]$ finite for $q < q^*$; small when much probability sits near $Y = 0$ |
| $\psi$ | Lee's map from a critical moment to a wing slope |
| $A_L,\ A_R$ | LQD tail scales (slide 14): $\mathbb{P}(X<x) \asymp e^{x/A_L}$, $\mathbb{P}(X>x) \asymp e^{-x/A_R}$, $X = \log Y$ |

The previous slide chose the tail class. This one connects the tail to something visible in the smile: how fast total variance grows in the far wings.

Notation first. Y is the terminal price divided by the forward, so its mean is one. k is log-moneyness, log of K over F, and w of k is the total implied variance there, sigma squared tau. Beta-R is the right, call-side wing slope: far out, how much total variance grows per unit of k. Beta-L is the same on the put side, per unit of minus k. Line one defines them as a limsup, the limit of the upper envelope, so they exist for any smile.

Line two: the critical moments. p-star measures the right tail: the moments of Y of order one plus p stay finite for p below p-star. We count from one because the first moment, the forward, is always finite. q-star measures the left tail through negative moments, Y to the minus q: they blow up when much probability sits near zero.

Line three is Lee's theorem: each wing slope is psi of the critical moment on its side. Psi falls from 2 at p equal to zero, where only the mean is finite, to zero as p goes to infinity, where every moment is. At p equal to one it is 0.34. A heavy tail forces a steep wing, a light tail a flat one. The ceiling of 2 is model-free: a steeper wing would price far out-of-the-money calls that never become worthless.

Line four is the LQD case, and it takes two lines of algebra. The right tail falls like e to the minus x over A-R, and Y to the power one plus p is e to the one plus p times x, so the moment is finite exactly when one plus p is below one over A-R: p-star is one over A-R, minus one. On the left, Y to the minus q is e to the minus q x, against a tail like e to the x over A-L, so q-star is one over A-L. That is where the minus one on the right comes from, and why there is none on the left.

The strip is a recorded fit, QQQ December, on 24 September. The tail scales are 0.628 on the left and 0.056 on the right. Left: q-star is 1.59, and psi of that is 0.243. Right: p-star is 16.9, psi is 0.029. These are the Lee slopes the fit diagnostics card prints: far out, the put wing gains about a quarter of a unit of total variance per unit of log-strike, and the call wing is almost flat.

What the app does with it. LQD needs no constraint: its slopes follow from the tail scales, and A-R below one, the finite forward, keeps the right slope below 2. SVI, in its default structural chart, holds both slopes below a cap of 1.95, strictly inside the ceiling, because a wing sitting exactly at 2 already misprices. MCS in its default chart has no cap: its slopes are reported, and Quality flags any above 2; its structural chart, opt-in, applies the same 1.95 cap.

Keep the scope in mind: these are limits. They say nothing about the shape just beyond the last quote, where options still carry value. That region has its own butterfly and calendar checks on the extrapolated wing.

**Transition:** the wings are also where a variance swap takes part of its value. Next slide.

**If asked about the generalised tails:** any positive alpha makes every moment finite on that side, so p-star is infinite and the Lee slope is zero, whatever the tail scale. The wing still grows, but slower than linearly.

**If asked why 2 is the ceiling:** along a ray w equal to beta times k with beta above 2, the Black call tends to one instead of zero as the strike goes to infinity, which no law with a finite mean can produce. At exactly 2 it tends to one half, still inadmissible; hence caps strictly below 2.

**Recorded QQQ fit · 18-Dec-26, 24 September.** Fit diagnostics: $A_L = 0.628$, $A_R = 0.056$. Left: $q^* = 1/0.628 = 1.59$, $\beta_L = \psi(1.59) = 0.243$. Right: $p^* = 1/0.056 - 1 = 16.9$, $\beta_R = \psi(16.9) = 0.029$. These are the card's Lee slopes: a steep put wing, a nearly flat call wing.

**In the app.** Parametric ▸ Fit diagnostics ▸ wings · Lee · var-swap: $A_L$, $A_R$ and both slopes. Compare shows Lee L/R per model; Quality flags a slope above 2.

**Sources.** [09_wings_last_quote.md](../../Docs/handoff/notes/09_wings_last_quote.md); [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [basis.py](../../backend/volfit/models/lqd/basis.py); [schemas.py](../../backend/volfit/api/schemas.py); [calibrate.py](../../backend/volfit/models/sigmoid/calibrate.py); [quality.py](../../backend/volfit/api/quality.py); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-22"></a>

## 22. Variance swaps as an integrated constraint

*3 · Tails and maturity consistency*

A variance-swap quote is one number per node, but it prices the whole strike strip, wings included. The fit meets it through one extra least-squares row.

*1 · Fair total variance: the log contract, replicated with out-of-the-money options*

$$
w_{\mathrm{VS}}=2\left[\int_0^1\frac{p(x)}{x^2}\,dx+\int_1^\infty\frac{c(x)}{x^2}\,dx\right]=-2\,\mathbb{E}[X],\qquad \sigma_{\mathrm{VS}}=\sqrt{w_{\mathrm{VS}}/\tau}
$$

*2 · The objective as the solver sees it: a plain sum of squared rows (plus the model's penalty rows)*

$$
\min_\theta\ \sum_i\bigl(\sqrt{\lambda_i}\,r_i\bigr)^2+r_{\mathrm{VS}}^2,\qquad r_{\mathrm{VS}}=\sqrt{\lambda_{\mathrm{VS}}}\,\bigl(\sigma_{\mathrm{VS}}^{\mathrm{model}}-\sigma_{\mathrm{VS}}^{\mathrm{quote}}\bigr)
$$

*3 · The weight of the var-swap row: a share of the node's option weight*

$$
\lambda_{\mathrm{VS}}=\frac{\mathrm{pct}}{100}\sum_i\lambda_i,\qquad \text{Hard pin: }\ \lambda_{\mathrm{VS}}=10^4\sum_i\lambda_i
$$

A variance swap pays realised variance against a fixed strike. Its fair strike is one number per node, but it depends on the whole smile, wings included: exactly the part the option quotes leave free. A quote on it is new information.

Line one. x is strike over forward; p and c are the undiscounted put and call in forward units. The fair total variance is twice the integral of out-of-the-money options weighted by one over x squared: puts below the forward, calls above. That is the static replication of the log contract, so it equals minus two times the expected log-return. Divide by the variance clock tau and take the square root: the var-swap vol. It equals expected realised variance only for continuous paths; jumps add a cubic correction and discrete dividends sit outside the derivation. The fit uses this diffusion fair strike.

Each model evaluates line one where it is cheapest. LQD takes minus two times E of X straight from its quantile grid, with an analytic derivative. SVI and MCS integrate their closed-form smile on a fixed strike grid. Local volatility uses the same static replication, or optionally a backward PDE for the expected remaining variance.

Line two answers the question: why lambda, and why its square root. The least-squares solver never sees weights; it squares its rows and adds them up. We want a var-swap miss to count with weight lambda-VS. So the row we hand the solver is the square root of lambda-VS times the miss: squared, it gives back lambda-VS times the squared miss. Every option row is built the same way, square root of lambda-i times r-i, so the sum is exactly the weighted objective of slide 10 plus one term. The row is in vol units like the option rows, so a one-bp var-swap miss trades against one-bp quote misses at the ratio of the weights, and nothing else.

Why the setting is lambda and not its square root: weights add up across rows, square roots do not. Line three makes lambda-VS a percentage of the summed option weights: the setting varSwapWeightPct, 10 by default. At 100 percent the one var-swap quote weighs as much as all the options together, and that meaning does not depend on how many quotes the node has.

The strip is the recorded QQQ card. 225 quotes at equal weight and a saved setting of 15 percent: lambda-VS is 33.75, its square root 5.81. The model sits at 25.03 percent, the quote at 25.04: a miss of about one vol bp becomes a row of about 5.8 bp. Squared, it weighs like 33.75 option quotes each one bp off. The card reports the term as about 1 percent of the node's squared error.

Hard pin replaces the percentage by ten thousand times the option weight. In row units that is a hundred times the whole data block, so the fitted var-swap lands on the quote to solver tolerance. It is still a penalty, not an exact constraint; it stays below the weight of the calendar rows, so a pinned quote cannot override them; and prior var-swap rows are never pinned.

Where the response goes. One integrated number cannot say which wing should move. The caption's split shows the stake on this node: 87 percent of the replicated variance comes from the quoted strikes, 13 percent from the put wing beyond them. The model's own tail law decides how the pull is shared, so after a change, read both the remaining gap and the wings.

**Transition:** next, the second constraint that couples smiles: calendar order between expiries.

**If asked how the local-volatility fit applies the same weight:** its var-swap row is written in total variance, so the weight enters as a tolerance: two sigma-VS tau times one vol point, divided by the square root of lambda-VS. Squared, the row carries the same weight as here.

**If asked about the clock:** the app quotes vols on its variance clock tau, which is calendar years when no events are set. Total variance is the same on any clock; a quote made on another clock must be converted before it is entered.

**Recorded QQQ card · 24 September.** 225 quotes at equal weight: $\sum_i\lambda_i = 225$. Saved setting 15%: $\lambda_{\mathrm{VS}} = 0.15 \times 225 = 33.75$ (the card's 33.8), $\sqrt{\lambda_{\mathrm{VS}}} = 5.81$. The model misses the quote by about 1 vol bp, so the row reads about 5.8 bp; squared, it weighs as much as 33.75 option quotes each 1 bp off.

**Visual.** QQQ 18-Dec-26, 24 September capture: quote 25.04%, model 25.03%. Weight 15% of the quote weight (default 10%), about 1% of the node's squared error. Replication: 87% from the quoted strikes, 13% from the put wing beyond them.

**In the app.** Parametric aside ▸ Variance swap card: add a quote at the model level, move it and watch the wings. The weight % sits in Options ▸ Calibration; Hard pin makes the row stiff.

**Sources.** [08_varswap_representations.md](../../Docs/handoff/notes/08_varswap_representations.md); [varswap.py](../../backend/volfit/calib/varswap.py); [service.py](../../backend/volfit/api/service.py); [schemas.py](../../backend/volfit/api/schemas.py); [affine_varswap.py](../../backend/volfit/api/affine_varswap.py); [calibrate.py](../../backend/volfit/models/lqd/calibrate.py); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-23"></a>

## 23. Calendar consistency across expiries

*3 · Tails and maturity consistency*

Two expiries can each be a valid law and still price a calendar spread below zero. The test compares calls at the same moneyness, or the LQD ledger at the same rank.

*1 · Same log-moneyness $k$: calls in forward units, equivalently total variance*

$$
c_{T_2}(k)\ge c_{T_1}(k)\ \ \forall k\quad\Longleftrightarrow\quad w_{T_2}(k)\ge w_{T_1}(k)\ \ \forall k
$$

*2 · Same rank $u$: the upper share $G$ of slide 15, called the ledger*

$$
G_T(u)=\int_u^1 e^{Q_T(v)}\,dv,\qquad G_{T_2}(u)\ge G_{T_1}(u)\ \ \forall u
$$

*3 · Why the two tests agree: each curve is an extremum over the other*

$$
c_T(k)=\max_{u}\bigl[G_T(u)-e^{k}(1-u)\bigr],\qquad G_T(u)=\min_{k}\bigl[c_T(k)+e^{k}(1-u)\bigr]
$$

Two expiries of the same underlying, each fitted well on its own, can still disagree with each other: together they can price a calendar spread below zero. This slide is the test; the next one is the repair.

Notation. T-one is the near expiry, T-two the far one. Each is normalised by its own forward: Y-T is the terminal price over the forward, with mean one. c-T of k is the call in forward units at log-moneyness k, and w-T of k the total implied variance there. G-T of u is the upper share of slide 15, which the code calls the ledger: the share of the forward paid by the outcomes above the u-quantile. It starts at one at rank zero, where every outcome counts, and falls to zero at rank one.

Line one: the condition. At every log-moneyness, the far call is worth at least the near call. Because the Black price rises with total variance at fixed k, that is the same as the far total variance being at least the near one. With equal means, ordering every call orders every convex payoff: the far law is a mean-preserving spread of the near one, which is convex order. By Kellerer's theorem, convex order plus a valid density at each date is exactly what it takes for some martingale to have these laws as its marginals.

Line two: the same order, read at the same rank instead of the same strike. The far ledger must lie above the near ledger at every u.

Line three says why the two readings agree. Take the outcomes above rank u and pay the strike on that event: you collect G of u and pay e to the k times one minus u. The best cut-off is the strike's own rank, so the call is the maximum of that difference over u. Read backwards, the ledger is a minimum over strikes. A maximum, or a minimum, of ordered curves is ordered, so order at every strike and order at every rank are the same statement. Comparing densities point by point would not be.

Why keep both readings. The quotes live at strikes, so the fit is screened at fixed strikes on the common quote support. The rank reading is free for LQD, since G is already computed for pricing, and it reaches the far tails without any implied-vol inversion; the certificate on the next slide uses it.

Variance, not vol: the strip takes the figure's pair at the money. Three months at 30 percent is a total variance of 0.0225; six months at 20 percent is 0.02. The far total variance is lower, so the forward variance is negative, minus 0.01: a calendar spread with a negative price. For this pair to be admissible the six-month vol needs at least 21.2 percent. Now put the three-month vol at 24 percent: its total variance is 0.0144, and the same 20 percent at six months is fine, with a forward variance of 0.0224, a forward vol of 15 percent. A vol that falls with maturity is not the problem; a total variance that falls is.

The figure is from the reference notes: fitted alone, the far slice sits below the near one across the whole strip. Refitted under a floor at the near slice, it is lifted onto the near curve and no further: zero forward variance there, the edge of what is admissible. In this figure only the far slice moves; the production repair on the next slide lets both move.

**Transition:** how the app finds and repairs such a pair, and how it proves the result: next slide.

**If asked about dividends and rates:** the comparison is at fixed forward moneyness, under deterministic carry. At a fixed cash strike, with discrete dividends, raw prices can cross without any arbitrage; stochastic rates would break the equivalence altogether.

**If asked about local volatility:** a positive local variance makes Dupire prices increase with maturity at every strike, so calendar order holds by construction; the app only checks the discrete scheme.

**Illustrative calculation.** The figure's pair at the money: 3 months at 30%, $w = 0.0225$; 6 months at 20%, $w = 0.0200$. Forward variance $(0.0200 - 0.0225)/0.25 = -0.010$: an arbitrage. With 24% at 3 months ($w = 0.0144$), 20% at 6 months is fine: forward vol 15.0%.

**Visual.** Reference-note figure: total variance against $k$, near $T = 0.25$ (grey, under the teal), far $T = 0.5$. Fitted alone, the far slice (red, dashed) lies below the near one: negative forward variance across the shaded range. Refitted under a floor at the near slice (teal), it is lifted onto the near curve and no further.

**In the app.** Parametric ▸ Stacked IV: total variance per expiry, crossings circled (cal. cross chip); Levels · $\Delta$ pairs plots each far-minus-near difference.

**Sources.** [10_calendar_unnamed_martingale.md](../../Docs/handoff/notes/10_calendar_unnamed_martingale.md); [01_lqd_model_coordinates.md](../../Docs/handoff/notes/01_lqd_model_coordinates.md); [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [gen_calendar.py](../../Docs/notes/figures/gen_calendar.py); [quadrature.py](../../backend/volfit/models/lqd/quadrature.py).

<a id="slide-24"></a>

## 24. Calendar repair and numerical certification

*3 · Tails and maturity consistency*

Fit each expiry alone, repair only the pairs that violate, then certify the stored surface on the whole line: at the nodes, between them and in the tails.

*1 · Ledger gap at the same rank, and its exact slope at every node*

$$
\Delta G(z)=G_{\mathrm{far}}(z)-G_{\mathrm{near}}(z),\qquad \partial_z\Delta G=u(1-u)\bigl(e^{Q_{\mathrm{near}}(z)}-e^{Q_{\mathrm{far}}(z)}\bigr)
$$

*2 · Hermite ledger gap: on each cell, the cubic that matches both end values and both end slopes*

$$
\Delta\hat G(z_j+t\,h)=c_0+c_1t+c_2t^2+c_3t^3,\qquad 0\le t\le1
$$

*3 · Interior candidates: where that cubic's slope vanishes*

$$
c_1+2c_2\,t+3c_3\,t^2=0,\qquad 0<t<1
$$

*4 · Certificate: the minimum over nodes, interior roots and one tail point per side*

$$
\min_{z\in\mathbb{R}}\,\Delta\hat G(z)\;\ge\;-10^{-6}
$$

| Step | Calculation | Outcome |
| --- | --- | --- |
| 1 · Independent fits | Each expiry on its own quotes, no calendar rows | A clean ladder keeps them, bit for bit |
| 2 · Screen | Near minus far call on the common quote support, over vega | Violation above 0.5 vol bp |
| 3 · Symmetric repair | Joint Gauss–Newton on each violating run; hinge weight $\times 10$, at most 3 times | Both slices concede, by their data weight |
| 4 · Exchange | Where the certificate fails: stiff ledger row ($10^6$) at the worst rank; refit | Up to 8 rounds, else irreducible |
| 5 · Certificate | Exact minimum of the Hermite ledger gap | Below $-10^{-6}$: not ready, Publish blocked |
| 6 · Tail order | Far tail scales $\ge$ near ones, on each side | Advisory; blocks only with the Tail-order gate |

Slide 23 gave the test. This one shows how the app enforces it, then proves the result, and it defines the Hermite ledger gap. Start with the table, top to bottom.

Step one: fit every expiry on its own quotes, with no calendar rows. Step two, the screen: for each adjacent pair, compare near and far calls at fixed strikes, on the strikes both expiries quote, divided by vega so the number reads as a vol gap. Above half a vol bp it is a violation. Most ladders are clean, and then the independent fits are kept, bit for bit.

Step three, the symmetric repair: each run of violating pairs is refitted jointly by Gauss–Newton, with both slices' own quote rows plus hinge rows on the interface. Each slice keeps its quote weights, so the better-informed slice moves less. If a violation survives, the hinge weight is multiplied by ten, at most three times. The older sequential route, near to far with each slice floored by the previous one, made the later expiry pay for everything.

Step four, the exchange: any pair the certificate still rejects gets a stiff ledger row, weight one million, at the rank where the certificate found its worst gap, and is refitted; up to eight rounds. A pair whose worst rank keeps coming back is declared irreducible: its quotes disagree, and the app reports it rather than flattening the surface.

Now the certificate, and the term in the title. Line one: the ledger gap is the far ledger minus the near ledger at the same rank, slide 23's comparison, written on the log-odds grid: 8,001 nodes from minus 40 to 40, step 0.01. Its slope is known exactly at every node: u times one minus u, times e to the near quantile minus e to the far quantile. So the gap can only turn where the two quantile curves cross.

Line two: the Hermite ledger gap. Between nodes, the app stores each ledger as a cubic Hermite interpolant: on every cell, the one cubic that matches the exact values and the exact slopes at both ends. Hermite interpolation means matching slopes as well as values. The pricer reads call prices from that same interpolant. The Hermite ledger gap is the difference of the two stored cubics: one cubic per cell again, with the coefficients c-zero to c-three listed under the formulas.

Line three: on a cell, a cubic reaches its minimum at an end or where its slope is zero, and the slope is a quadratic in t. So the candidates are finite: every node, at most two roots per cell, and beyond the grid one closed-form point per side, where the two tail continuations cross. Line four: the certificate takes the minimum over all of them and requires it above minus ten to the minus six, a hundredth of a basis point of the forward. It is the minimum of the stored object, not of a sample, so it is exact.

The strip shows why the interior roots matter. One cell: the gap is plus two times ten to the minus six at both nodes, with slopes minus and plus 0.002. The cubic is two times ten to the minus six, times one minus 10 t plus 10 t squared. Its slope vanishes in the middle, where the gap is minus three times ten to the minus six. Both nodes pass, the cell fails: a check at the nodes alone would accept it.

Last row, the tail order: with common tail exponents, each far tail scale must be at least the near one, so the far law never has a lighter tail. It is reported and advisory by default; the Tail-order gate option makes it block. Policy overall: a failed certificate takes the node out of 'ready' and blocks Publish, and the Quality card names the gap in bp and its strike.

**Transition:** that completes the parametric surface. Next, local volatility, where calendar order holds by construction and the work is in the fit itself.

**If asked why the exchange uses ledger rows when the screen uses prices:** a floor on the whole ledger drags a fit by its unquoted tails, because the ledger at one rank integrates everything above it. That is why the screen and the repair work at quoted strikes. The exchange adds a ledger row only at the few ranks the certificate rejects.

**Illustrative calculation.** One cell, $h = 0.01$: gap $2\times10^{-6}$ at both nodes, slopes $\mp 0.002$. The cubic is $\Delta\hat G = 2\cdot10^{-6}\,(1 - 10t + 10t^2)$; its slope vanishes at $t = 1/2$, where $\Delta\hat G = -3\times10^{-6}$. Both nodes pass the $-10^{-6}$ tolerance; the cell fails.

**In the app.** Quality lens ▸ node card: Cal viol shows the screen and the certificate's ledger gap; Tail order reads the tail clause; a failed certificate blocks Publish.

**Sources.** [generalized_tails_calendar_roadmap.md](../../Docs/generalized_tails_calendar_roadmap.md); [10_calendar_unnamed_martingale.md](../../Docs/handoff/notes/10_calendar_unnamed_martingale.md); [calendar_certificate.py](../../backend/volfit/calib/calendar_certificate.py); [symmetric.py](../../backend/volfit/calib/symmetric.py); [symmetric_exchange.py](../../backend/volfit/calib/symmetric_exchange.py); [interp.py](../../backend/volfit/models/lqd/interp.py); [quality_gates.py](../../backend/volfit/api/quality_gates.py); [export_blockers.py](../../backend/volfit/api/export_blockers.py); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-25"></a>

## 25. A piecewise-affine local-variance surface

*4 · Local-volatility calibration*

The local-volatility fit has one unknown per vertex of a strike–time grid: the local variance there. Between vertices the surface is affine on triangles, so positive vertices give a positive surface.

*1 · One unknown per vertex, one hat function per unknown*

$$
\nu_\theta(\tau,x)=\textstyle\sum_{\ell=1}^{m}\theta_\ell\,\phi_\ell(\tau,x),\qquad \theta_\ell=\nu_\theta(\tau_\ell,x_\ell)
$$

*2 · Inside a triangle: an average of its three corners*

$$
\nu_\theta(\tau,x)=b_1\,\theta_{\ell_1}+b_2\,\theta_{\ell_2}+b_3\,\theta_{\ell_3},\qquad b_a\ge 0,\quad b_1+b_2+b_3=1
$$

*3 · So a box on the vertices is a box on the whole surface*

$$
\nu_{\mathrm{lo}}\le\theta_\ell\le\nu_{\mathrm{hi}}\ \ \text{for every }\ell\quad\Longrightarrow\quad \nu_{\mathrm{lo}}\le\nu_\theta(\tau,x)\le\nu_{\mathrm{hi}}
$$

This section changes the object. Until now each expiry had its own smile model. Local volatility describes the whole surface with one diffusion: the forward-normalised price moves with an instantaneous variance nu that depends on where it is, x, and when, tau. x is the normalised strike, K over F. tau is the variance clock: calendar time plus any event days, and equal to calendar time when no events are set. Nu is a variance, local vol squared.

Line one. The unknowns are a finite list of numbers, theta-ell, one per vertex of a grid in time and strike: theta-ell is the local variance at vertex ell. Between vertices the surface is built from hat functions: phi-ell equals one at its own vertex, zero at every other vertex, and is affine on each triangle. The grid is a tensor product, n-tau time rows by n-x strike columns, and each rectangle is cut into two triangles. The QQQ sheet in the capture has 11 time rows and 28 strike columns: 308 numbers describe the whole surface. The chart labels its time axis T; it is the variance clock tau.

Line two is the key property. A point inside a triangle takes the weighted average of the triangle's three corner values, with barycentric weights b: nonnegative, summing to one. An average cannot leave the range of what it averages. The strip: weights one half, 0.3 and 0.2 on corners at 20, 30 and 25 percent local vol give a variance of 0.0595, a local vol of 24.4 percent. Variances are averaged, not vols.

Line three follows at once: bounds on the vertices are bounds on the whole surface inside the grid. So positivity, the condition that makes the diffusion exist and its prices free of arbitrage, is a box on each unknown, which a least-squares solver handles directly, with no penalty. The cap is 60 percent vol, or three times the highest quoted implied vol if that is larger, and never above 400 percent. The floor is 5 percent vol, lowered to half the lowest at-the-money implied vol when that is smaller.

Why the floor may sit below every implied vol. An option's implied variance is an average of local variance along the paths to its expiry; at the money, roughly, the implied variance to tau is the time average of the local variance at the money up to tau. When the term structure rises, the early local variance must sit below the shortest implied variance. The same fact is the first bullet: a vertex value is not the implied vol of an option at that point. It is read through the pricing equation, which is the next slide.

Where the vertices go. Time rows sit at zero, at a quarter of the first expiry and at every expiry, then the widest gaps, measured in square-root time, are split until there are at least ten rows after zero. Strike columns come from a delta axis: the 1, 2, 5, 10, 25 and 40 delta points of each side plus the money, scaled by the longest expiry and clipped to the quoted range. There are at least twelve, and at least eight inside each expiry's own quoted range. That last rule exists because a six-day weekly once caught only three vertices on its smile and fitted at 108 bp; with eight it came down to about 28.

Outside the grid. To the right, the local variance is held flat at its last column. To the left it is flat by default. With the Convex wing option it continues linearly at 1.5 times the slope of the first cell, and with a variance-swap quote that multiple becomes a fitted parameter between 0 and 20. There the averaging argument no longer holds, so a falling continuation could turn negative; the march floors it at zero.

**Transition:** next, how a sheet of local variance becomes option prices: the forward Dupire march.

**If asked why triangles rather than bilinear cells:** on a triangle the interpolant is exactly affine and is fixed by its three corners, which also works on vertex sets that are not rectangular. Bilinear cells keep the averaging property but add a cross term. The diagonal of each rectangle comes from the triangulation library's tie-break, and the viewer draws the triangulation the pricing uses.

**If asked why the unknown is a variance rather than a vol:** the pricing equation is linear in the local variance, so the derivative of the operator with respect to one vertex is exact and cheap, which slide 27 uses; and averaging variances is what keeps the positivity argument.

**If asked whether the sheet is unique:** no. Prices average local variance, so different sheets can reprice the same quotes. Note 04 shows two sheets 22 vol points apart in the unquoted deep-put wing that reprice the same quotes within 1.6 vol bp. The regularisation of slide 27 chooses one.

**Worked example.** Weights 0.5, 0.3, 0.2 on corners at 20%, 30%, 25% local vol: $\nu = 0.5(0.04) + 0.3(0.09) + 0.2(0.0625) = 0.0595$, a local vol of 24.4%. Variances are averaged, not vols, and the result stays between 20% and 30%.

**Visual.** 24 September capture of the fitted QQQ sheet: $11 \times 28$ vertices, time rows by strike columns. Each facet is a triangle on which $\nu$ is affine; height and colour give the local variance, $0.0025$ to $1.44$. STALE refers to the saved snapshot.

**In the app.** Local Vol lens (Alt+4) ▸ LV surface: rotate the mesh. Options ▸ Local-Vol surface: the resolved grid $n_\tau \times n_x = m$ and the box.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [04_local_volatility_forward.md](../../Docs/handoff/notes/04_local_volatility_forward.md); [affine_surface.py](../../backend/volfit/models/localvol/affine_surface.py); [affine_fit.py](../../backend/volfit/api/affine_fit.py); [schemas.py](../../backend/volfit/api/schemas.py); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-26"></a>

## 26. The forward Dupire pricing calculation

*4 · Local-volatility calibration*

Given a local-variance sheet, one forward march prices every strike and every expiry: start from the payoff and step forward in time, one tridiagonal solve per step.

*1 · Forward Dupire equation, started from the payoff*

$$
\partial_\tau c=\tfrac12\,\nu(\tau,x)\,x^2\,\partial_{xx}c,\qquad c(0,x)=(1-x)^+
$$

*2 · Three-point stencil: row $i$ of the matrix $A$*

$$
(AU)_i=\nu_i\bigl[\,a_i^-U_{i-1}-(a_i^-+a_i^+)\,U_i+a_i^+U_{i+1}\bigr]
$$

*3 · One BDF2 step: a single tridiagonal solve*

$$
\bigl(I-\gamma_n\Delta\tau_n A^{n+1}\bigr)\,U^{n+1}=\alpha_n U^n-\beta_n U^{n-1}
$$

*4 · Step weights from the step ratio $\omega_n = \Delta\tau_n/\Delta\tau_{n-1}$*

$$
\gamma_n=\frac{1+\omega_n}{1+2\omega_n},\qquad \alpha_n=\frac{(1+\omega_n)^2}{1+2\omega_n},\qquad \beta_n=\frac{\omega_n^2}{1+2\omega_n}
$$

| Symbol | Meaning |
| --- | --- |
| $c,\ \nu$ | Call over $DF$, carry inside $F$ and $D$; local variance, the sheet of the previous slide |
| $\tau$ | Variance time (slide 29): calendar time plus event days; $t$ itself with no events |
| $x_i,\ h_i^\pm$ | Lattice node $i$; widths of the cells below ($h_i^-$) and above ($h_i^+$) it |
| $\nu_i,\ a_i^\pm$ | $\nu(\tau_{n+1}, x_i)$; stencil weights $x_i^2/\bigl((h_i^-+h_i^+)\,h_i^\pm\bigr)$, the $\tfrac12$ folded in |
| $U^n$ | Call values on the lattice at time level $\tau_n$ |
| $\Delta\tau_n,\ \omega_n$ | Step $\tau_{n+1}-\tau_n$; its ratio to the previous step |
| $\gamma_n,\ \alpha_n,\ \beta_n$ | Step weights: implicit Euler $(1, 1, 0)$; constant-step BDF2 $(\tfrac23, \tfrac43, \tfrac13)$ |

Line one, the forward Dupire equation. c is the call price divided by D times F, as a function of the normalised strike x, K over F, and of the variance time tau. Rates, dividends and borrow sit inside F and D, so they do not appear. The equation says: the call gains value with maturity at a rate equal to one half the local variance, times x squared, times the convexity of the call in strike, and that convexity is the risk-neutral density. It starts from the payoff, one minus x floored at zero. At x equal zero the call is worth the whole forward, one; at the far edge, x-max, it is worth zero. x-max is 1.4 times the highest quoted strike, and at least 2.5. Why forward: the Black–Scholes equation runs backward from one option's payoff, one solve per option. Dupire's runs forward in maturity with strike as the space variable, so one march produces the whole call surface, and every quote of every expiry is read off the same solution.

Line two, space. On the strike lattice the second derivative at node i uses node i and its two neighbours only. With h-minus and h-plus the widths of the cells below and above the node, the weights a-minus and a-plus are x_i squared over the sum of the two widths times the width on that side; the one half of the equation is already folded in. Multiply by the local variance at the node, taken at the new time level, and you have row i of the matrix A. Three entries per row: A is tridiagonal.

Line three, time: this is BDF2. BDF stands for backward differentiation formula, and 2 is its order. Take the two last known time levels and the unknown new one, draw the parabola through the three in time, and use its slope at the new time as the time derivative. Set that slope equal to A times the new level. At a constant step it reads: three U-new minus four U-now plus U-previous, over two delta-tau, equals A U-new. Rearranged, that is line three with gamma two thirds, alpha four thirds and beta one third. Line four gives the weights when the step length changes, through the ratio omega of this step to the last one. Alpha minus beta is always one, so a flat price stays flat.

What it buys. Implicit Euler, the legacy scheme, is first order: halve the step and you halve the error. BDF2 is second order: halve the step and you quarter it. And it is L-stable: the stiffest modes, the jagged strike-scale components the payoff kink injects, are damped to zero, where Crank–Nicolson lets them flip sign at every step instead of dying; that ringing, with negative densities, was recorded on coarse strike grids. BDF2 needs two past levels, so its first step is implicit Euler; so is any step more than twice the previous one, because variable-step BDF2 is only stable for growth below one plus root two. The graded grid never grows by more than 25 percent, so from step two on every step is BDF2.

The grids. In time: the payoff kink makes the at-the-money price grow like the square root of tau, so near zero the natural time scale is tau itself. Steps start at one percent of the first grid mark and grow geometrically by at most 25 percent, capped at 0.05 years, with at least eight steps between marks; every expiry and every vertex row is a mark, because the local variance has a kink in time at each row. In strike: each expiry gets its own step, 0.15 of its at-the-money standard deviation, out to six standard deviations; the wings step 0.02; the step changes by at most 15 percent per cell, and x equal one is always a node. For a two-day front at 15 percent vol that is a step of about one six-hundredth between 0.94 and 1.07.

Positivity. The left-hand matrix is an M-matrix: positive diagonal, non-positive off-diagonals, diagonally dominant. So the solve needs no pivoting, and its inverse has no negative entry. The minus-beta term on the right means that alone does not prove the full two-level update keeps the density positive, so every fit measures it: the smallest second difference per expiry, calendar order and price bounds are checked on the output.

The strip. A flat 15 percent sheet has a known answer: 15 percent at every strike. Marched over the SPY ladder of 23 September, two to 359 days, the graded grid has 115 steps, the first one seven minutes long. Implicit Euler misses the at-the-money vol by 16 bp at two days and by 5 to 12 bp further out. BDF2 misses by 3.2 bp at two days, which is the strike lattice's share, and by at most 0.3 bp elsewhere. On fitted surfaces the recorded figure is at most about 5 bp per expiry for BDF2, where the old implicit rule left 15 to 170 bp for the fit to absorb.

**Transition:** the fit must now choose the sheet. Next, how the calibration differentiates this march, and why that stays cheap.

**If asked what BDF2 is, in one sentence:** an implicit two-step method that takes the time derivative from a parabola through the last three levels; second order like Crank–Nicolson, but it damps the stiff modes like implicit Euler.

**If asked why not Crank–Nicolson:** it is second order but not L-stable, since its amplification tends to minus one on the stiffest modes, so the payoff kink rings; and its sensitivity step costs more, up to about twice, because it also applies the operator to the old level. It stays available as Rannacher, Crank–Nicolson after two implicit start-up steps, as an option.

**If asked how big the lattice is:** for the SPY ladder of 23 September, 368 strike nodes and 116 time levels. The old uniform lattice took the shortest expiry's step everywhere: on a SPY surface with a two-day expiry, about 1,700 strike nodes where the graded one needs about 400.

**Worked numbers.** A flat 15% sheet, whose exact price is known, marched over the SPY ladder of 23 September (2 to 359 days): 115 graded steps, the first 7 minutes long. ATM vol error: implicit Euler 16 bp at 2 days, 5 to 12 bp further out; BDF2 3.2 bp at 2 days, at most 0.3 bp further out.

**In the app.** Options ▸ Local-Vol surface: the Time stepping selector (BDF2 by default, Rannacher, Implicit Euler legacy) and the Graded strike lattice toggle.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [04_local_volatility_forward.md](../../Docs/handoff/notes/04_local_volatility_forward.md); [time_schemes.py](../../backend/volfit/models/localvol/time_schemes.py); [affine_dupire.py](../../backend/volfit/models/localvol/affine_dupire.py); [pde_grids.py](../../backend/volfit/models/localvol/pde_grids.py); [affine_lattice.py](../../backend/volfit/api/affine_lattice.py); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-27"></a>

## 27. Calibrating through the PDE

*4 · Local-volatility calibration*

The fit chooses the vertex values $\theta$ by damped Gauss–Newton. The derivatives it needs come out of the same march as the prices, through the same tridiagonal matrix.

*1 · Quote residual: the price miss over vega, in vol points*

$$
r_i(\theta)=\frac{c_i(\theta)-c_i}{0.01\,v_i}
$$

*2 · Objective: weighted misses plus three penalties, minimised over the box $\nu_{\mathrm{lo}} \le \theta \le \nu_{\mathrm{hi}}$*

$$
\Phi(\theta)=\textstyle\sum_i\lambda_i\,r_i^2+\kappa_R\,\|\delta^2\theta\|^2+\kappa_D\,\|\delta_x^3c\|^2+\kappa_F\,\|\theta_{0,\cdot}-\theta_{1,\cdot}\|^2
$$

*3 · Sensitivities $S_\ell = \partial U/\partial\theta_\ell$: the same matrix, one more right-hand side each*

$$
\bigl(I-\gamma\Delta\tau A^{n+1}\bigr)S_\ell^{n+1}=\alpha S_\ell^{n}-\beta S_\ell^{n-1}+\gamma\Delta\tau\,A_\ell^{n+1}U^{n+1}
$$

*4 · Levenberg–Marquardt step on the stacked residuals $r$, with $\|r\|^2 = \Phi$, clipped to the box*

$$
\bigl(J^{\top}J+\mu\,\mathrm{diag}(J^{\top}J)\bigr)\,\Delta\theta=-J^{\top}r,\qquad \theta\leftarrow\clip(\theta+\Delta\theta)
$$

| Symbol | Meaning |
| --- | --- |
| $c_i(\theta),\ c_i$ | Model call at quote $i$, read off the march; the market mid. Both over $DF$ |
| $v_i,\ \lambda_i$ | Black vega of the quote, floored at $10^{-3}$; quote weight. A 1-point vol miss gives $r_i \approx 1$ |
| $\delta^2\theta$ | Second differences of neighbouring vertices along strike and along time, spacing-aware: $\theta_{j-1}-2\theta_j+\theta_{j+1}$ on an even grid |
| $\delta_x^3 c$ | Third differences of each expiry's marched call, the slope of the density $\partial_{xx}c$, over the quoted range $\pm2$ ATM std |
| $\theta_{0,\cdot},\ \theta_{1,\cdot}$ | Vertex rows at $\tau = 0$ and the next one; before a front under 0.08 y, every row up to it, at weight at least 1 |
| $\kappa_R,\ \kappa_D,\ \kappa_F$ | Penalty weights, by default $10^{-2}$, $1$, $10^{-2}$ (Options: Roughness, Density smoothness, Front-tie weight) |
| $A_\ell$ | $\partial A/\partial\theta_\ell$: $A$ with $\nu_i$ replaced by $\phi_\ell(\tau_{n+1}, x_i)$; $\gamma, \alpha, \beta$ as on slide 26 |
| $J,\ \mu$ | Jacobian of all rows of $r$, built from the $S_\ell$; damping, $10^{-3}$ at the start |

This slide fits the sheet: choose the m vertex variances theta so that the marched prices meet the quotes. Line one, the quote residual. c_i of theta is the model call at quote i, read off the march; c_i alone is the market mid, both divided by D times F. The miss is divided by 0.01 times the quote's Black vega, v_i, floored at ten to the minus three. So the residual reads in vol points: a one-point miss gives about one, a one-basis-point miss a hundredth. In bid–ask and haircut modes the band residual of slide 11 takes its place, with the same weak mid anchor.

Line two, the objective: the squared misses weighted by the quote weights lambda-i, plus three penalties, over the box of slide 25. Kappa-R times the curvature of the sheet: delta-two theta is the second difference of neighbouring vertices, along strike within a time row and along time within a strike column, each scaled by the local spacing, so that on an even grid it is theta-left minus two theta plus theta-right. Kappa-D times the roughness of the density: delta-three c is the third difference of each expiry's marched call, which is the slope of the density, over its quoted range widened by two at-the-money standard deviations, and scaled so that a smooth bell costs about 0.14 kappa-D whatever the maturity. Kappa-F times the front tie, which pulls the rows before the first expiry toward it. Defaults: 0.01, 1 and 0.01.

Why regularise at all. Prices are averages of local variance along the diffusion's paths, so the data leave some directions almost free: 253 unknowns against quotes packed near the money of nine expiries. Before the first expiry the quotes pin only the average of the local variance, not its shape; beyond the quoted wings they pin almost nothing. Note 04 shows two sheets, 22 vol points apart in the unquoted put wing, that reprice the same quotes within 1.6 vol bp. The penalties choose one member of that family: the least curved sheet, the smoothest density, and a front that continues the first expiry. When the first expiry is under a month the front tie is chained over every early row at weight one; untied, those rows were measured ringing by 5 to 30 vol points.

How much they weigh. A one-bp miss costs ten to the minus four. A kink of 0.01 in variance between neighbouring vertices costs ten to the minus six. So the curvature penalty decides where the quotes are silent and yields where they speak. The density rows aim at what the quotes cannot see: vertex-scale ringing that shows up as spikes in the density. On the SPY weekly fixture they cut the finer-lattice RMS from 20.2 to 18.5 bp and the evaluations from 62 to 43.

Line three, the derivatives. Differentiate the step of slide 26 with respect to one vertex, theta-ell. The left-hand matrix does not change. On the right, the previous sensitivities combine exactly like the prices, plus a source: A-ell times the new prices, where A-ell is the stencil with the local variance replaced by the hat function of vertex ell. That is exact, because the equation is linear in nu. Read it as: vertex ell moves prices only where the diffusion passes through its triangles, in proportion to the convexity it meets there.

Why a tridiagonal matrix, and why it matters. The second derivative at node i uses only nodes i minus one, i and i plus one, so each row has three entries. Such a system is solved by one forward sweep and one back substitution, the Thomas algorithm, in a few operations per node; and because this matrix is an M-matrix, no pivoting is needed. Factor it once per step and reuse it for the price and for all 253 sensitivity columns. The compiled kernel keeps the columns as its inner loop, so the processor works on several columns per instruction.

Line four, the optimiser. Gauss–Newton replaces the residuals near theta by their linearisation, r plus J delta-theta, and solves that linear least-squares problem; J is the Jacobian of every residual row, built from the sensitivities. Levenberg–Marquardt adds the damping mu, scaled by the diagonal of J-transpose-J: small mu gives the Gauss–Newton step, large mu a short step down the scaled gradient. A trial is kept if the objective falls; mu shrinks after a good step and grows after a rejected one. The step is clipped to the box; in band modes the clipped vertices are pinned and the rest re-solved. The linear system is solved by LSMR, an iterative least-squares method that needs only the products J v and J-transpose w: no J-transpose-J, no dense decomposition. The fit stops at convergence, at 200 evaluations, or when the quote misfit has not improved by 0.3 percent in 18 evaluations, 12 in band modes, and returns the best accepted point. Fits with a variance-swap quote use scipy's trust-region solver instead.

The computational picture, the strip. SPY on 23 September: 875 quotes, 253 vertices, a lattice of 368 strikes by 115 steps. One evaluation marches the price and up to 253 sensitivity columns: 115 steps times 366 interior nodes times 253 columns is about 10.6 million node updates, behind one factorisation per step. A column stays zero until the march reaches its vertex's rows, so fewer are live on average. Measured today on a synthetic surface of that size, one such march takes about 17 milliseconds on this laptop. The recorded cold fit took 66 evaluations and 2.8 seconds; warm-started from the previous fit, 20 evaluations and 0.9 seconds. Total time is the cost of one evaluation times the number of evaluations, and every speed-up attacked one of the two: the compiled march and the graded grids for the first; the Dupire seed of a cold fit, the warm start and the early stop for the second.

**Transition:** last slide of the section: the fitted sheet beside the local variance read directly off the parametric smiles.

**If asked why a tridiagonal matrix:** the equation has one space dimension and its second derivative is approximated by a three-point stencil, so each unknown couples only to its two neighbours. That makes each step linear in the number of nodes and lets one factorisation serve the price and every sensitivity.

**If asked what Gauss–Newton and Levenberg–Marquardt are:** Gauss–Newton is Newton's method for least squares with the second derivatives of the residuals dropped, the Hessian replaced by J-transpose-J. Levenberg–Marquardt adds a damping term that blends it with gradient descent and adapts from step to step: full steps near the answer, cautious ones far from it. We use forward sensitivities rather than an adjoint because Gauss–Newton needs the whole Jacobian of 875 quote rows, not the gradient of one number.

**Recorded SPY · 23 September.** 875 quotes, $m = 253$ vertices, lattice 368 strikes by 115 steps. One evaluation marches the price and up to 253 columns $S_\ell$: $115 \times 366 \times 253 \approx 10.6$ million node updates behind one factorisation per step. Cold fit: 66 evaluations, 2.8 s. Warm-started from the last fit: 20 evaluations, 0.9 s.

**In the app.** Local Vol aside ▸ Fit diagnostics: per-expiry errors, N PDE solves · price rms, and the ⏵ calibration-trace player.

**Sources.** [localvol_calibration_methodology.md](../../Docs/localvol_calibration_methodology.md); [04_local_volatility_forward.md](../../Docs/handoff/notes/04_local_volatility_forward.md); [affine_calib.py](../../backend/volfit/models/localvol/affine_calib.py); [affine_gn.py](../../backend/volfit/models/localvol/affine_gn.py); [affine_fit.py](../../backend/volfit/api/affine_fit.py); [schemas.py](../../backend/volfit/api/schemas.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-28"></a>

## 28. Fitted local variance and the Dupire-derived surface

*4 · Local-volatility calibration*

The Compare tab reads a local variance off the parametric smiles the classical way, differentiate then divide, and scores it beside the fitted sheet on the same quotes.

*1 · Dupire twin: differentiate the parametric surface, then divide*

$$
\nu_{\mathrm{twin}}(\tau,x)=\frac{\partial_\tau c}{\tfrac12\,x^2\,\partial_{xx}c}=\frac{\partial_\tau w}{g(k,w)},\qquad k=\log x
$$

*2 · Round trip: reprice the twin, compare it with its own source at the quoted $k_i$*

$$
\mathrm{RT}=\operatorname{rms}_i\,\bigl|\,\sigma_{\mathrm{twin}}(k_i)-\sigma_{\mathrm{param}}(k_i)\bigr|
$$

Slides 25 to 27 read Dupire's equation forward: choose a local variance, march the prices, match the quotes. The Compare tab reads it the classical way, backward: take the parametric smiles already fitted, differentiate them, and divide. We call the result the Dupire twin, and the tab sets it beside the fitted sheet.

Line one. In our coordinates it is the equation of slide 26 solved for nu: the time derivative of the call over one half x squared times its second strike derivative. The numerator is a calendar spread, the denominator a butterfly, that is, the density. In total variance it is Gatheral's formula: the time derivative of w over the butterfly function g. The app builds w from the displayed parametric fits at the spot they were calibrated at. Between expiries it interpolates in tau, through w equal zero at tau zero, with a monotone cubic, the Smooth chip, or linearly, the Buckets chip. The Tails chips set the twin beyond each expiry's quoted range: the model's own wings by default, held flat from the quoted edge, or the fitted sheet. It differentiates by finite differences and counts every repair: a cell with g at or below zero is a butterfly arbitrage of the parametric surface itself, a cell with falling w a calendar arbitrage; floored and capped cells are counted too.

Why this direction is delicate. Differentiation amplifies noise, twice in strike and once in time, and the denominator is a density, small in the wings. Starting from smooth parametric smiles keeps it usable, but the twin inherits every choice of that surface: its interpolation in time, its tails, any arbitrage it carries.

The twin is then repriced through the same forward equation, on the fit's own lattice made four times finer in strike and eight times finer in time, with a second-order scheme. Line two, the round trip: the RMS gap between the twin's repriced vols and its own parametric source, at the quoted strikes. If differentiation and repricing were exact it would be zero.

Two controls sit beside it. Floor: a flat sheet at the ladder's median implied variance, marched on the same operator. Its exact answer is known, so its error is the operator's own, and no round trip can be read below it. Sheet: the twin sampled only at the fit's vertices, interpolated on triangles like the fitted sheet, and repriced.

The capture: QQQ, 18 December expiry, haircut target. The three curves sit on top of each other. The row reads parametric 2 bp, twin 4, affine sheet 2, and 8 on the finer lattice; round trip 0.3 bp over a floor of 0.1. The telling number is the last one: the smooth twin, sampled at the vertices, reprices 71 bp away from its source. So the vertex values of a good sheet are not samples of the true local variance; they are the values that make the triangulated sheet price right. That is what the direct fit of slide 27 solves for, and why it exists.

The affine columns. rms is measured on the lattice the fit used; conv reprices the same sheet on a lattice twice as fine in strike and four times as fine in time. The SPY record of 23 September: 3.61 vol bp on the fit's lattice, 5.12 on the finer one, 24.8 at the worst quote. Why show both: an optimiser facing a fixed lattice can bend theta to cancel that lattice's own error, so its own residual flatters it; only another lattice exposes that part.

Two practical points. The comparison is anchored at the calibration spot, so a spot tick does not rebuild the twin. And the Sheets and Difference views need the displayed fit on the same vertex grid as the twin; in the capture it was not, so the difference was withheld until the next Calibrate.

**Transition:** that closes local volatility. The next section is about time itself: the event-weighted variance clock tau that every equation here has run on.

**If asked why not use the twin as the local-volatility surface:** it inherits the interpolation and the tails of the parametric surface, it needs repairs wherever that surface carries arbitrage, and its vertex samples reprice poorly. It is a diagnostic. A cold fit does start from the same classical reading, as a starting point only.

**If asked whether the finer-lattice number is exact:** no. It is the same sheet on a finer lattice, marched with implicit Euler steps; on a flat 15 percent sheet over the SPY ladder that reprice itself reads 1 to 4 bp at the money. The gap between the two numbers signals discretisation; it is not the exact error.

**Recorded SPY · 23 September.** Nine expiries, 875 quotes, 253 vertices: 3.61 vol bp RMS on the fit's own lattice, 5.12 bp repriced on the finer one, 24.8 bp worst quote. Quote both: a fit can absorb its own lattice's error into $\theta$, and only another lattice shows it.

**Visual.** 24 September capture, QQQ 18-Dec-26, haircut target: affine sheet (blue), parametric source (green), Dupire twin (orange, dashed). Its row reads parametric 2, twin 4, affine 2 (conv 8) bp; round trip 0.3 bp over a floor of 0.1, while the twin sampled at the vertices reprices 71 bp away.

**In the app.** Local Vol ▸ Compare ▸ Smiles: the three curves on the quotes and the per-expiry score table. The Time and Tails chips rebuild the twin; Sheets and Difference set the two surfaces on one vertex grid.

**Sources.** [lv_compare.py](../../backend/volfit/api/lv_compare.py); [dupire_twin.py](../../backend/volfit/models/localvol/dupire_twin.py); [dupire_surface.py](../../backend/volfit/models/localvol/dupire_surface.py); [reprice.py](../../backend/volfit/models/localvol/reprice.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-29"></a>

## 29. Event-weighted variance time

*5 · Time, spot and stored information*

A price fixes total variance $w$; a volatility is $w$ divided by a clock. The event clock counts a scheduled event as extra days, so the same price reads a lower volatility.

*1 · Variance clock: each event before expiry adds $N_e$ days*

$$
\tau(t)=t+\frac{1}{365}\sum_{t_e\le t}N_e
$$

*2 · Two readings of one price*

$$
w=\sigma_{\mathrm{cal}}^2\,t=\sigma_{\mathrm{evt}}^2\,\tau\quad\Longrightarrow\quad \sigma_{\mathrm{cal}}=\sigma_{\mathrm{evt}}\sqrt{\tau/t}
$$

*3 · Optional normalisation: a one-year expiry keeps a one-year clock*

$$
\tau_{\mathrm{norm}}(t)=\tau(t)\,\frac{365}{365+\sum_{t_e\le 1}N_e}
$$

An option price fixes one number: the total variance w, the variance of the log-return to expiry. A volatility is w divided by a length of time. The question on this slide is which length of time.

Line one is the variance clock. Tau of t is calendar time, plus, for every scheduled event on or before the expiry, N-e extra days divided by 365. N-e is in days, never years: an earnings day with N-e equal to four counts as five ordinary days. An event after the expiry adds nothing. With an empty calendar tau equals t exactly, and every fit is identical to the calendar-time pipeline.

Line two: two readings of the same price. W divided by t is the calendar volatility; w divided by tau is the event-clock volatility. Once an event sits inside the horizon, tau is larger than t, so the event-clock reading is lower, by the factor root t over tau. The event-clock reading is the working one: every fit, the term view, the option table and the 3-D surface read tau.

Why bother: measured in variance days, the diffusion looks steady again. The short-dated volatility that looks too high before earnings is the same total variance divided by too short a time. The figure shows it: flat 20 percent on the event clock; on the calendar clock the same prices jump when the expiry crosses the event, then decay as the event becomes a smaller share of a longer horizon.

The strip, worked through. Event on day 30, worth five extra days, 20 percent on the event clock. A 30-day expiry has tau of 35 over 365; total variance 0.04 times 35 over 365, 0.00384. Divide by 30 over 365 instead and the calendar reading is 20 percent times root 35 over 30: 21.60. At 60 days, 20.82; at 90 days, 20.55.

The vol crush, read on both clocks. Once the event date has passed, its extra days are no longer ahead of the expiry. On the event clock nothing changes: 20 percent before, 20 percent after. On the calendar clock the reading falls from 21.60 toward 20: the event's variance has been delivered, and the calendar reading had been spreading it over the whole horizon.

Line three is optional and off by default. Unnormalised, events add variance to the year. Normalised, every day, event days included, is scaled by one factor so that a one-year expiry reads exactly as with no events: events redistribute the year's variance instead of adding to it. With the day-30 event the factor is 365 over 370, and the same prices read 20.14 percent at every expiry.

What stays on calendar time: carry, discounting and the de-Americanisation tree all run on t. Only the volatility read-off, and every fit that works in volatility or variance per unit time, uses tau.

**Transition:** typing N-e by hand needs the date and the size of each event. The next slide reads both off the term structure.

**If asked whether switching the clock changes the fit:** re-reading a stored fit on another clock is exact. Changing the calendar refits the ticker, and a refit is a new calibration: the vega in the residual scales with root tau while the penalties and the vega floor do not, so the result can differ from a pure relabelling. Compare the display change and the refit separately.

**If asked about intraday events:** with the intraday clock on, off by default, maturity runs to the settlement instant and each day accrues through a session-weighted profile. An event date is a year fraction, so an 8:30 CPI print is a fractional event date and line one applies unchanged.

**Worked example.** Event on day 30 worth $N_e = 5$, 20% on the event clock. 30-day expiry: $\tau = 35/365$, $w = 0.04 \times 35/365 = 0.00384$, calendar reading $20\% \times \sqrt{35/30} = 21.60\%$. At 60 and 90 days: 20.82% and 20.55%. Normalised: every $\tau$ is multiplied by $365/370$, and the same prices read 20.14% at every expiry.

**Visual.** Same prices, two clocks: the event-clock reading is flat at 20%; the calendar reading jumps to 21.60% when expiry crosses the day-30 event, then decays as the event becomes a smaller share of the horizon.

**In the app.** Parametric ▸ Term: the Events card (date in years, extra days). The chart draws the event-clock reading and, dashed amber, the calendar reading of the same prices. Options ▸ Events and Normalize events.

**Sources.** [11_event_market_clock.md](../../Docs/handoff/notes/11_event_market_clock.md); [weighted_time.py](../../backend/volfit/calib/weighted_time.py); [quotes.py](../../backend/volfit/api/quotes.py); [service.py](../../backend/volfit/api/service.py); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-30"></a>

## 30. Auto-calibrating isolated variance peaks

*5 · Time, spot and stored information*

Prices fix the forward variance between consecutive expiries. An interval that runs hotter than both neighbours is read as one event, sized exactly to remove the excess; every other shape installs nothing.

*1 · Forward variance per calendar year: fixed by prices*

$$
f_i=\frac{w_i-w_{i-1}}{t_i-t_{i-1}}
$$

*2 · Reference: the hotter neighbour, read on the event clock*

$$
r_i=\max\bigl(f^{\tau}_{i-1},\,f^{\tau}_{i+1}\bigr),\qquad f^{\tau}_j=\frac{w_j-w_{j-1}}{\tau_j-\tau_{j-1}}
$$

*3 · Event size: the extra days that bring $f_i$ down to $r_i$*

$$
N_i=d_i\left(\frac{f_i}{r_i}-1\right)
$$

*4 · Materiality: both floors, or no event*

$$
N_i\;\ge\;\max\bigl(0.5,\ 0.03\,d_i\bigr)\ \text{days}
$$

| Interval (days) | ATM vol at its end, calendar | Forward vol $\sqrt{f_i}$ | Found $N_i$ |
| --- | --- | --- | --- |
| 0–30 | 20.00% | 20.00% | 0 |
| 30–60 | 20.66% | 21.29% | 4.0 days, at day 45 |
| 60–90 | 20.44% | 20.00% | 0 |
| 90–120 | 20.33% | 20.00% | reference only |

The previous slide took the event calendar as given. This one reads it off the market. The input is the at-the-money total variance of each calibrated expiry, taken from each slice's LQD backbone.

Line one: the forward variance of each interval between expiries, per calendar year. Prices fix it, so no calendar can change it. What carries the information is how uneven this ladder is.

The key fact is a sign. An event inside an interval adds days to that interval on the event clock, which lowers that interval's event-clock forward variance and leaves every other interval alone. So the only shape an event can create is a peak: an interval running hotter than both neighbours. A rising ramp, a smooth decline, a dip: no event produces those, so the rule installs nothing for them. It is a detector, not a smoother.

Lines two and three. The reference is the hotter of the two neighbours, read on the event clock, so it includes any event already found there. Ask for the extra days that make this interval run exactly at its reference: delta-w over d-i plus N-i days equals r-i. That solves to line three: the size is exact, with no penalty shrinking it. Clipping one peak can lower a neighbour's reference, so the rule repeats until no peak is left. It converges to the smallest events that leave no peak, in at most one pass per interval: microseconds.

Line four, materiality: an event must add at least half a day, and at least 3 percent of the interval's days. On a monthly interval the second floor binds, 0.9 day. Fit noise between adjacent expiries sits below both floors; an earnings day sits far above.

The table. A monthly ladder at 20 percent on the event clock, with earnings worth four extra days inside the second month. On the calendar clock the ATM vols read 20.00, 20.66, 20.44, 20.33: the familiar hump. The forward vols read 20, 21.29, 20, 20. The second interval is hotter than both neighbours: N equals 30 times 0.04533 over 0.04 minus one, 4.0 days, placed at day 45, the midpoint. After installing it the event-clock ladder is flat, and the Ladder spread readout goes from 53 variance bp to zero.

The two ends. The last interval has no right neighbour, so it is never a candidate: it is the reference for the tail, whatever horizon you choose. The first has no left neighbour: its reference is the second interval, extended one step by the back ladder's own slope when that ladder is falling, so a volatility spike that decays smoothly is not read as an event.

Placement is a convention. Prices only see the total variance at each listed expiry, so they cannot tell Tuesday from Thursday inside one interval, nor two events from one event of their combined size. The midpoint is a default; the date is yours to edit.

On real data, the 18 July AAPL export with four expiries: one event of 3.8 days in the September to December interval, which contains the late-October earnings, and nothing elsewhere. The ladder spread fell from 127 to 106 variance bp. On SPY it installs nothing.

**Transition:** the clock handles time. Next: what happens to a stored fit when spot moves between calibrations.

**If asked why not fit a smooth clock:** the earlier version minimised a flatness objective. It put events on ramps, read mild backwardation as events and stopped early. It was replaced on 4 September by this detector, which installs events only where an event is the one explanation of the shape.

**If asked about its limits:** two adjacent events of equal size form a plateau, which has no peak and is invisible; the first interval cannot separate a scheduled event from a spike front that decays faster than the back ladder; and the detector reads the ATM ladder only. Review the installed calendar before relying on it.

**Worked example.** Monthly ladder, 20% on the event clock, earnings worth 4 extra days between days 30 and 60. That interval is hotter than both neighbours: $N = 30\,(0.04533/0.04 - 1) = 4.0$ days. The Ladder spread readout goes from 53 variance bp on the calendar clock to 0 on the event clock.

**In the app.** Parametric ▸ Term ▸ Auto-calibrate events: choose the horizon, then Calibrate; read the result line and the Ladder spread readout, calendar clock then event clock. Uncalibrated expiries are skipped, so light the ladder first.

**Sources.** [11_event_market_clock.md](../../Docs/handoff/notes/11_event_market_clock.md); [event_autocalib.py](../../backend/volfit/calib/event_autocalib.py); [event_autocalib.py](../../backend/volfit/api/event_autocalib.py); [termLadder.ts](../../frontend/src/lib/termLadder.ts); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-31"></a>

## 31. Spot transport between calibrations

*5 · Time, spot and stored information*

Between calibrations the stored fit is read through a transport, not refitted; the spot–vol rule $R$ of slide 5 sets how far the smile slides.

*1 · The new curve reads the stored one $Rh$ further along; a fixed strike's label moves by $-h$*

$$
w_1(k)=w_0(k+R\,h),\qquad k_1=k_0-h\ \Longrightarrow\ w_1(k_1)=w_0\bigl(k_0+(R-1)\,h\bigr)
$$

*2 · ATM response, to first order*

$$
\Delta\sigma_{\mathrm{ATM}}=\sigma_0(R\,h)-\sigma_0(0)\;\simeq\;R\,s_0\,h
$$

*3 · Sticky local vol: Hagan's map, $w_1(k) = w_0(\ell(k,h))$*

$$
\ell(k,h)=\log\bigl(e^{h}(e^{k}+1)-1\bigr)\;\simeq\;k+\bigl(1+e^{-k}\bigr)h
$$

A calibration is a snapshot at one spot. Between calibrations spot moves, every forward moves with it, and the app has to show a smile at the new forward without refitting. How the smile moves with spot is not in today's quotes: through every arbitrage-free surface pass many admissible tomorrows. So it is a choice, the spot–vol rule R — the same R as in quote synchronisation on slide 5.

The move is h, the log of the new forward over the stored fit's forward, positive when the forward rises. It is always computed from forwards: under a cash dividend schedule the forward moves additively, F-one equals F-zero plus the spot change grown at the rate, so h differs from one expiry to the next.

Line one: the new curve at log-moneyness k reads the stored curve R h further along. The variance time does not change, so this is also a horizontal slide of the vol curve. The second half of the line is the check on the signs. A fixed strike does not move, but its log-moneyness does, by minus h. Substitute: its variance becomes w-zero at k-zero plus R minus one, times h. At R equals one the argument is k-zero: every fixed strike keeps its vol. That is sticky strike, exactly, and it is the default. At R equals zero the curve does not move in k: the smile rides the forward, sticky moneyness.

Line two: at the money the new vol is the stored curve read at R h, so to first order it moves by R times the skew times h. That is what makes R the skew-stickiness ratio: the ATM vol change per unit log-forward move, divided by the skew. Equity skew is negative, so when the forward falls, h negative, the ATM vol rises for any positive R.

Line three is sticky local vol, and here is what Hagan's map is. In a local-volatility model, Hagan's expansion says the implied vol at strike K is, to leading order, the local vol read at the midpoint between the forward and the strike. Now freeze the local-vol surface in absolute strike and move the forward. The new implied vol at K is the local vol at the midpoint of F-one and K — which is the old implied vol at the strike whose midpoint with F-zero is the same point. Write that strike in log-moneyness and you get ell: the stored smile is read at ell of k, a nonlinear relabelling instead of the straight slide of line one. At the money ell of zero is about 2 h — the curve slides twice as far, which is where R near two comes from: short-dated implied skew is about half the local skew. Away from the money the displacement, one plus e to the minus k, is larger on the put side.

What is recomputed on a spot move: nothing. The fitted parameters stay exactly as calibrated. Every view — smile, term, density, variance swap, the local-vol extraction — reads the stored fit through the transport, and for the two local-vol regimes that transport is Hagan's map, a closed form, not a PDE. The calibrated affine surface, when there is one, is transported the same way: its reconstructed smiles through the map, and its vertex grid relabelled — at R equal to two the grid stays fixed in absolute strike. Calibrate refits and resets the move to zero.

The one place where the PDE is re-run is the Scenario overlay of the Parametric lens, in the LV-grid regime. It extracts a local-vol grid from the fitted parametric smiles — Dupire's formula on the parametric surface — holds that grid fixed in absolute strike, reprices the expiry through the forward PDE, and reports the realised R as an output: 2.09 at seven weeks, 2.00 at eighteen months on Note 12's surface. It needs no local-vol calibration; if the node has no parametric fit at all, there is nothing to transport and the overlay is empty.

The strip. The plotted smile, forward down two percent. Sticky strike: the new ATM reads the old curve at minus 0.02, 20.61 percent: 60 bp from the skew, 1.4 from the curvature. Sticky local vol, linear: minus 0.04, 21.26 percent. Hagan's map reads minus 0.0404: plus 127 bp. And the old ATM strike, now at k plus 0.02, keeps 20 percent only under sticky strike: 19.41 under R zero, 20.61 under R two.

**Transition:** the same transport brings yesterday's saved fit to today's forward. That is where the prior starts: next slide.

**If asked why the choice matters:** hedge ratios. A fixed strike's vol moves by R minus one times the skew per unit log-forward move, so the delta changes by vega times that. On Note 12's long-dated SPY smile, skew minus 0.354, the gap between R zero and R two is 19.7 delta points on an out-of-the-money put: same book, same surface.

**If asked what happens if local volatility was never calibrated:** nothing changes. The two local-vol regimes only need the stored parametric smile, read through Hagan's map; the Scenario's LV-grid regime builds its grid from the parametric smiles. The affine local-vol calibration is never required for a transport.

**If asked about the other regimes in the Scenario overlay:** for moneyness, strike and the linear local-vol rule it uses a vol-space one-liner, the curve re-indexed by h plus a level shift of R minus one times skew times h. Its ATM response matches to first order; in the wings it differs at second order. For large moves all of these are first-order rules: Note 12 measured up to 111 vol bp between Hagan's map and linear R two in the wings of a 5 percent move.

**Worked example.** The new ATM reads the stored curve at $Rh$. $R = 1$: $\sigma_0(-0.02) = 20.61\%$, +61 bp (first order +60). $R = 2$: $\sigma_0(-0.04) = 21.26\%$, +126 bp; Hagan's map, $\ell(0,h) = -0.0404$, gives +127 bp.

**Visual.** Three readings of one stored smile: $\sigma_0(k) = 0.20 - 0.30k + 0.35k^2$ after a 2% forward fall, $h = -0.02$. Each curve is the stored one shifted right by $0.02R$; with a negative skew the ATM vol rises with $R$.

**In the app.** Spot move card ▸ Scenario: the dial moves the spot and every lens reads the transported fit; Options ▸ Spot-vol dynamics switches the regime.

**Sources.** [12_spotvol_missing_derivative.md](../../Docs/handoff/notes/12_spotvol_missing_derivative.md); [transport.py](../../backend/volfit/dynamics/transport.py); [ssr.py](../../backend/volfit/dynamics/ssr.py); [service.py](../../backend/volfit/api/service.py); [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md).

<a id="slide-32"></a>

## 32. Activating a prior where quote support is weak

*5 · Time, spot and stored information*

Yesterday's smile may pull on today's fit only where today's quotes leave a feature undetermined. Each persisted feature has a gate: fully open with no nearby quote, exactly closed from about one quote on.

*1 · Support of a leg: effective number of quotes near it*

$$
n_a=\sum_i \tilde\lambda_i\,\exp\!\Bigl(-\frac{(k_i-k_a)^2}{2b^2}\Bigr)
$$

*2 · Information of an operator, $I_{\mathrm{ATM}} = n_0$: every leg must be supported*

$$
I_{\mathrm{RR}}=\Bigl(\frac{1}{n_c}+\frac{1}{n_p}\Bigr)^{-1},\qquad I_{\mathrm{BF}}=\Bigl(\frac{1}{4n_c}+\frac{1}{4n_p}+\frac{1}{n_0}\Bigr)^{-1}
$$

*3 · Gate: 1 with no support, exactly 0 from the required level*

$$
g_j=\Bigl[\operatorname{clip}\Bigl(1-\frac{I_j}{I_{\mathrm{req}}},\,0,\,1\Bigr)\Bigr]^{\gamma}
$$

*4 · One row per open gate; rows share a budget*

$$
r_j=\sqrt{\Lambda_j}\,\bigl(O_j(\theta)-O_j(\mathrm{prior})\bigr),\qquad \Lambda_j=B\,\frac{g_j}{\sum_m g_m}
$$

| Symbol | Meaning |
| --- | --- |
| $k_i,\ \tilde\lambda_i$ | Log-moneyness of quote $i$; its fit weight rescaled to mean one |
| $n_0,\ n_c,\ n_p$ | Support at the ATM leg and at the $25\Delta$ call and put legs |
| $b$ | Kernel bandwidth: 0.06 in log-moneyness |
| $I_j,\ I_{\mathrm{req}}$ | Information of operator $j$; required level 1, one effective quote |
| $g_j,\ \gamma$ | Gate, the gap column in the app; sharpness, 1 |
| $O_j(\theta),\ O_j(\mathrm{prior})$ | The operator, in vol, on the model's smile and on the transported prior |
| $\Lambda_j,\ B$ | Weight of prior row $j$ (column $\lambda$ in the app); budget $B = 50\% \times \sum_i \lambda_i$ |
| $g_{\mathrm{VS}}$ | Gate of the var-swap level: its own row, weight $B\,g_{\mathrm{VS}}$, support probed at 0 and $\pm 1.4\,\sigma_{\mathrm{ATM}}\sqrt{\tau}$ |

Overnight the at-the-money level moves on news and is re-quoted at once; the wings may get no fresh quote at all. Fit today's quotes alone and the unquoted wings flap. Anchor everything to yesterday and the prior damps the genuine move at the money. The rule of this slide: yesterday may speak only where today is silent.

The set-up. The saved prior is first carried to today's forward with the transport of the previous slide, so a pure spot move is not mistaken for a change of shape. The persisted features are operators, the desk's own coordinates: the ATM vol, the 25-delta risk reversal and butterfly, and the variance-swap level. Their leg strikes are located once, on the transported prior, and frozen.

Line one: support. For each leg, count today's quotes near it with a Gaussian kernel of width 0.06 in log-moneyness, the fit weights rescaled to mean one. A quote exactly on the leg counts one; a quote two bandwidths away counts about 0.14.

Line two: the information of an operator. If each leg's vol were estimated with a variance proportional to one over its support, independently, the operator's variance would be the sum of its coefficients squared over the supports; the information is the inverse. Two consequences. One unsupported leg kills the operator: a risk reversal with no put quotes is undetermined however many calls there are. And the butterfly's wing legs enter with a quarter, so the same legs identify the butterfly more easily than the risk reversal.

Line three: the gate. One when there is no support, falling linearly with gamma one, and exactly zero once the information reaches the requirement: one effective quote. Exactly zero, not small.

Line four: the rows. Each open gate adds one residual row: the operator on the model's smile minus the same operator on the transported prior, in vol, times the square root of its weight. The weights share a budget B, 50 percent of the summed quote weights by default, in proportion to the gates. The variance-swap operator has its own row, weight B times its gate, with its support probed at the money and 1.4 ATM standard deviations out on each side.

The strip. A one-year node, flat 20 percent prior, five quotes of weight one within four hundredths of the money, so B is 2.5: the prior rows together weigh like two and a half quotes. The ATM leg has 4.49 effective quotes: closed. The 25-delta call leg at 0.155 has 0.30; the put leg at minus 0.115 has 1.02. The risk reversal's information is 0.23, its gate 0.77, its weight 1.91; the butterfly's information 0.76, gate 0.24, weight 0.59. The variance swap sees almost nothing at 0.28 from the money: gate one, weight 2.5.

The flip side. The same five quotes on a three-month node close every vol gate: the 25-delta legs sit at plus 0.07 and minus 0.06, about one bandwidth from the quotes, and the kernel credits them. Only the variance-swap row stays open, gate 0.77. The kernel overstates identification just beyond the last quote, which is why the default mode, hybrid, adds strike anchors for the deep tail: next slide.

What a closed gate guarantees: a zero row, so no cost and no gradient. The prior cannot pull on that feature directly. It can still move it indirectly, through other open rows and the model's own coupling. And support counts quotes; it does not check whether they agree. Disagreement is the Kalman filter's business, two slides on.

**Transition:** which features to persist matters as much as where. Shape against level, next slide.

**If asked where the prior comes from:** one prior per node, active on save. Saving a node's fit makes it the prior at once, with no fetch step. Only lit, calibrated nodes can become priors; graph output never does. There is no age decay in this gate.

**If asked whether the gate could use the real precision of the fit:** the opt-in two-pass mode does that. It fits once without the prior, measures how well each operator is actually pinned, then refits: exact, at about twice the cost.

**Worked example.** One-year node, flat 20% prior, five equal-weight quotes at $k = 0, \pm 0.02, \pm 0.04$: $B = 2.5$. Supports $n_0 = 4.49$, $n_c = 0.30$ ($k = 0.155$), $n_p = 1.02$ ($k = -0.115$). ATM closed. RR: $I = 0.23$, $g = 0.77$, $\Lambda = 1.91$. BF: $I = 0.76$, $g = 0.24$, $\Lambda = 0.59$. Var swap: $g = 1$, weight 2.5.

**In the app.** Options ▸ Prior ▸ Config: the Prior diagnostics table lists, per expiry, the open operators with gap · $\lambda$ · age · src · $h$. An operator the quotes pin down drops out of the table.

**Sources.** [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [operators.py](../../backend/volfit/calib/operators.py); [precision.py](../../backend/volfit/calib/precision.py); [service.py](../../backend/volfit/api/service.py); [schemas.py](../../backend/volfit/api/schemas.py).

<a id="slide-33"></a>

## 33. Persisting shape versus absolute strike values

*5 · Time, spot and stored information*

What the prior persists decides which moves it resists: risk reversals and butterflies ignore a parallel shift of the smile; a fixed-strike anchor does not.

*1 · Shape operators: coefficients that sum to zero*

$$
\mathrm{RR}=\sigma(k_c)-\sigma(k_p),\qquad \mathrm{BF}=\tfrac12\bigl(\sigma(k_c)+\sigma(k_p)\bigr)-\sigma(0)
$$

*2 · So a parallel move by $v$ vol points leaves both unchanged*

$$
\mathrm{RR}(\sigma+v)=\mathrm{RR}(\sigma),\qquad \mathrm{BF}(\sigma+v)=\mathrm{BF}(\sigma)
$$

*3 · Strike anchor: a price residual over vega, read in vol*

$$
r_j=\sqrt{\Lambda_j}\;\frac{c_\theta(k_j)-c_{\mathrm{prior}}(k_j)}{\partial_\sigma B(k_j)+\eta}\;\simeq\;\sqrt{\Lambda_j}\,\bigl(\sigma_\theta(k_j)-\sigma_{\mathrm{prior}}(k_j)\bigr)
$$

The gate decides where the prior may pull. This slide is about what it pulls on, and that decides which market moves the prior resists.

Line one: the risk reversal and the butterfly, with legs at the 25-delta strikes, located once on the transported prior and frozen. Their coefficients: plus one and minus one for the risk reversal; one half, one half and minus one for the butterfly. Both sets sum to zero.

Line two is the consequence. Add the same v to every vol and both operators are unchanged. A shape row therefore cannot resist a parallel move. When the at-the-money quotes lift the level overnight, the rows carry yesterday's shape onto today's level: the unquoted wing is rebuilt as today's ATM plus yesterday's shape.

Line three is the other kind of row, the strike anchor. A call-price difference at a fixed strike, divided by the prior's vega plus the floor, so it reads as a vol error. It persists an absolute value at that strike. If the level jumps and that strike is unquoted, the anchor pulls the wing back toward yesterday's absolute vol. The inverse vega is capped at 25 times its smallest value, so a far-tail anchor cannot dominate.

The strip. Yesterday: ATM 20, 25-delta call 19, put 23. Risk reversal minus 4, butterfly plus 1. Overnight every vol rises by 4 points. Risk reversal and butterfly are unchanged, so their rows cost nothing. An anchor at the put strike still wants 23 against a market at 27: a 4-point residual pulling the wing down. The figure shows the same thing on a whole curve.

Recorded in Note 13, on a controlled 4-point jump with quotes only near the money: the operator rows land 0.3 vol point from the lifted wing at k minus 0.20; strike anchors miss it by 3.7, still 3.3 from yesterday's curve. And the at-the-money fit under the operator prior matches the data-only fit to 0.00: no damping where the quotes are.

Why the default combines both. Pure operator modes are often inert on liquid mornings: the kernel closes their gates, as on the previous slide. And no operator reaches the deep tail. Hybrid adds strike anchors at the 2, 5 and 10-delta strikes of the transported prior. The budget: together, the anchor rows get a total least-squares weight equal to 20 percent of the node's summed quote weights — the setting priorTailAnchorStrengthPct — so the prior competes with the data at a controlled strength. That total is split among the anchors in proportion to the missing quote mass in each anchor's cell: the desired quote density minus the observed one, floored at zero, times the cell width. An anchor sitting where the quotes already reach gets nothing; as the data fill in, the rows vanish. On the August 2024 spike backtest, 1,116 node-days, hybrid improved the held-out wing by a median 32 vol bp over no prior and won 66 percent of the days; the pure operator modes were at zero at the median. The price: across a jump, the deep tail is still pulled toward yesterday's absolute level.

**Transition:** the prior fills gaps. Next: dense but noisy quotes, where the gate is closed and yet today's fit should not be taken at face value. That is the Kalman filter.

**If asked how to see the effect on one node:** the chart header's Fit switch draws a shadow fit in place of production: Free, with no prior and no filter, on the same quotes and model. With a saved prior active, production is the plus-Prior fit. Parametric Compare adds the Pull column: the ATM distance to the free fit, in vol bp.

**If asked about the variance-swap row:** it matches the prior's variance-swap level by default. An option makes it match the variance swap minus the ATM vol instead, so a level move carries the tail along.

**Worked example.** Yesterday ATM 20%, $25\Delta$ call 19%, put 23%: $\mathrm{RR} = -4$, $\mathrm{BF} = +1$ vol point. Overnight every vol rises 4 points: 24%, 23%, 27%. RR and BF are unchanged, so their rows cost nothing. A strike anchor there, as in strike-gap mode, still targets 23%: a 4-point residual pulling the wing down.

**Visual.** Illustrative: the whole smile lifted by 4 points keeps its RR and BF at fixed legs. A fit anchored to the earlier absolute wings keeps the old level outside the quoted band (shaded).

**In the app.** On a thin node with a saved prior: the chart header's Fit switch, Production (the + Prior fit) against Free; Parametric ▸ Compare shows the Pull column in ATM vol bp.

**Sources.** [13_prior_flat_directions.md](../../Docs/handoff/notes/13_prior_flat_directions.md); [operators.py](../../backend/volfit/calib/operators.py); [prior.py](../../backend/volfit/calib/prior.py); [prior_mode.py](../../backend/volfit/api/prior_mode.py); [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md).

<a id="slide-34"></a>

## 34. Temporal filtering of ATM handles

*5 · Time, spot and stored information*

Each calibration is a noisy reading of three numbers: ATM level, skew and curvature. The filter carries yesterday's estimate to today and averages it with today's reading, each weighted by the inverse of its variance.

*1 · Predict: move the last estimate to today's forward; the wait adds variance*

$$
m^{-}=\mathcal{T}_h\bigl(m^{+}_{\mathrm{prev}}\bigr),\qquad P^{-}=P^{+}_{\mathrm{prev}}+Q
$$

*2 · Measure: today's fit reads the handle as $z$, with a variance $R$ built on the next slide*

$$
z=x(\hat\theta),\qquad R=\operatorname{Var}(z)
$$

*3 · Update: the inverse-variance average of prediction and reading*

$$
m^{+}=\frac{R\,m^{-}+P^{-}z}{P^{-}+R}=m^{-}+K\,(z-m^{-}),\qquad K=\frac{P^{-}}{P^{-}+R},\qquad \frac{1}{P^{+}}=\frac{1}{P^{-}}+\frac{1}{R}
$$

*4 · The transport of the three handles, first order in the forward move $h$*

$$
\sigma_0'=\sigma_0+\mathrm{SSR}\,s_0\,h,\qquad s_0'=s_0+\kappa_0\,h,\qquad \kappa_0'=\kappa_0
$$

| Symbol | Meaning |
| --- | --- |
| $\sigma_0,\ s_0,\ \kappa_0$ | ATM vol, skew $\partial_k\sigma(0)$ and curvature $\partial_k^2\sigma(0)$ of the LQD fit (slide 17) |
| $m^-,\ P^-$ | Predicted value and variance of a handle, before today's reading |
| $m^+,\ P^+$ | Its filtered value and variance after the reading |
| $z,\ R$ | Today's fitted handle and its variance, from the fit itself (next slide) |
| $Q$ | Variance added by the wait: $(30\ \text{bp})^2$ per day for the level, $0.02^2$ and $0.05^2$ per day for skew and curvature, plus a term in the spot move |
| $K$ | The gain: the share of the total variance the prediction carries; 0 keeps the prediction, 1 takes the reading |
| $h,\ \mathrm{SSR}$ | Log forward move since the last reading; the spot–vol rule of slide 31, written SSR here because $R$ is a variance |
| $\mathcal{T}_h$ | The transport of line 4 |

The prior of the last two slides fills gaps. This slide is about the opposite case: dense quotes, so every gate is closed, but noisy ones — today's fit should not be taken at face value. The tool is a Kalman filter on three numbers per node, the ATM handles: level, skew and curvature.

The principle in one sentence: two estimates of the same number, each with a variance, are best combined by weighting each with the inverse of its variance. The filter does that once per day, per node and per handle.

Line one, predict. Take the last filtered value, m-plus, and move it to today's forward with the transport of line four — the same spot rule as the transport slide, to first order. Its variance grows by Q: the wait adds uncertainty, 30 vol bp per root day for the level by default, plus a term for the size of the spot move.

Line two, measure. Today's data-only fit gives each handle a value z, and — this is the part that is computed, not set — a variance R. The next slide builds R from the fit itself.

Line three, update. The posterior is the inverse-variance average: R times the prediction plus P-minus times the reading, over their sum. Written as a step, it moves the prediction toward the reading by the gain K, the prediction's share of the total variance. And the precisions add: one over P-plus is one over P-minus plus one over R. A precise reading, small R, gives a gain near one and the reading wins; a noisy one gives a small gain and the estimate barely moves.

Line four is the transport of a handle vector. The level moves by SSR times skew times h, the skew by curvature times h, and the curvature stays. The spot rule is written SSR here because on these two slides R is a variance.

The updates run per handle, separately, and that is deliberate. With a full three-by-three covariance, the correlation between level and curvature let a junk curvature reading on a coarse chain drag the level by 3 to 28 vol points in the backtest — worse than no filter at all. Scalar gains cannot do that.

The strip: the level's prediction is 20.0 plus or minus 0.30, the fit reads 20.4 plus or minus 0.15. The gain is 0.09 over 0.1125, 0.80, so the posterior is 20.32, plus or minus 0.13. For the curvature, a stale strike has put a kink in today's fit: 0.55 against a prediction of 0.10, but with a variance so much wider that the gain is 0.027. The posterior is 0.112: the kink is barely admitted.

**Transition:** everything rests on R, the variance of today's reading. The next slide shows how it is built from the fit itself.

**If asked how this differs from the prior:** the prior has a gate and turns off where the quotes speak; the filter is always on, at a weight that follows from the variances. And the prior acts on the fit; the filter, in its default overlay mode, acts on the handles read off the fit.

**Worked example.** Level: prediction $20.0\% \pm 0.30\%$, today's fit $20.4\% \pm 0.15\%$: $K = 0.30^2/(0.30^2 + 0.15^2) = 0.80$, posterior $20.32\% \pm 0.13\%$. Curvature: prediction $0.10 \pm 0.05$, fit $0.55 \pm 0.30$ (a stale strike puts a kink in it): $K = 0.027$, posterior $0.112$. The kink is barely admitted.

**In the app.** Options ▸ Kalman filter: Observation filter Overlay; the table K(ATM) · K(skew) · K(curv) · innov bp, then Timeline. On the smile, the FILTER badge.

**Sources.** [15_kalman_computed_trust.md](../../Docs/handoff/notes/15_kalman_computed_trust.md); [observation_filter.py](../../backend/volfit/calib/observation_filter.py); [observation_filter.py](../../backend/volfit/api/observation_filter.py).

<a id="slide-35"></a>

## 35. Where the reading's variance comes from

*5 · Time, spot and stored information*

The variance of today's handles is computed from the fit itself: from how firmly the quotes, at their stated noise, pin the parameters, and from how badly the fit missed them.

*1 · Stated noise of a quote, in vol: half its spread, floored at 1 bp, wider under 30 days*

$$
\delta_i=\max\Bigl(\tfrac12\bigl(\sigma_i^{\mathrm{ask}}-\sigma_i^{\mathrm{bid}}\bigr),\ 1\ \mathrm{bp}\Bigr)\cdot\max\Bigl(1,\sqrt{30/n_d}\Bigr)
$$

*2 · How firmly the quotes pin the parameters: the Jacobian, each quote row divided by its noise*

$$
\mathcal{I}_\theta=J^\top J,\qquad J_{ij}=\frac{1}{\delta_i}\,\frac{\partial r_i}{\partial\theta_j}\ \ \text{(quote rows)},\ \ \text{plus the penalty rows}
$$

*3 · From parameters to handles: the handle Jacobian $G$ carries the uncertainty through*

$$
R_x=G\,\mathcal{I}_\theta^{-1}\,G^\top,\qquad G=\frac{\partial x}{\partial\theta}\ \ (3\times(N+1))
$$

*4 · Inflate when the fit misses the quotes by more than their stated noise*

$$
R=\rho\,R_x,\qquad \rho=\operatorname{clip}\Bigl(\frac{\chi^2}{m-3},\,1,\,25\Bigr),\qquad \chi^2=\sum_i\lambda_i\,\frac{r_i^2}{\delta_i^2}
$$

Everything on the previous slide rests on R, the variance of today's reading. Quote weights cannot give it: they say which quotes matter more, not how noisy each one is. So R is built from three things: the market's stated noise per quote, the fit's own sensitivities, and how badly the fit missed.

Line one, the stated noise. Each quote gets half its bid–ask spread in vol, floored at one basis point, and multiplied below 30 days by the root of 30 over the days to expiry — 1.4 at 15 days, 2 at 7 — because short-dated quotes were measured to be two to three times noisier than their spread says.

Line two, the Jacobian. J is the matrix the solver already has at the solution: one row per quote — the derivative of that quote's residual with respect to every parameter — plus the model's penalty rows. Divide each quote row by its noise. Then J-transpose J is the information matrix: entry by entry, how much a unit move of the parameters changes the residuals, measured in units of the quotes' noise. A direction the quotes pin has a large entry; a direction they do not see has a small one. In band mode a quote sitting inside its spread has a zero row: it contributes no information, which is right.

Line three, from parameters to handles. G is the handle Jacobian: three rows, one per handle, one column per parameter — how much the ATM level, skew and curvature move when each parameter moves. It is computed by central differences of the exact handle map, each evaluation a slice build, microseconds. The delta method then gives the handles' variance: G times the inverse information times G-transpose. The inverse is regularised: eigenvalues below ten to the minus ten of the largest are raised, so an unpinned direction reads as a large but finite variance, never as zero uncertainty.

Line four, the inflation. Chi-square is the fit's weighted misfit in units of the stated noise, over the quotes. If the fit sits inside the stated noise, chi-square over the degrees of freedom is about one and nothing changes. If a dense cluster cannot be fitted within its stated noise — the quotes contradict each other — chi-square grows, rho grows, R grows, and the gain falls. No threshold, no rule: disagreement among the quotes reads as noise. Rho is capped at 25 so one broken chain cannot poison the state.

The strip is the shape of the numbers. Twenty quotes, 10 bp of noise each, all reading the level: the information is 20 over delta squared, so the level's standard deviation is delta over root 20, 2.2 bp. If the fit misses every quote by twice its noise, chi-square is about 80 over 17 degrees of freedom, rho 4.7, and the standard deviation becomes 4.9 bp. On Note 15's test, a contradictory cluster took the curvature gain from 0.73 to 0.20 and left the level's at 0.74.

Overlay and active. In Overlay, the default, the filter computes the posterior handles and draws them: the fit itself is untouched, and the filtered smile is the fit retargeted to the posterior handles. In Active, the prediction enters the fit as three extra rows — each handle's distance to its prediction, over the prediction's variance — so one calibration produces the posterior directly, and today's quotes count once. Prior rows on the same handles are dropped in that case.

**Transition:** to compare the free, prior and filtered fits through time on the same observations, the app replays stored frames. The Series lens, next.

**If asked about the factors route:** when no solver Jacobian is available the covariance falls back to the graph layer's precision vocabulary — rms, quote density, spread, freshness — per handle. It is also the A/B column in the filter table.

**If asked about intraday use:** at daily cadence on expiries beyond 30 days the active fit beat both the raw fit and the overlay in the backtest. On intraday series with short expiries it did not: an active lane spent minutes per frame and diverged, so the Series dialog warns and caps a frame at 300 seconds. Overlay has no such problem.

**Worked example.** Twenty quotes, each with 10 bp of stated noise, all reading the level: $\mathcal{I} \approx 20/\delta^2$, so the level's sd is $\delta/\sqrt{20} = 2.2$ bp. If the fit misses them by twice their noise, $\chi^2 \approx 80$ and $\rho \approx 80/17 = 4.7$: the sd becomes $2.2\sqrt{4.7} = 4.9$ bp and the gain falls.

**In the app.** Options ▸ Kalman filter: R Jacobian (default) or factors; the ρ column of the filter table; the contaminated flag when the fit carried prior rows.

**Sources.** [15_kalman_computed_trust.md](../../Docs/handoff/notes/15_kalman_computed_trust.md); [observation_measurement.py](../../backend/volfit/calib/observation_measurement.py); [observation_filter.py](../../backend/volfit/api/observation_filter.py).

<a id="slide-36"></a>

## 36. Series replay and independent calibration lanes

*5 · Time, spot and stored information*

A series stores one ticker's chains at a sequence of instants. Several lanes calibrate the same frames in time order, each with its own settings and its own memory, so their differences come from the settings alone.

*1 · Memory: a lane's prior is its own previous fit, transported*

$$
\mathrm{prior}^{\ell}_{i}=\mathcal T_{h_i}\bigl(\mathrm{fit}^{\ell}_{i-1}\bigr),\qquad h_i=\log\frac{F_i}{F_{i-1}}
$$

*2 · Fit error: mean over frames of the fit's RMS, in vol bp*

$$
\overline{\mathrm{rms}}^{\,\ell}=\frac1n\sum_{i=1}^{n}\mathrm{rms}^{\ell}_i
$$

*3 · Roughness: mean frame-to-frame move of the ATM vol*

$$
\mathrm{rough}^{\ell}=\frac{1}{n-1}\sum_{i=2}^{n}\bigl|\sigma_0^{\ell}(i)-\sigma_0^{\ell}(i-1)\bigr|
$$

*4 · Pull: ATM distance to the free lane at the same frame*

$$
\mathrm{pull}^{\ell}_i=\sigma_0^{\ell}(i)-\sigma_0^{\mathrm{free}}(i)
$$

| Object | Holds | Purpose |
| --- | --- | --- |
| Frame | One instant: chain, spot and quote kind, harvested, live or imported | The same market inputs for every lane |
| Lane | A patch over the series' frozen base settings: model, prior mode, filter mode | Change one policy or model at a time |
| Lane memory | Its own prior and filter state, checkpointed at every frame | No lane feeds another; pause and resume are exact |
| Replay | Frames in time order; each lane runs the desk's own Calibrate on a detached state | No future information; the desk's fit |
| Readouts | Smile, surface, term; per lane rms, roughness, pull, filter $\zeta$, fit time | Where and when the lanes diverge, and at what cost |

Everything in this chapter has a time dimension: the prior uses yesterday, the filter carries a state. Judging them needs the same observations run under different settings, in time order. That is what a series does.

Frames first. A series has one ticker, a clock, meaning a start, a step and a count, and a ladder of expiries. Each frame is the chain at one instant: harvested from Massive's historical NBBO, the same as-of fetch as the Smile lens, about 12 seconds per frame at the 1,500-contract cap; or taken live at each tick; or imported from stored captures. A frame is an observation: nothing is interpolated between frames.

Lanes. Each lane is a patch over the series' base settings, frozen at creation so the replay is reproducible after the live Options change. The presets: LQD free, plus prior, which is hybrid, plus prior plus filter, which is the active filter, SVI-JW and MCS free, local vol free and with prior, and Current Options, the live settings as they are. Each lane runs on its own detached state; the live desk is never touched.

Line one: memory. A prior lane's prior at frame i is its own fit at frame i minus one, carried to frame i's forward by slide 31's transport. Its filter state is also its own, with the time step read off the snapshot timestamps. A free lane has no memory: its frames are independent. The first frame of a memory lane is a seed fit. The carry is checkpointed at every frame, so pause and resume reproduce the same fits.

Order: every lane fits frame i before any lane moves to frame i plus one, and the harvest runs in its own thread, so a frame's fits start as soon as its chain lands.

Lines two to four are the readouts. Mean rms: the fit's error to that frame's quotes, averaged over frames. Roughness: the average absolute frame-to-frame move of the ATM vol, what a prior or a filter damps. Pull: the lane's ATM vol minus the free lane's at the same frame, what the prior bought. Read them together. A prior that lowers roughness for a small rms cost is doing its job; one that lowers roughness by lagging a real move is not. Look at the frames around the move.

The strip, recorded on 10 September on a SPY replay day: 25 frames, 15 minutes apart, the one-day expiry. Free: rms 4.66 bp, roughness 18.4 bp per frame. Plus prior: rms 5.20, roughness 17.5, mean absolute pull 3.6 bp. So the prior damps the path by about 0.9 bp per frame for about half a bp of rms. The overlay filter leaves the fit unchanged and adds its record, with an ATM zeta standard deviation of 0.82.

The filter lane in that readout had to be the overlay filter. The plus-prior-plus-filter preset uses the active filter, which the previous slide showed failing at intraday cadence on short expiries: series creation warns, and a 300-second frame budget stops a lane from diverging for ever. For filter evidence on an intraday series, set Options to hybrid with the filter on Overlay, and add the Current Options lane.

Adopting a result is explicit: Adopt as prior saves one lane's fit at one frame as the live prior, through the normal save route. Nothing else in a series writes a prior. A series can be exported to a file and imported elsewhere.

**Transition:** so far each node has been handled alone, through time. The last chapter couples nodes across expiries and underlyings: the graph.

**If asked whether a lane reproduces the desk:** yes. A free lane's frame fit is byte-identical to a desk Calibrate on the same chain under the same settings, locked by a test, and the certification case series replay determinism re-runs a stored series and reproduces every fit.

**If asked about cost:** measured on the stored 0DTE store, a free LQD lane took 391 ms per frame, 28 seconds for 60 frames; a hybrid-prior lane 1,266 ms per frame at the median. Local-vol lanes dominate, at 1 to 25 seconds per frame.

**Recorded, SPY replay day, 10 September.** 25 frames, 15 minutes apart; one-day expiry. Free: rms 4.66 bp, ATM roughness 18.4 bp per frame. + Prior (hybrid): rms 5.20 bp, roughness 17.5 bp, mean $|\mathrm{pull}|$ 3.6 bp. The overlay filter leaves the fit unchanged and adds its record: ATM $\zeta$ standard deviation 0.82.

**In the app.** Series lens (Alt+6): New series… with clock, ladder and lane presets, Estimate, then Start; the Lanes stage shows the metric chart and the evidence table (mean rms · roughness · pull · $\zeta$ · fit ms).

**Sources.** [series_replay_roadmap.md](../../Docs/series_replay_roadmap.md); [series_lanes.py](../../backend/volfit/api/series_lanes.py); [series_evidence.py](../../backend/volfit/api/series_evidence.py); [series_presets.py](../../backend/volfit/api/series_presets.py); [series_create.py](../../backend/volfit/api/series_create.py); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-37"></a>

## 37. Graph state: handle changes against transported priors

*6 · Graph inference*

A node is one smile: one underlying at one expiry. The graph estimates how far today's market has moved each node's three ATM handles away from its saved prior.

*1 · Three handles $y_i$: level, slope and curvature at the money*

$$
y_i=\bigl(\sigma_i(0),\ \partial_k\sigma_i(0),\ \partial_k^2\sigma_i(0)\bigr)
$$

*2 · Lit node: today's fit minus the transported prior*

$$
d_i=y_i^{\mathrm{fit}}-y_i^{0}
$$

*3 · Every node after the solve: prior plus inferred change*

$$
\widehat y_i=y_i^{0}+\widehat z_i,\qquad \widehat z_i=0\ \ \text{if no lit node is connected}
$$

This section fills in the dark part of the universe. A node is one smile: one underlying at one expiry. The canvas is the staging of 24 September: six underlyings, 47 nodes, 39 of them lit — calibrated today — and 8 dark, with real quotes we keep aside for checking.

Line one is the state. We do not push a whole smile through the graph. We push three numbers per node, the handles: the at-the-money vol, the slope of the smile in log-moneyness at the money, and its curvature there. For a fit they are read exactly from the LQD slice, with no finite differences. A skew of minus 0.1 means that one tenth of log-moneyness to the left adds about one vol point.

The handles are measured from a baseline, y-zero: the node's saved prior, moved to today's forward by the spot–vol rule. If the ticker's active prior has this exact expiry, we use it. If not, we take that prior's nearest expiry. Failing that, today's own fit, and as a last resort a flat 20 percent smile. The Inspector prints which one was used. It matters twice: the baseline carries all the shape the graph does not touch, and a weaker source enters the solve with less confidence.

Line two: at a lit node the observation is d, today's fitted handles minus the baseline — the market's move against the prior. Line three: after the solve, every node publishes its baseline plus the inferred change, z-hat. Lit nodes land on their fit, or very close to it. Dark nodes get what the relations carry to them.

Why changes rather than levels? Levels and shapes differ a lot across names and maturities, and the prior already holds them. What the lit nodes tell us this morning is how the market moved, and that is what relations can carry. So the graph spreads the move, and each smile keeps its own shape. When no lit node is connected to a node, its change is exactly zero: it stays at its prior, with a wide band and a flag. Nothing is invented.

Each handle is its own field: level, skew and curvature are solved separately, with the same relations and handle-specific noise scales.

The strip is a real node from that capture: AAPL, February 2027, dark. Its baseline came from the nearest expiry of the saved prior: 25.4 percent, skew minus 0.103, curvature 0.645. After the Run: the level is still 25.4 — it moved minus 2.5 bp — the skew is minus 0.110 and the curvature 0.760. The lit AAPL expiries around it moved between plus 2 and minus 41 bp, and its cross-asset neighbours barely moved, so the level change it received is small.

**Transition:** the question is now how a change seen at a lit node reaches a dark one. There are three operators for that; the next slide compares them.

**If asked why three handles and not the whole smile:** three numbers are what one day's move pins down across many names. The rest of the shape comes from the prior. Reconstruction, at the end of this section, turns the three numbers back into a full arbitrage-free smile of the node's model.

**If asked what happens when the prior is old or far away:** its precision drops. It halves every 30 days of age and falls with the transport distance, the log of today's forward over the prior's. A dark node's baseline also counts at a quarter of the lit tier, so the lit data move it more easily.

**Recorded, 24 September.** Dark AAPL 19 Feb 2027, Layered Run. Baseline from the prior's nearest expiry, $y^0 = (25.4\%,\ -0.103,\ 0.645)$; result $\widehat y = (25.4\%,\ -0.110,\ 0.760)$, so $\widehat z = (-2.5\ \text{bp},\ -0.007,\ +0.115)$. The lit AAPL expiries moved between $+2$ and $-41$ bp.

**Visual.** 24 September, after a Layered Run: 39 lit nodes (filled) and 8 dark (outlined) on six underlyings, SPY, NVDA, AAPL, QQQ, XOM and MSFT. Arrows are calendar and cross-asset relations; the largest shift is 122.9 bp.

**In the app.** Graph lens (Alt+1): Run, then click a dark node. The Inspector shows prior to posterior per handle, the Shift, the Posterior confidence ($1\sigma$) and the Prior source.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [graph_nodes.py](../../backend/volfit/api/graph_nodes.py); [atm.py](../../backend/volfit/models/lqd/atm.py); [precision.py](../../backend/volfit/graph/precision.py).

<a id="slide-38"></a>

## 38. Three graph operators and what each assumes

*6 · Graph inference*

The operator is the rule that carries lit changes to dark nodes. Layered is the default, Precision the second choice, Smooth field the legacy option under Advanced.

*1 · Smooth field: stay small, and close to the neighbours' weighted average*

$$
E_{\mathrm{sm}}(z)=\kappa\sum_i z_i^2+\eta\sum_i \pi_i\Bigl(z_i-\sum_j K_{ij}\,z_j\Bigr)^2
$$

*2 · Precision: one term per relation $z_i \approx \beta_{ij} z_j$, held with precision $p_{ij}$*

$$
E_{\mathrm{msg}}(z)=\sum_{j\to i}p_{ij}\,\bigl(z_i-\beta_{ij}\,z_j\bigr)^2=z^\top Q\,z
$$

*3 · Layered, reciprocal part: lit nodes fixed at their observed changes $d_{\mathrm{lit}}$, zero gradient in the free nodes*

$$
Q_{\mathrm{free,free}}\;\widehat z_{\mathrm{free}}=-\,Q_{\mathrm{free,lit}}\;d_{\mathrm{lit}}
$$

| Operator | Assumes | Far from the lit node | Direction · memory |
| --- | --- | --- | --- |
| Smooth field · legacy | related smiles move alike | the move fades with distance | none · none |
| Precision | each relation is a stated rule: $\beta$ and $p$ | full $\beta$ amplitude at Desk strength; the band widens | both ways · none |
| Layered · default | the same rules, plus one-way arcs where set | full $\beta$ amplitude; fresh lit nodes stay fixed | one way on directed arcs · each node's residual |

One question separates the three operators: by what rule does a change seen at a lit node reach a dark one? Each answers with a quadratic penalty on the field of changes, z. The solve finds the z that agrees with the lit data and pays the least penalty. In probability language the penalty is minus twice the log-density of a Gaussian prior; minimising it with the data gives the posterior mean, and its curvature gives the bands.

Line one, the smooth field, makes two wishes. Every change should be small: kappa pulls it toward zero. And each node should match the weighted average of its neighbours: eta sets how much that matters. K is the table of trust weights; each row sums to one, so a node shares one unit of attention among its informers. Pi weighs each node by its traffic in that table. No term says 'this move should be twice that one'. How far a move travels, and how much of it arrives, come out of kappa, eta and the weights together.

Line two, Precision, has one term per relation. The relation from informer j to receiver i says z-i should be beta times z-j, and p says how firmly. Beta is the amplitude, p the confidence, two separate dials. Summed over relations the penalty is z-transpose Q z, with Q sparse: each relation touches two nodes.

Line three is the reciprocal part of Layered. It uses the same relation terms. The fresh lit nodes are fixed at their observed change — a boundary condition. Split Q into its free and lit blocks and set the derivative of z-transpose Q z with respect to the free nodes to zero: Q free-free times z-free equals minus Q free-lit times d-lit, where d-lit stacks the observed changes of the lit nodes. One linear solve. On top of that, Layered can carry one-way arcs with a remembered residual; that is four slides on.

The strip runs the three operators on the smallest ladder: 3M, 6M and 1Y of one ticker, only 6M lit, at plus one vol point. Precision and Layered give 3M plus 2.00 and 1Y plus 0.50, exactly: the calendar amplitude is the ratio of maturities, and the precision moves only the bands — 2.94 points at 3M, 1.57 at 1Y. The smooth field at its defaults gives plus 0.89 at both ends: its calendar edges carry beta one, so it does not scale by maturity, and kappa shrinks the move a little. On a longer chain its move keeps fading.

Which one runs: Layered is the default in the Graph lens since 7 September, chosen for its one-way and memory semantics. Precision is the next button. Smooth field is the legacy operator, kept byte-identical and reachable under Advanced. It is also what a bare API request solves, so old replays reproduce exactly.

**Transition:** the next slide opens one relation: what beta and p mean, and why an arrow does not stop information flowing back.

**If asked which operator is best:** the recorded evidence is split. Daily leave-one-out on three historical regimes: Precision at the learned level tied the smooth field, 280.9 against 279.3 bp of ATM error. Intraday replay on an ETF triangle, eight sessions, 27 July: smooth field 168.6 bp, almost no better than the prior alone at 172.7; Precision 65.8; the best Layered arm 73.7. The daily campaign gave Layered's solve an edge in stressed regimes, 14.7 bp better in the August 2024 spike and 9.2 in the October 2022 bear, and 6.2 bp worse in the calm one. The default is a choice of semantics; the benchmark pack is to adjudicate it.

**If asked about the smooth field's third term:** the legacy operator can add an optimal-transport term that prices a move by the cheapest flow along the graph. It ships switched off.

**Worked example.** Ladder 3M, 6M, 1Y of one ticker, only 6M lit at +1 vol point. Precision and Layered: 3M $+2.00$, 1Y $+0.50$, because $\beta = T_{\text{informer}}/T_{\text{receiver}}$, whatever the precision. Smooth field at its defaults: $+0.89$ at both ends, since its calendar edges carry $\beta = 1$.

**In the app.** Graph lens top bar: the operator segment Layered | Precision; Smooth field opens from the Coupling pane's Advanced. Run each on the same lit set and compare the Diagnostics tab.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [prior.py](../../backend/volfit/graph/prior.py); [message.py](../../backend/volfit/graph/message.py); [harmonic_posterior.py](../../backend/volfit/graph/harmonic_posterior.py); [schemas.py](../../backend/volfit/api/schemas.py); [FINDINGS_dynamic_intraday.md](../../backend/backtest/FINDINGS_dynamic_intraday.md); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-39"></a>

## 39. One relation: amplitude and confidence

*6 · Graph inference*

A relation states how much a receiver moves when its informer moves, and how firmly. The two answers are separate numbers: $\beta$ and $\sigma$.

*1 · The statement: amplitude $\beta$, unexplained part of size $\sigma$*

$$
z_i=\beta_{ij}\,z_j+\varepsilon_{ij},\quad \varepsilon_{ij}\sim\mathcal N\bigl(0,\sigma_{ij}^2\bigr),\quad p_{ij}=\frac{1}{\sigma_{ij}^2}
$$

*2 · Default calendar amplitude: the ratio of maturities*

$$
\beta_{ij}=\Bigl(\frac{T_j}{T_i}\Bigr)^{\alpha_T},\qquad \alpha_T=1
$$

*3 · Each relation adds one rank-one term to the precision matrix*

$$
Q_{\mathrm{msg}}=\sum_{j\to i}p_{ij}\,u_{ij}u_{ij}^\top,\qquad u_{ij}=e_i-\beta_{ij}\,e_j
$$

*4 · What the receiver hears, if its informers were known*

$$
z_i\,\big|\,z_{\mathrm{informers}}\;\sim\;\mathcal N\Bigl(\sum_j\frac{p_{ij}}{q_i}\,\beta_{ij}\,z_j,\ \frac{1}{q_i}\Bigr)
$$

| Symbol | Meaning |
| --- | --- |
| $z_i,\ z_j$ | ATM change at receiver $i$ and informer $j$; 0.01 is one vol point |
| $\beta_{ij}$ | Amplitude: receiver move per unit informer move |
| $\varepsilon_{ij},\ \sigma_{ij}$ | The part of the move the relation leaves unexplained, and its standard deviation |
| $p_{ij}$ | Relation precision $1/\sigma_{ij}^2$, per $\text{vol}^2$ |
| $T_i,\ \alpha_T$ | Years to expiry (days / 365.25); shape exponent, 1 by default |
| $e_i,\ u_{ij}$ | Unit vector at node $i$; the factor's direction $e_i - \beta_{ij}e_j$ |
| $Q_{\mathrm{msg}}$ | The relations' precision matrix: $z^\top Q_{\mathrm{msg}}z = \sum p_{ij}(z_i-\beta_{ij}z_j)^2$ |
| $q_i$ | Incoming precision: $\sum_j p_{ij}$ over the informers of $i$ |

A relation has two ends: the informer, j, and the receiver, i. Line one is the whole statement: the receiver's change equals beta times the informer's change, plus a part the relation does not explain, epsilon, of size sigma. Beta is the amplitude. Sigma is the confidence; p, one over sigma squared, says the same thing as a precision. Everything is in the receiver's units: vol points of its ATM level.

Line two is the default amplitude of a calendar relation: the ratio of maturities, informer over receiver, to the power alpha-T, which is one by default. Why the ratio: total variance is sigma squared T. A small ATM change z moves it by about two sigma T z. If the same amount of total variance arrives at both maturities, and their vol levels are similar, the changes are inversely proportional to maturity. Plus one point at six months reads as plus two at three months and plus a half at one year. It is a chosen scaling, accurate for small moves and similar vols, and the day-horizon data identify it only weakly — so it is held for what it means.

Line three: the penalty of one relation is p times the squared miss, z-i minus beta z-j. As a matrix it is rank one: p times u u-transpose, with u equal to e-i minus beta e-j, where e-i is the unit vector at node i. It touches two nodes only, and it is never negative, whatever the sign of beta. The relations' precision matrix, Q-msg, is the sum of these terms: sparse, and valid by construction.

Line four is what a receiver hears. If its informers' changes were known, its best estimate is the average of their messages — each message is beta times the informer's change — weighted by the precisions, p-i-j over q-i. The precisions add up to q-i, the incoming precision. Two informers at the same p that disagree cancel, and the receiver's precision doubles: disagreement is information, not silence.

So amplitude and confidence do not mix. With one known informer, the receiver's mean is beta z-j whatever p is. Halving the trust widens the band; it does not shrink the move. In a larger network p can change a mean indirectly, by changing how much each of several competing informers counts. That is weighting, not shrinking.

The strip is the reference ladder. Six months lit at plus one point, three months and one year dark, at Desk strength. Three months receives beta two: plus 2.00, with a one-sigma band of 2.94 points: the relation's own sigma, which the next slide's calendar rule sets from the maturity gap — root of 0.97 plus root-gap, over 1,700 — 2.94 at a quarter-year gap, 3.14 at a half-year. One year is the informer of the six-month to one-year relation — the automatic calendar relations always make the shorter expiry the receiver — so it is read backwards: beta one half, sigma halved from 3.14 to 1.57. Plus 0.50. Scale every precision up by a hundred and the moves do not change; with six months fixed, the bands shrink tenfold.

**Transition:** the next slide is the app's editor for exactly these numbers — the relation card — and the reverse reading we just used.

**If asked why the arrow does not make the relation one-way:** in the Precision operator one relation is one symmetric Gaussian term. Observing the receiver legitimately informs an uncertain informer. The arrow fixes the units and the bookkeeping, not causality. One-way influence is a directed arc in the Layered operator.

**If asked about a negative beta:** it is allowed, and the term stays a valid penalty. The canvas draws such an arrow in rose.

**Worked example.** 6M lit at $+1$ point, 3M and 1Y dark. 3M: $\beta = 0.5/0.25 = 2$, so $+2.00$ with $1\sigma = 2.94$ points. 1Y is the informer of the 6M–1Y relation (the shorter expiry receives), so it is read backwards: $\beta = 1/2$, $\sigma = 3.14/2$, so $+0.50 \pm 1.57$. The two $\sigma$ are the next slide's calendar rule, $\sigma = \sqrt{(0.97 + \sqrt{\text{gap}})/1700}$: 2.94 at a 0.25-year gap, 3.14 at 0.5. Multiplying every $p$ by 100 keeps the moves and divides the bands by 10.

**In the app.** Coupling pane: the live line '6M informs 3M: +1.00 pt → +2.00 pt message · relationship uncertainty 2.94 pt' follows the dials.

**Sources.** [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [message.py](../../backend/volfit/graph/message.py); [graph_message_golden.json](../../backend/tests/fixtures/graph_message_golden.json).

<a id="slide-40"></a>

## 40. Calendar and cross-asset relation controls

*6 · Graph inference*

Two sliders set the default confidence of every automatic relation. Clicking an arrow opens the relation card, which edits that one relation: its confidence $\sigma$, its amplitude $\beta$ and, in Layered, its direction.

*1 · Calendar relation between expiries $T_i$ and $T_j$: confidence falls slowly with the gap*

$$
p_{ij}=\frac{p_0}{\varepsilon_T+\sqrt{|T_i-T_j|}},\qquad \sigma_{ij}=\frac{1}{\sqrt{p_{ij}}}
$$

*2 · The same relation read from the other end: same penalty, the other node's units*

$$
p\,(z_i-\beta z_j)^2=p\beta^2\Bigl(z_j-\frac{z_i}{\beta}\Bigr)^2\;\Rightarrow\;\beta_{\mathrm{rev}}=\frac{1}{\beta},\ \ \sigma_{\mathrm{rev}}=\frac{\sigma}{|\beta|}
$$

This slide is the editor for the numbers of the previous one, at two levels. The Coupling pane sets the defaults for whole classes of relations with two sliders. The relation card, which opens when you click an arrow, edits one relation.

Line one is the default confidence of a calendar relation. Its precision is p-zero divided by epsilon-T plus the square root of the maturity gap; sigma is one over the root of that. Both constants were fitted on stored day-over-day moves of adjacent expiries: p-zero is 1,700 per vol squared, epsilon-T is 0.97. Epsilon dominates, so the confidence is nearly flat in the gap: 2.55 points at one week, 2.94 at three months, 3.40 at one year.

The Calendar slider moves p-zero. Its readout, 2.43 points, is the sigma at a reference gap — the gap where epsilon plus root-gap equals one — so a single number summarises the whole curve. Cross-asset relations, between names at the same expiry, get amplitude one and one constant precision, 13,000 per vol squared: 0.88 of a point. That seed was measured on ticker medians, so it is on the confident side; the Cross-asset slider is there to loosen it.

Line two is the reverse reading. One relation is one penalty term, p times the squared miss of z-i against beta z-j. Written from the other end, the same term is p beta squared times the squared miss of z-j against z-i over beta. So read backwards the amplitude is one over beta and the sigma is sigma over beta. The card prints that on its last line. It is the same relation in the other node's units, not a second relation.

The strip is the MSFT card of 24 September: September 2027 informs April 2027. Beta is 358 over 204 days, 1.755. The gap is 154 days, 0.422 years, root 0.649; plus 0.97 gives 1.619; 1,700 over that is 1,050; one over its root is 3.09 points — the AUTO sigma on the card. Read backwards: beta 0.57, sigma 1.76.

The card's three fields. Confidence: AUTO, which is line one, or a value you type. Amplitude: the maturity ratio by default, editable, with a link across the three handles. Semantics, which only Layered reads: reciprocal — every automatic relation is reciprocal — or directed, a one-way arc, which the next slides explain.

Editing follows one rule: what you see is what runs. Every slider move stages a draft. Live re-solves the draft as a preview that records nothing. Run solves it and records the result. Apply makes the draft the active configuration, with an entry in the event log; Discard reverts.

**Transition:** with the relations and their confidences set, the next slide solves them all at once, and shows why a source reached by two routes must still count once.

**If asked about Desk and Learned under Advanced:** they set the amplitude level of the Precision solve. Desk passes the full beta; Learned passes the share measured on stored day-over-day moves, 0.23 for calendar and 0.39 for cross-asset relations. The Layered solve, as built today, always passes the full beta and does not read this switch.

**If asked whether to add the reverse arrow:** under reciprocal semantics, no — the reverse is already implied by line two. The plus-reverse button adds a second, explicit relation, which only means something for a directed arc; two directed arcs facing each other form a cycle, which the Layered solve rejects.

**Worked numbers, the MSFT card.** Gap 154 days $= 0.422$ years, $\sqrt{0.422} = 0.649$: $p = 1700/(0.97 + 0.649) = 1050$, $\sigma = 1/\sqrt{1050} = 3.09$ points. $+1$ point in September 2027 predicts $+1.755$ in April 2027, give or take $3.09$; read backwards, $+1$ in April predicts $+0.57$ in September, give or take $1.76$.

**Visual.** 24 September, MSFT relation card: 17 Sep 2027 informs 16 Apr 2027. $\beta = 358/204 = 1.755$, the ratio of days to expiry, and $\sigma = 3.09$ points from line 1; read backwards (bottom left), $\beta = 0.57$ and $\sigma = 1.76$ points.

**In the app.** Graph lens: the Coupling pane's two sliders; click an arrow for its card; Advanced holds Desk | Learned, the amplitude level of the Precision solve.

**Sources.** [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [message.py](../../backend/volfit/graph/message.py); [graph_dynamic.py](../../backend/volfit/api/graph_dynamic.py); [RelationCard.tsx](../../frontend/src/components/graphshell/RelationCard.tsx); [PolicyPane.tsx](../../frontend/src/components/graphshell/PolicyPane.tsx); [ROADMAP.md](../../ROADMAP.md).

<a id="slide-41"></a>

## 41. The joint posterior and shared information

*6 · Graph inference*

All relations and all lit changes are solved together, one linear system per handle. A source reached by two routes then counts once.

*1 · Posterior precision: relations, anchors, lit observations*

$$
Q^{+}=Q_{\mathrm{msg}}+\mathrm{diag}(\kappa)+\sum_{s\,\in\,\mathrm{lit}}r_s\,e_se_s^{\top}
$$

*2 · Posterior mean and covariance*

$$
Q^{+}\,\widehat z=\sum_{s\,\in\,\mathrm{lit}}r_s\,d_s\,e_s,\qquad \Sigma^{+}=\bigl(Q^{+}\bigr)^{-1}
$$

*3 · A lit change is uncertain twice: today's fit and the baseline*

$$
\frac{1}{r_s}=\frac{1}{r_s^{\mathrm{fit}}}+\frac{1}{p_s^{0}}
$$

*4 · Reported $1\sigma$: the marginal; a dark node adds its baseline once*

$$
\mathrm{sd}_i=\sqrt{\Sigma^{+}_{ii}}\ \ \text{(lit)},\qquad \mathrm{sd}_i=\sqrt{\Sigma^{+}_{ii}+1/p_i^{0}}\ \ \text{(dark)}
$$

| Symbol | Meaning |
| --- | --- |
| $\widehat z,\ \Sigma^+$ | Posterior mean of the changes, and their covariance |
| $Q_{\mathrm{msg}}$ | The relations' precision matrix, previous slides |
| $\kappa_i$ | Pull toward zero, $p_{\max}(1-\rho)/\rho$, $p_{\max}$ the node's firmest relation; 0 at Desk |
| $e_s,\ d_s$ | Unit vector and observed change at lit node $s$ |
| $r_s$ | Precision of $d_s$: fit and baseline combined |
| $r_s^{\mathrm{fit}}$ | $1/\mathrm{rms}^2$, cut for few quotes, wide spreads, old data |
| $p_i^0$ | Baseline precision: source tier, cut by age and transport; $\times 0.25$ if dark |
| $q_i$ | Incoming precision $\sum_j p_{ij}$: conditional, not the band |

Each relation gave one penalty term. Now we put them together with the data and solve once, for each handle. This is the Precision operator's solve; the Layered completion uses the same algebra, with its fresh lit nodes fixed.

Line one: the posterior precision, Q-plus, has three parts. Q-msg, the relations. A diagonal of kappas: a pull toward zero change, which is zero at Desk strength and set by the Learned level otherwise. And for each lit node s, its observation precision r-s on the diagonal; e-s is the unit vector at s. The Note writes that last sum as H-transpose R H.

Line two: the mean solves one linear system — Q-plus times z-hat equals the lit changes weighted by their precisions — and the covariance is the inverse. The code works group by connected group, checks each block is positive definite with a Cholesky factorisation, and inverts it. The dense algebra is sized for universes of a hundred to a thousand nodes.

Line three: a lit change is a difference of two estimates, today's fit minus the baseline. Both are uncertain, so their variances add. The fit precision is one over the fit's rms squared, cut for few near-the-money quotes, for wide spreads and for old data. The baseline precision comes from the prior's source, its age and how far it was transported.

Line four: the reported one-sigma is the marginal, the diagonal of the covariance. For a lit node the baseline is already inside r-s. For a dark node its own baseline variance is added here, once. Then a floor: a dark node's ATM band cannot be narrower than a set fraction of that name's recent innovations.

Why solve jointly: the strip. A is lit, with variance one over p. Three relations, A to B, A to C and B to C, each with precision p and beta one. C hears A twice: directly, and through B. The relation noise on the two routes is independent — one over p direct, two over p through B — and combines in parallel to two over three p. But A's own uncertainty is common to both routes and enters once: plus one over p, so five over three p. Treat the two routes as independent messages and A's uncertainty is averaged down as if there were two As: six over five p. That is 28 percent too little variance, 39 percent too much confidence.

Which number is the confidence: the incoming precision, q-i, is the sum of the precisions arriving at a node — what it would know if its informers were exact. They are not. On 24 September the dark AAPL February node had q 29,642 per vol squared: a conditional sigma of 0.58 of a point. Its final band was plus or minus 4.35 points. The final band is the one to read; the Inspector shows both.

No lit path: a group of nodes with no lit node in it is never solved into a number. Its change stays zero — the prior — with a flag and a band of one typical move, about three points on the ATM level.

**Transition:** Precision treats every relation as symmetric and has no memory. The next slide adds the two things a desk often wants — one-way influence, and a memory of each name's own dislocation: the Layered operator.

**If asked why not pass messages node by node, as in belief propagation:** on a graph with loops, local message passing can count a source more than once — exactly the strip's error. The joint solve is exact for any topology at this size.

**If asked about correlated informers, say SPY and QQQ on one macro shock:** the joint solve prices shared routes, but a common factor behind two sources is not modelled; q adds their precisions as if they were independent. That is recorded as open work.

**Worked example.** A lit with variance $1/p$; relations A–B, A–C, B–C, all $\beta = 1$ and precision $p$. The routes to C, direct ($1/p$) and via B ($2/p$), combine to $2/(3p)$; A's own $1/p$ enters once: $\mathrm{Var}(z_C) = 5/(3p)$. Independent routes would count A twice: $6/(5p)$, 28% too small; at $\sigma = 1$ point, 1.10 against 1.29.

**Sources.** [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [message_posterior.py](../../backend/volfit/graph/message_posterior.py); [graph_message.py](../../backend/volfit/api/graph_message.py); [precision.py](../../backend/volfit/graph/precision.py); [idio.py](../../backend/volfit/graph/idio.py); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md).

<a id="slide-42"></a>

## 42. Layered propagation and residual memory

*6 · Graph inference*

Layered runs in two layers: one-way arcs first, where a target's mark is its sources' prediction plus its own remembered dislocation; then the reciprocal completion.

*1 · Layer 1, directed arc $j \to i$: the sources' prediction $s_i$ plus the target's residual $u_i$*

$$
m_i=\underbrace{\sum_j\frac{p_{ij}}{q_i}\,\beta_{ij}\,m_j}_{s_i}\;+\;u_i
$$

*2 · The residual: set when the target prints, then halved every $H$ days*

$$
u_i\;\leftarrow\;d_i-s_i,\qquad u_{i,t+\Delta}=2^{-\Delta/H}\,u_{i,t}
$$

*3 · Layer 2: fresh lit nodes fixed at $d_{\mathrm{lit}}$; the layer-1 marks as soft anchors*

$$
\Bigl(Q_{\mathrm{free,free}}+\mathrm{diag}\,\tfrac{1}{V}\Bigr)\,\widehat z_{\mathrm{free}}=-\,Q_{\mathrm{free,lit}}\,d_{\mathrm{lit}}+\frac{m}{V}
$$

Precision is symmetric and has no memory: every relation works both ways, and nothing is carried from one Run to the next. Layered adds both things, in two layers.

Layer one is the directed arcs, evaluated sources first. Line one: along an arc from source j to target i, the target's mark is the sources' prediction — the same precision-weighted, beta-mapped average of their marks as on the relation slide, called s, the systematic part — plus u, the target's own residual: the part of its last print the sources did not explain. The arcs must form a graph without cycles; a directed cycle blocks the Run at preflight.

Line two is the memory. When the target prints fresh data, its residual is reset to the print minus the systematic prediction. The sources are never written: that is the cut. A single name printing cheap does not mark the index down. Between prints the residual decays, halving every H days. H is never by default, so the residual is carried flat until the next print.

The plot is the smallest story, with beta one. The source moves to plus 13, and the dark target follows to plus 13. Then the target prints plus 10: its residual becomes 10 minus 13, minus 3. The source moves on to plus 14; the target marks 14 minus 3, plus 11. The source's path never moves on the target's print.

Line three is layer two: the reciprocal relations — calendar ladders, peers — complete every other node, exactly as on the operators slide. Fresh lit nodes, with data at most a day old, are fixed at their observed change d. The layer-one marks enter as soft anchors, each with its variance V: they inform their neighbours but cannot flow back to their sources. Older lit nodes enter the same way, as soft anchors at their last change.

What runs by default matters. The automatic relations are all reciprocal, so a default Run has no directed arcs — but the memory is on. Every Layered Run stores each fresh lit node's change. If that node is dark at a later Run, the stored change becomes its anchor, and at the default H it stays as it is until the node prints again, or until the dynamics settings are edited, which clears the store. Checked through the production code: a node lit at plus one point one day and dark the next marks plus 0.99 with its memory, plus 0.26 without.

The strip puts numbers on the half-life. With H five days and the source moving one day after the print, the residual is minus 3 times 2 to the minus one fifth, minus 2.61, so the target marks 11.39 instead of 11. After five days it is minus 1.5. The residual clock counts whole days, so two Runs on the same day see no decay.

In the app, the Inspector's Decomposition card prints the identity for every node: baseline plus systematic plus residual plus harmonic equals the mark. The Dynamics card under Fine-tune holds the fresh window, the half-life and the semantics defaults.

**Transition:** every operator ends with three numbers per node. The next slide turns them back into a full smile.

**If asked whether Layered is the best operator:** it is the default for its one-way and memory semantics, and the recorded evidence is mixed. Intraday replay on an ETF triangle over eight sessions: the best Layered arm reached 73.7 bp of ATM error with a half-life of 0.1 day, memoryless 80.6, never-forget 108.1 — and Precision 65.8. The memory pays within the session; carried flat, it hurt at every horizon measured.

**If asked why only acyclic arcs:** a directed cycle has no one-way order to evaluate. Two-way coupling belongs to the reciprocal layer, so the preflight blocks a Run that contains a directed cycle.

**Worked example.** $H = 5$ days, the source moving one day after the print: $u = -3 \times 2^{-1/5} = -2.61$, so the target marks $14 - 2.61 = +11.39$; after 5 days $u = -1.50$. With $H$ never, $u$ stays at $-3$ until the next print.

**Visual.** Illustrative, $\beta = 1$, $H$ never. The target follows its source to $+13$, then prints $+10$: residual $-3$. The source moves to $+14$; the target marks $14 - 3 = +11$. The source's path never reacts to the target's print.

**In the app.** Coupling ▸ Fine-tune ▸ Dynamics: fresh window, half-life, semantics; Inspector ▸ Decomposition: baseline + systematic + residual + harmonic = mark.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [dynamic_directed_harmonic_graph_framework.md](../../Docs/dynamic_directed_harmonic_graph_framework.md); [graph_dynamic.py](../../backend/volfit/api/graph_dynamic.py); [directed_state.py](../../backend/volfit/graph/directed_state.py); [temporal_state.py](../../backend/volfit/graph/temporal_state.py); [FINDINGS_dynamic_intraday.md](../../backend/backtest/FINDINGS_dynamic_intraday.md).

<a id="slide-43"></a>

## 43. Reconstructing and displaying an inferred smile

*6 · Graph inference*

The graph returns three numbers per node: ATM level, skew and curvature. The node's own earlier shape supplies the rest, so the rebuilt curve is always a valid LQD law.

*1 · Target handles: the baseline plus the graph's move*

$$
\hat y_i \;=\; y_i^{0}+\hat z_i
$$

*2 · Retarget the base slice: solve for three moves, shape modes held*

$$
y\bigl(\theta^{*}+U\delta+V\xi^{*}\bigr)\;=\;\hat y_i
$$

*3 · Band $\hat\sigma(k)\pm1.96\,\mathrm{sd}(k)$, first order in the handle sds*

$$
\mathrm{sd}(k)^{2}\;=\;\sum_{j=1}^{3}\Bigl(\frac{\partial\sigma(k)}{\partial y_j}\Bigr)^{2}\mathrm{sd}_j^{2}
$$

After a Run the graph holds, for every node, three numbers: the posterior ATM volatility, skew and curvature, each with a standard deviation. A smile needs far more than three numbers. This slide is how we go from three handles to a full curve, and what the band around it means.

Line one: the target. The baseline handles, y-zero, come from the transported prior; add the graph's posterior move, z-hat. On the capture, AAPL February 2027 had a baseline ATM of 25.4 percent and a move of minus 2.5 basis points; its skew went from minus 0.103 to minus 0.110, its curvature from 0.645 to 0.760.

Line two: the reconstruction. Take a base slice: the node's latest fit, or, if it has none, its transported prior. Write its LQD parameters as theta-star, plus three primary directions U scaled by delta, plus all the other shape modes, V times xi-star. The primary directions are the smallest parameter moves that change the three handles; the shape modes leave the handles unchanged to first order, and we hold them fixed. That is what keeps the base slice's wings. Newton solves for the three deltas until the slice's exact ATM total variance, skew and curvature hit the targets. Only parameters move, so the result is a genuine LQD law: positive density, no butterfly arbitrage, by construction.

Two edge cases. At an extreme target the Newton solve can fail; that node then shows no curve rather than a wrong one. And when the desk model is SVI or MCS, that family is fitted to the LQD curve on strikes with usable time value, so its handles can differ slightly from the targets.

Line three: the band. Each handle has a marginal posterior standard deviation. We push them through the reconstruction itself: bump each handle up and down, rebuild the slice, and read how the volatility at every strike moves. Square, weight by the handle's variance, sum: that is a standard deviation per strike, and the band is plus or minus 1.96 of it. The three handles are treated as independent here; their covariance is not in this band.

One more piece, the ATM floor. For any node without an observation, the ATM standard deviation may not be smaller than root 0.30 times sigma-I. Sigma-I is the ticker's recent unexplained ATM move: an exponentially weighted RMS of its recorded innovations, shrunk toward the universe average. It exists because in calm markets single names move for their own reasons, which the relations cannot see.

Now the strip, because the capture looks odd at first: a move of 2.5 basis points, and a badge saying plus or minus 4.4 points. The width is the floor, not the graph. AAPL's stored innovations come from two sessions in July, between 2.6 and 9.1 vol points; they give sigma-I of 7.95 points, and root 0.30 times 7.95 is 4.35. The 95 percent interval is 25.4 plus or minus 8.5, so 16.9 to 33.9 percent, exactly the Inspector's reading. On this capture, the band tells you about that stored history, not about the relations.

Provenance. The inferred curve is stored as a fit-like record tagged graph, so it is transported with the spot exactly like a fit: violet dash-dot, with the INFERRED badge naming the Run. It is never committed, never becomes a prior and never enters a calibration. A new Run, a recalibration or a prior change rebuilds it.

**Transition:** how good are these inferred marks? We hide nodes whose answer we know, and score.

**If asked why the violet curve follows the red quotes so closely:** its shape comes from this node's own earlier fit, made the same afternoon before the node was darkened. Only the three handles came from the graph. A fair test needs a base shape dated before the quotes it is scored on.

**If asked whether the band moves with the spot:** the curve does; the band is drawn in the drill-in from the Graph lens, at the current solve, together with the curve's RMS, share inside the spread and zeta against the node's quotes.

**Worked numbers, 24 September capture.** AAPL February 2027, dark: baseline $25.4\%$, graph move $-2.5$ bp. Its ATM sd is the floor $\sqrt{0.30}\,\sigma_I=\sqrt{0.30}\times7.95=4.35$ points, from AAPL moves stored in July. 95%: $25.4\pm1.96\times4.35$, so 16.9 to 33.9%.

**Visual.** AAPL 19 February 2027, dark, 24 September. Violet dash-dot: the smile inferred by the 16:17 UTC Run. Blue: the node's earlier fit, now stale. Red: its current quotes, not used by the Run. Badge: ATM $25.4\pm4.4\%$, one sd.

**In the app.** After a Run, a dark node's smile: the INFERRED · GRAPH badge and the violet curve. Opened from the Graph lens it adds the 95% band and RMS · in-band · $\zeta$ against the node's quotes.

**Sources.** [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [graph_reconstruct.py](../../backend/volfit/api/graph_reconstruct.py); [graph_inferred.py](../../backend/volfit/api/graph_inferred.py); [graph_band.py](../../backend/volfit/api/graph_band.py); [band.py](../../backend/volfit/models/lqd/band.py); [ortho.py](../../backend/volfit/models/lqd/ortho.py); [idio.py](../../backend/volfit/graph/idio.py).

<a id="slide-44"></a>

## 44. Validation against a transported baseline

*6 · Graph inference*

Hide one lit node's calibration, infer it from everything else, and compare. The baseline to beat is the transported prior, not a flat surface.

*1 · Errors of the graph and of the baseline*

$$
e_i=\hat\sigma_{0,i}^{(-i)}-\sigma_{0,i}^{\mathrm{fit}},\qquad e_i^{0}=\sigma_{0,i}^{0}-\sigma_{0,i}^{\mathrm{fit}}
$$

*2 · Standardised residual: the error in units of its stated uncertainty*

$$
\zeta_i=\frac{\sigma_{0,i}^{\mathrm{fit}}-\hat\sigma_{0,i}^{(-i)}}{\sqrt{V_i^{(-i)}+1/r_i}}
$$

*3 · Coverage: share of nodes inside the 80% and 95% bands*

$$
\mathrm{cov}_p=\tfrac1n\,\#\bigl\{i:\ |\zeta_i|\le z_p\bigr\},\qquad z_{80}=1.28,\ \ z_{95}=1.96
$$

The question is not whether the graph beats a flat surface. It is whether it adds anything beyond the transported prior, which already carries the earlier shape and the spot rule. So the comparison column is the transported prior, with no propagation at all.

The procedure. Take one lit node that has a calibration. Remove that calibration from the observations, solve the graph from everything else, and read the posterior ATM volatility at the node. Put it back and take the next one. Thirty-nine nodes: thirty-nine solves per operator. Nodes whose prior is today's own fit are left out, because that test would be circular.

Line one: two errors per node. e-i is the graph's prediction minus the calibrated ATM volatility; e-i-zero is the transported prior minus the same calibration. RMSE is the root mean square of each over the nodes.

Line two: the standardised residual, zeta. The same error, divided by the uncertainty the model stated: the posterior variance at the withheld node plus the variance of the node's own calibration, one over r-i. An example: the node calibrates at 24.0 percent, the graph predicted 23.6, the posterior sd is 30 bp and the node's own sd 10 bp. The error is 40 bp, the combined sd is the root of 900 plus 100, 31.6 bp, so zeta is 1.26.

Line three: coverage. If the bands are right, zeta behaves like a standard normal: 80 percent of nodes within 1.28, 95 percent within 1.96. The example node, at 1.26, sits just inside the 80 percent band. The screen computes both coverages from the zetas.

Now the table. The smooth field has the lowest RMSE, 36.7 against 38.7 for the prior: 2 bp, five percent. But its zeta standard deviation is 0.11: its stated uncertainty is about nine times the errors it makes, and every node sits inside even the 80 percent band. Precision messages: 38.5 bp, close to the prior; zeta standard deviation 0.72; 35 of 39 nodes inside the 80 percent band and 37 inside 95. Slightly wide, much closer to the right width.

Why the baseline is so hard to beat here: the priors were saved earlier the same afternoon, so the prior already knows most of the answer. And 39 nodes on one day cannot separate two operators by 2 bp. Read this table as the readout, not as a ranking.

Leave-one-out removes only the current calibration; it does not make the prior independent of the target. A real test seeds the priors before the scored time and never lets a scoring pass write stored state. The offline benchmark does that: chronological, over three historical regimes, with gates written before the run. The link beside the button opens it.

**Transition:** validation says how good the marks are. The next slide asks where one more quote would improve them most.

**If asked which operator is better:** on the recorded daily benchmark they tie, full leave-one-out ATM RMS 280.9 bp for learned messages against 279.3 for the smooth field. On the intraday replay they separate: messages 65.8 bp, the smooth field 168.6, pure transport 172.7. That intraday result is why messages became the Options default on 27 July.

**If asked whether a withheld node gets the band floor of the previous slide:** yes. A withheld node is unobserved, so its ATM band is floored like a dark node's. On this store the floor comes from July records for SPY, AAPL and NVDA, 3.6 to 10.5 vol points, which widens those nodes' bands.

**Worked numbers, 24 September table.** Smooth field: RMSE 36.7 bp, 2.0 better than the baseline's 38.7, but $\zeta$ std 0.11 and 39 of 39 inside 80%: bands about nine times too wide. Messages: 38.5 bp; $\zeta$ std 0.72; 35 of 39 inside 80%, 37 inside 95%.

**Visual.** 24 September, Validation ▸ Compare operators (LOO), 39 held-out nodes. Same day, universe and settings; only the operator differs. The transported prior carries no stated uncertainty here, so it has no $\zeta$ or coverage.

**In the app.** Graph drawer ▸ Validation ▸ Compare operators (LOO): one solve per held-out node and operator, so start it while talking.

**Sources.** [14_graph_three_priors.md](../../Docs/handoff/notes/14_graph_three_priors.md); [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [graph_backtest.py](../../backend/volfit/api/graph_backtest.py); [hyper.py](../../backend/volfit/graph/hyper.py); [useLooComparison.ts](../../frontend/src/state/useLooComparison.ts).

<a id="slide-45"></a>

## 45. Choosing the next observation

*6 · Graph inference*

Before a quote exists, the posterior covariance says how much it would reduce uncertainty, here and at every correlated node. The plan ranks nodes by that.

*1 · Covariance after the quote: a rank-one update*

$$
\Sigma' \;=\; \Sigma-\frac{\Sigma_{\cdot c}\,\Sigma_{c\cdot}}{\Sigma_{cc}+1/r_c}
$$

*2 · Variance removed at each node $i$*

$$
\Delta V_i \;=\; \frac{\Sigma_{ic}^{2}}{\Sigma_{cc}+1/r_c}
$$

*3 · Score: the removed variance, summed with exposure weights*

$$
G(c)\;=\;\sum_i w_i\,\Delta V_i
$$

Suppose you can ask a broker for one more quote. Which node should it be? The posterior answers that before the quote exists.

Line one: Gaussian conditioning on one noisy measurement. Sigma is the posterior covariance of ATM volatility across all nodes after the Run. Quoting node c with noise variance one over r-c subtracts from Sigma the outer product of its column c, divided by the candidate's own variance plus the quote noise. Nothing in it depends on what the quote will say, only on how precise it will be. So we can rank the candidates before anything is quoted; the value moves the means once it arrives.

Line two reads the diagonal of that update. At node i the variance falls by Sigma-i-c squared over the same denominator. At the candidate itself that is almost all of its variance when the quote is precise. At another node it depends on how correlated that node is with the candidate.

Line three: the score adds those drops over the universe, each with an exposure weight w-i, one per ticker by default, so a desk can steer the ranking toward the books it holds. The screen shows the score as a share of all the ATM variance left in the universe: minus 49.5 percent sigma-squared means one quote at XOM April would remove about half of it.

Two details. The assumed precision r-c comes from the candidate's own chain when it has quotes: fit RMS, quote count near the money, spread. Otherwise it is the median lit node's. And the idiosyncratic band floor is left out, because quoting other nodes can never remove it.

The strip, by hand. Two dark nodes: c with sd 60 bp, j with sd 50 bp, correlation 0.8, so their covariance is 2400 bp squared. A quote at c with sd 15 bp: the denominator is 3600 plus 225, 3825. At c the sd falls from 60 to 14.6 bp. At j the drop is 2400 squared over 3825, 1506, so its sd falls from 50 to 31.5 bp, at a node nobody quoted. Together, 80 percent of their variance is gone.

The capture. The top four are the April 2027 nodes of XOM, MSFT, AAPL and NVDA. All four are dark, no ticker has a lit April node, and the automatic cross relations tie same-expiry nodes of different names together. So each is uncertain and each is correlated with the other three: quoting any one informs all four, hence three nearly equal scores. AAPL February 2027 comes fifth at 8 percent: it sits between two lit AAPL expiries, so the graph already pins it well.

The tag on XOM, resolves competing signals, means its incoming messages disagree in sign, each by more than a tenth of a vol point. A quote there settles the vote.

Everything here is conditional on the model: the relations, their precisions, the assumed quote noise. A very noisy quote is worth little even at a poorly known node. And the cost of obtaining a quote is not in the score; that is the desk's call.

**Transition:** that closes the graph section. Next, what all of this costs in computing time.

**If asked whether it re-solves the graph for each candidate:** no. It is closed form on the solved covariance, one rank-one formula per candidate, no refit.

**Illustrative calculation.** Nodes $c$ and $j$, sd 60 and 50 bp, correlation 0.8: $\Sigma_{jc}=2400\ \mathrm{bp}^2$. Quote $c$ at sd 15 bp: denominator $3600+225=3825$. At $c$, sd 60 → 14.6 bp; at $j$, $\Delta V=2400^2/3825=1506$, sd 50 → 31.5 bp. 80% of their variance gone.

**Visual.** 24 September, Observation plan ▸ Rank: the five best places to quote next. The April 2027 nodes lead, three of them tied near 49.4%; XOM's incoming messages disagreed in sign. AAPL February 2027, between two lit expiries, would remove 8.1%.

**In the app.** Graph drawer ▸ Observation plan ▸ Re-rank: hover a row for sd before → after and the nodes it also shrinks; click to open its smile.

**Sources.** [14_graph_messages.md](../../Docs/handoff/notes/14_graph_messages.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [stage3.py](../../Docs/deck/demo_2026-09-24/stage3.py); [select.py](../../backend/volfit/graph/select.py); [graph_select.py](../../backend/volfit/api/graph_select.py); [graph_message.py](../../backend/volfit/api/graph_message.py); [planAnnotations.ts](../../frontend/src/lib/planAnnotations.ts).

<a id="slide-46"></a>

## 46. Where calibration time is spent

*7 · Computation and inspection*

One SPY ticker with nine expiries: the smiles take a third of a second, the local-volatility surface about three seconds. Warm-starting the surface saves optimiser evaluations: 20 instead of 66.

*1 · One ticker's Calibrate job: the smiles, then the surface*

$$
T_{\mathrm{job}}\;\approx\;T_{\mathrm{LQD}}+T_{\mathrm{LV}}
$$

*2 · Local-volatility stage: fixed work plus optimiser evaluations*

$$
T_{\mathrm{LV}}\;\approx\;T_{\mathrm{fix}}+n_{\mathrm{eval}}\,t_{\mathrm{eval}}
$$

*3 · The two recorded runs, cold and warm parameter start (seconds)*

$$
0.3+66\times0.038\approx2.8,\qquad 0.3+20\times0.030\approx0.9
$$

Every number here comes from one recorded experiment: the evening of 23 September, SPY after the US close, real NBBO from Massive, nine expiries from two days to one year, 875 quotes fitted to mids, on this laptop, an i7-12700H, with the desk app running, one worker. They describe that workload; a different chain will give different numbers.

The bars. Preparing the ladder, meaning forwards, removing the early-exercise premium and inverting quotes: 0.354 seconds. Fitting the nine LQD-24 smiles with the calendar screen: 0.338 seconds. The local-volatility surface: 2.82 seconds from a cold parameter start, 0.89 seconds from a warm one.

Line one: a Calibrate job for one ticker is the smiles, then the surface. Measured as one job it took 3.34 seconds; the two stages timed on their own add to 3.16. Separately timed medians need not add up exactly to a job measured whole.

Line two: the local-volatility stage has a fixed part and a part proportional to the number of optimiser evaluations. Each evaluation marches the forward Dupire equation over the 368 by 116 lattice and computes its sensitivities to the 253 vertex variances.

Line three puts the recorded numbers in. About 0.3 seconds outside the optimiser loop in both runs: the seed, three post-fit reprices, the response. Cold: 66 evaluations at about 38 milliseconds each. Warm, seeded from the previous surface: 20 evaluations at about 30. Same final surface either way: 3.61 bp in the fitting operator, 5.12 bp on the converged reprice. The warm start saves evaluations.

Three kinds of reuse save three different things. The warm start saves optimiser evaluations. The prepared-quote cache saves the exercise-premium removal and the inversions: a change of fit settings reuses them. The compiled-kernel cache saves compilation: a restarted process loads the kernels from disk.

Parallelism. The calibration pool, by default one worker per core minus one and at most eight, fits different tickers at the same time. It does not split one surface: pooled, the SPY surface took 2.90 seconds against 2.82 serial. Starting the pool costs about 4 seconds once per session, and the app starts it while the quotes are being prepared.

Around the job: the live NBBO fetch for this ladder was 1.2 to 1.4 seconds, and reconstructing a past instant from Massive history 12.7 seconds. For a single smile the fetch is the slowest step: after it, one node takes about 50 milliseconds, the forward 4.5, the quotes 17, the LQD-24 fit 24.

**Transition:** speed is one property of a result. The next slide is how to read its quality before it is published.

**If asked about the default order 16 rather than 24:** on the same node LQD-16 took 26 ms against 24 for LQD-24, and the RMS differed by 0.04 bp. The order is an accuracy setting, not a speed setting.

**If asked whether the calendar constraint costs time:** not on a consistent ladder. The solver screens first and repairs only proven violations; here it found none, 338 against 340 milliseconds with the constraint off. When a repair does fire it costs time, and this ladder does not measure that.

**Recorded 23 September.** Calibrate job 3.34 s, measured as one job; its two fit stages timed alone add to $0.34+2.82=3.16$ s. Before it: live fetch 1.2 to 1.4 s, quote preparation 0.35 s. One smile alone, after the fetch: about 50 ms.

**Visual.** Recorded 23 September after the US close: SPY Massive NBBO, mid target, i7-12700H laptop, one worker. Medians of three runs (the warm LV bar: one run). Cold: seeded from the LQD fits; warm: seeded from the previous surface.

**Sources.** [presentation_prep_QA_2026-09-23.md](../../Docs/deck/presentation_prep_QA_2026-09-23.md); [q3_chain.json](../../Docs/deck/prep_2026-09-23/q3_chain.json); [q3_chain.py](../../Docs/deck/prep_2026-09-23/q3_chain.py); [affine_calib.py](../../backend/volfit/models/localvol/affine_calib.py); [affine_fit.py](../../backend/volfit/api/affine_fit.py).

<a id="slide-47"></a>

## 47. Reading fit quality and publication state

*7 · Computation and inspection*

The Quality lens reads cached fits only; it never refits. A lit node is ready when every gate passes; other diagnostics are shown but do not block.

*1 · Error of quote $i$ against its target band: zero inside*

$$
e_i=\bigl(\sigma(k_i)-\sigma^{\mathrm{hi}}_i\bigr)^{+}+\bigl(\sigma^{\mathrm{lo}}_i-\sigma(k_i)\bigr)^{+}
$$

*2 · Node RMS on the fit's own weights*

$$
\mathrm{RMS}=\Bigl(\sum_i\lambda_i\,e_i^{2}\Big/\sum_i\lambda_i\Bigr)^{1/2}
$$

| Gate | Ready requires | QQQ 18-Dec-26 |
| --- | --- | --- |
| Freshness | fit on current inputs; data under 120 min | current; 25 min |
| Fit error | $\mathrm{RMS}\le50$ bp | 2.3 bp, max 16.3 |
| Wing slopes | Lee $\beta_L,\beta_R\le2$ | 0.24, 0.03 |
| Calendar | $\min_u\,(G_{\mathrm{far}}-G_{\mathrm{near}})\ge-10^{-6}$ | $1.7\times10^{-17}$ |
| Butterfly | $g\ge0$ on the quoted range | min 0.164 at $k=-0.39$ |

The Quality lens is a read-only summary: it reads the cached calibrations and never triggers a fit. It grades lit nodes; the eight dark nodes are graph targets and are not graded here.

Line one: the error of one quote is measured against the fit target. With a band target, bid–ask or haircut, it is the distance outside the band, zero anywhere inside. With a mid target it is simply model minus mid.

Line two: the RMS weights those errors with the fit's own weights, lambda-i, the ones the calibration summed. So it reads: how well did the fit meet its own objective. In haircut mode, an RMS of 2 bp means the curve is almost everywhere inside the tightened bands; it does not mean the curve is 2 bp from the mids. The maximum matters too: QQQ December has an RMS of 2.3 bp, and its worst quote is 16.3 bp outside its band.

The table lists the gates; a node is ready only if all of them pass. Freshness: the fit was calibrated on the current inputs, otherwise it is stale, and the chain is under 120 minutes old. QQQ's was 25 minutes: amber past 20, not failing. Fit error: under a 50 bp budget. Wing slopes: Lee's limit of 2. Calendar: the exact minimum, over the whole line, of the far expiry's ledger minus the near one's, not below minus ten to the minus six. Butterfly: Durrleman's g, whose sign is the sign of the density, non-negative on the traded range.

Two of these also block an export: calendar and butterfly, together with any curve region below intrinsic. A publish containing such a node is refused; a draft can still be exported, stamped as a draft. Staleness, RMS and data age lower readiness but do not block the export.

Shown but not gating: arbitrage checks on the extrapolated wings, the filter's contamination flag, the count of screened quotes, the MCS calendar certificate. They inform; they do not block.

The strip. On 24 September, 38 of the 39 lit nodes were ready. The exception, QQQ February 2027, fits well at 2.2 bp. The sampled calendar screen passed; the exact certificate against January did not: a minimum gap of minus 0.1 bp of the forward, at k equals minus 1.70, deep in the put wing. One failure, and the node is not ready.

Each export writes a manifest: the chains, the settings and the artifact, hashed and chained to the previous publish, so a published surface can be reproduced later.

**Transition:** next, the whole sequence on two nodes, from quotes to this screen.

**If asked what stale means exactly:** something the fit depends on changed after it was made, a new chain, a forward, a setting, an edit, an event or a prior. The displayed curve is then the old fit transported, not a new calibration.

**Recorded 24 September.** 38 of 39 lit nodes ready. The exception, QQQ February 2027 (RMS 2.2 bp), fails the calendar certificate against January: minimum gap $-0.1$ bp of the forward at $k=-1.70$.

**Visual.** 24 September, Quality lens: publish ready 38/39, arbitrage flags 1 (QQQ), median RMS 6.6 bp, worst 26.5 bp (NVDA November 2026), LV surfaces 4/4 arbitrage-free. Card: QQQ December 2026.

**In the app.** Quality lens (Alt+5): tiles, per-ticker rollup, node table with Exceptions first; a node card's certificates and data age.

**Sources.** [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [_notes_parametric.json](../../Docs/deck/assets/shots_demo/_notes_parametric.json); [quality.py](../../backend/volfit/api/quality.py); [quality_gates.py](../../backend/volfit/api/quality_gates.py); [export_blockers.py](../../backend/volfit/api/export_blockers.py); [rms.py](../../backend/volfit/calib/rms.py); [calendar_certificate.py](../../backend/volfit/calib/calendar_certificate.py).

<a id="slide-48"></a>

## 48. A worked sequence on the 24 September desk

*7 · Computation and inspection*

One liquid node, QQQ December 2026, and one dark node, AAPL February 2027, followed from quotes to the publish check. Every value is read off the archived captures.

| Step | Where in the app | What to read on 24 September |
| --- | --- | --- |
| 1 · Market input | Parametric ▸ Table, QQQ 18-Dec-26 | chain 15:42:09 UTC; spot 736.05, forward 742.89, $T=0.233$; 225 strikes |
| 2 · One smile | Fit diagnostics card | LQD $N=24$, haircut target: ATM 20.5%, skew $-0.355$, curvature 4.01; $A_L=0.628$, $A_R=0.056$ |
| 3 · Expiry ladder | Stacked IV; Quality card | $w=\sigma^2T$ for 9 expiries, chip 1 cal. cross; December against November: gap $1.7\times10^{-17}\ge0$ |
| 4 · Spot move | Spot move card; Options ▸ Dynamics | SSR $R=1.5$: the fit stays, the curve is transported (strip below) |
| 5 · Earlier information | Fit switch; FILTER badge | Production against Free; filter gains $K$ 0.61, 0.11, 0.00 for ATM, skew, curvature |
| 6 · Dark node | Graph lens ▸ Inspector, AAPL 19-Feb-27 | baseline 25.4% (nearest-expiry prior), move $-2.5$ bp, $\pm435$ bp (1 sd); violet curve on its smile |
| 7 · Score and plan | Graph drawer ▸ Validation, Observation plan | 39 held out: 38.7, 36.7, 38.5 bp; next quote XOM 16-Apr-27, $-49.5\%$ of $\sigma^2$ |
| 8 · Publish check | Quality lens (Alt+5) | 38 of 39 ready; QQQ 19-Feb-27 fails the calendar certificate |

To finish the technical part, one pass through the whole calculation on the desk we staged on 24 September: a liquid node, QQQ December 2026, and a dark one, AAPL February 2027. Every value in the table is read off the archived captures.

Step one, the market input. The Table view shows what the fit will see: the chain stamped 15:42:09 UTC, spot 736.05, the parity forward 742.89, 0.233 years to expiry, 225 strikes. Check the time stamp and the forward before anything else.

Step two, one smile. LQD of order 24 on the haircut target: ATM 20.5 percent, skew minus 0.355, curvature 4.01, tail scales A-L 0.628 and A-R 0.056. The left tail is the heavy one, as expected for an index.

Step three, the ladder. Read total variance, w equals sigma squared T, across the nine expiries, not annualised volatility. The Quality card gives the calendar certificate against November: a gap of 1.7 times ten to the minus seventeen, so ordered.

Step four, move the spot. With the SSR rule at 1.5 the fit stays and the curve is transported. The strip: QQQ falls one percent, h is minus 0.01; the ATM volatility moves by R times skew times h, 1.5 times minus 0.355 times minus 0.01, plus 53 basis points, before any refit. Under sticky strike, R equals 1, it would be plus 35.5.

Step five, earlier information. The Fit switch compares the production fit with the free one; the FILTER badge gives the Kalman gains, 0.61 on the ATM, 0.11 on the skew, zero on the curvature: the filter trusts the new ATM a lot, the new curvature not at all.

Step six, the dark node. AAPL February 2027 has no observation. Its baseline is a nearest-expiry prior at 25.4 percent; the Run moves it by minus 2.5 bp, with one standard deviation of 435 bp, the band floor we explained earlier. Its smile shows the violet inferred curve.

Step seven, score and plan. Leave-one-out over 39 lit nodes: 38.7 bp for the transported prior, 36.7 for the smooth field, 38.5 for messages. The observation plan says the next quote should be XOM April 2027, which would remove about half the remaining ATM variance.

Step eight, the publish check. 38 of 39 nodes are ready; QQQ February 2027 fails the calendar certificate, and an export containing it would be refused.

**Transition:** that is the whole chain. One last slide to put it in one picture.

**If asked to replay a step:** each node opens by deep link, the node and the lens in the address, and the O key returns to any slide of this deck.

**Worked example, step 4.** QQQ falls 1%: $h=\log(F_1/F_0)=-0.01$. First-order ATM change $R\,s_0\,h=1.5\times(-0.355)\times(-0.01)=+53$ bp, with no refit. Sticky strike, $R=1$, would give $+35.5$ bp.

**In the app.** Open each node by link: /?node=QQQ|2026-12-18&activity=parametric, then /?node=AAPL|2027-02-19&activity=graph.

**Sources.** [README_parametric.md](../../Docs/deck/assets/shots_demo/README_parametric.md); [README_graph.md](../../Docs/deck/assets/shots_demo/README_graph.md); [_notes_parametric.json](../../Docs/deck/assets/shots_demo/_notes_parametric.json); [README.md](../../Docs/deck/demo_2026-09-24/README.md); [ssr.py](../../backend/volfit/dynamics/ssr.py); [useDeepLink.ts](../../frontend/src/state/useDeepLink.ts).

<a id="slide-49"></a>

## 49. One calculation, read in dependency order

*Close*

Every number on the desk is observed, fitted, carried or inferred. Each step between them adds one assumption, and the app shows it beside the number.

To close, the one idea that organised the talk. Every number on the desk is one of four kinds: observed, fitted, carried or inferred. Each step from one kind to the next adds one assumption, and the app shows that assumption next to the number it produced.

Observed. Raw quotes are not yet comparable. We synchronise them to one spot and one time, take the forward and the discount from put–call parity, and remove the early-exercise premium with the tree. The assumptions: the spot rule used for synchronisation, the dividend model, the tree.

Fitted. One smile per expiry, or one local-variance surface. A fit is only readable with its objective, mid, band or haircut, with its weights, its tail policy and its calendar coupling. LQD is a valid law for any parameters; the certificates check what a model does not guarantee by itself, across expiries and on the traded range.

Carried. Between calibrations the fit moves with the spot by the chosen rule. Where quotes are thin, a prior supplies what the market does not. Across time, the filter weighs a new estimate against the transported one. Each is visible: the transported curve, the prior's active rows, the filter's gain.

Inferred. For the dark nodes, the graph starts from the transported prior and adds a move carried by stated relations, with a marginal uncertainty. The result is rebuilt as a proper smile, drawn in violet, and it never comes back as a fit or a prior.

And dated. Every timing and every score belongs to the run that produced it: the 23 September SPY experiment for speed, the 24 September session for the captures, the validation table and the plan. Numbers from different runs are not added together.

Thank you. Questions are welcome, by topic. The O key opens the contents to jump to any slide, and the speaker notes carry the equations, the worked examples and the source files for each one.

**Sources.** [demo_speaker_notes_2026-09-24.md](../../Docs/deck/demo_speaker_notes_2026-09-24.md); [README.md](../../Docs/deck/demo_2026-09-24/rewrite/README.md); [README.md](../../Docs/deck/demo_2026-09-24/README.md).
