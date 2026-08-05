# Chapter 4 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch04/gen_figures.py` into `ch04_macros.tex`. Last write 2026-08-05.

| Macro | Value | Meaning |
|---|---|---|
| `\MacLvRatioBadQuotedSharePct` | `0.00` | same share restricted to the common quoted support of each expiry pair |
| `\MacLvRatioBadSharePct` | `0.5` | share of displayed (k, tau) cells where the Dupire ratio is inadmissible (negative calendar increment or g_D <= 0) |
| `\MacLvRatioLocMaxPct` | `61.5` | largest extracted local vol (%) on the common quoted support |
| `\MacLvRatioLocMinPct` | `9.0` | smallest extracted local vol (%) on the common quoted support |
| `\MacLvWrongCoarseMinPct` | `13` | smallest valid extracted local vol (%) in the 13-quote arm |
| `\MacLvWrongEdgePts` | `22` | max \|fitted - true\| local vol (vol points) anywhere on the common quoted support: the short-expiry span edges, where single rippled quotes meet weakly identified vertices |
| `\MacLvWrongFwdMaxPts` | `12.9` | max \|fitted - true\| local vol (vol points) along the two plotted cross-sections of the forward fit to the noisy quotes |
| `\MacLvWrongMaxSpikePct` | `73` | largest extracted local vol (%) in the naive pipeline |
| `\MacLvWrongNBad` | `14` | strikes at which the naive extraction returns negative variance or a nonpositive Durrleman factor |
| `\MacLvWrongQuoteRmsBp` | `49` | reprice rms (vol bp) of the forward fit to the rippled quotes: the noise stays in the residual, not the surface |
| `\MacLvWrongRippleBp` | `50` | amplitude (vol bp) of the deterministic alternating ripple |
| `\MacLvWrongTruthAtmPct` | `23` | true ATM local vol (%) at tau = 0.25 |
| `\MacLvSheetCols` | `24` | SPY sheet strike columns |
| `\MacLvSheetRows` | `9` | SPY sheet maturity rows |
| `\MacLvSheetVtx` | `216` | SPY sheet vertex count (= calibration parameters) |
| `\MacLvLatCflBound` | `0.0003` | CN monotonicity bound 2 dy^2/(v y^2) at the money on this lattice (the marching step 0.01 exceeds it) |
| `\MacLvLatCnMinDens` | `-36` | min discrete density under undamped Crank-Nicolson (plot window) |
| `\MacLvLatImplMinDens` | `0.0012` | min discrete density under fully implicit Euler (plot window) |
| `\MacLvIdentColY` | `0.45` | strike of the moved vertex column |
| `\MacLvIdentMaxDiffBp` | `22.6` | largest reprice change (vol bp) across every quote |
| `\MacLvIdentMovePts` | `10` | vol points taken off the unquoted deep-put column |
| `\MacLvIdentRmsDiffBp` | `2.5` | rms reprice change (vol bp) across every quote |
| `\MacLvInflMaxRel` | `\ensuremath{1.1\times10^{-8}}` | worst relative disagreement, analytic tangent vs central FD, over all vertices and expiries |
| `\MacLvInflVtx` | `50` | vertex count of the synthetic sheet |
| `\MacLvRtEvals` | `20` | objective evaluations of the synthetic fit |
| `\MacLvRtMaxErrBp` | `1.8` | max quote reprice error (vol bp), clean synthetic round trip |
| `\MacLvRtNQuotes` | `124` | synthetic quote count (four expiries) |
| `\MacLvRtRmsErrBp` | `0.6` | rms quote reprice error (vol bp), clean synthetic round trip |
| `\MacLvRtSurfMaxPts` | `3.10` | max \|fit - truth\| local vol (vol points), quote-covered region |
| `\MacLvRtSurfRmsPts` | `0.78` | rms \|fit - truth\| local vol (vol points), quote-covered region |
| `\MacLvNvdaButterflyMin` | `\ensuremath{-2.1\times10^{-13}}` | NVDA min divided second difference of the marched prices over every expiry (butterfly proxy) |
| `\MacLvNvdaCalendarMin` | `\ensuremath{-7.8\times10^{-16}}` | NVDA min adjacent-expiry increment of the marched prices at fixed y (calendar proxy) |
| `\MacLvNvdaConvBp` | `46.1` | NVDA all-quote rms (vol bp), refined operator |
| `\MacLvNvdaEvals` | `94` | NVDA objective evaluations (cold fit) |
| `\MacLvNvdaQuotes` | `506` | NVDA quote count (all expiries) |
| `\MacLvNvdaRmsBp` | `16.1` | NVDA all-quote rms (vol bp), fitting operator |
| `\MacLvNvdaVtx` | `207` | NVDA sheet vertex count |
| `\MacLvNvdaWorstConvBp` | `116.9` | NVDA worst per-expiry refined-operator rms (vol bp) |
| `\MacLvSpyButterflyMin` | `\ensuremath{-8.5\times10^{-13}}` | SPY min divided second difference of the marched prices over every expiry (butterfly proxy) |
| `\MacLvSpyCalendarMin` | `\ensuremath{-8.9\times10^{-16}}` | SPY min adjacent-expiry increment of the marched prices at fixed y (calendar proxy) |
| `\MacLvSpyConvBp` | `13.6` | SPY all-quote rms (vol bp), refined operator |
| `\MacLvSpyEvals` | `116` | SPY objective evaluations (cold fit) |
| `\MacLvSpyQuotes` | `1026` | SPY quote count (all expiries) |
| `\MacLvSpyRmsBp` | `2.7` | SPY all-quote rms (vol bp), fitting operator |
| `\MacLvSpyVtx` | `216` | SPY sheet vertex count |
| `\MacLvSpyWorstConvBp` | `28.2` | SPY worst per-expiry refined-operator rms (vol bp) |
