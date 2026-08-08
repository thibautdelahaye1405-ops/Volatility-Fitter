# Chapter 6 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch06/gen_figures.py` into `ch06_macros.tex`. Last write 2026-08-08.

| Macro | Value | Meaning |
|---|---|---|
| `\MacFwdLineFNaive` | `762.71` | naive whole-chain parity root (dollars) |
| `\MacFwdLineFResolved` | `767.92` | the reference implementation's resolved forward (dollars) |
| `\MacFwdLineGapBp` | `68` | resolved-minus-naive forward gap (bp of forward) |
| `\MacFwdLineGapDollars` | `5.2` | resolved-minus-naive forward gap (dollars) |
| `\MacFwdLineNPairs` | `158` | paired strikes on the running node's raw chain |
| `\MacFwdLinePiMaxDollars` | `609` | largest portfolio price on the board (dollars) |
| `\MacFwdLinePiMinAbsDollars` | `242` | magnitude of the most negative portfolio price (dollars) |
| `\MacFwdLineRateNaivePct` | `-0.24` | implied rate of the naive slope (percent) |
| `\MacFwdLineResidMaxDollars` | `4.8` | largest single residual of the naive line (dollars) |
| `\MacFwdLineRmsDollars` | `2.97` | rms residual of the naive parity line (dollars) |
| `\MacFwdLineSpanDollars` | `850` | range of the observable Pi across the board (dollars) |
| `\MacFwdLineSpotDollars` | `757.67` | SPY spot on the snapshot date (dollars) |
| `\MacFwdLineStraightPct` | `0.35` | rms residual as a percentage of the observable's range |
| `\MacFwdIdentCleanFwdErrBp` | `0.15` | clean rounded-board forward recovery error (bp, absolute) |
| `\MacFwdIdentCleanRateErrBp` | `1.0` | clean rounded-board rate recovery error (bp, absolute) |
| `\MacFwdIdentEpsCents` | `2` | quote-noise sd per mid (cents) |
| `\MacFwdIdentFwdPredBp` | `0.57` | predicted sd of the forward (bp of F) |
| `\MacFwdIdentFwdSdBp` | `0.57` | measured sd of the forward (bp of F) |
| `\MacFwdIdentLeverDollars` | `1.51` | lever arm F minus mean strike on the running board (dollars) |
| `\MacFwdIdentNStrikes` | `25` | paired strikes on the running synthetic board |
| `\MacFwdIdentRatePredBp` | `6.4` | predicted sd of the implied rate (bp) |
| `\MacFwdIdentRateSdBp` | `6.3` | measured sd of the implied rate (bp) |
| `\MacFwdIdentRatio` | `11` | rate-to-forward scatter ratio (both in bp) |
| `\MacFwdIdentRootSkk` | `90` | root strike dispersion sqrt(S_KK) (strike-dollars) |
| `\MacFwdIdentShortRateSdBp` | `63` | measured rate sd on the short-dated variant (bp) |
| `\MacFwdIdentShortT` | `0.05` | year fraction of the short-dated variant |
| `\MacFwdIdentTrials` | `2000` | Monte Carlo trials in the identifiability experiment |
| `\MacFwdMaskDeltaRatePct` | `2` | carry error of the coherent stale wing (percent) |
| `\MacFwdMaskFwdErrBp` | `13` | forward error under coherent staleness (bp, absolute) |
| `\MacFwdMaskNOut` | `0` | points trimmed in the masking experiment |
| `\MacFwdMaskNWing` | `5` | number of coherently stale wing quotes |
| `\MacFwdMaskRatePct` | `1.7` | implied rate under coherent staleness (percent) |
| `\MacFwdTrimErrBp` | `0.1` | forward error after the trim (bp, absolute) |
| `\MacFwdTrimNOut` | `1` | points trimmed in the staged single-outlier experiment |
| `\MacFwdTrimRawErrBp` | `4` | forward error of the raw fit (bp, absolute) |
| `\MacFwdTrimRawRatePct` | `4.8` | implied rate of the raw (untrimmed) fit (percent) |
| `\MacFwdTrimSigmaOut` | `120` | the stale quote's distance in robust sigmas |
| `\MacFwdTrimStaleDollars` | `1.20` | size of the staged stale-put error (dollars) |
| `\MacFwdLeverFwdDollars` | `101.5` | true forward of the asymmetric board (dollars) |
| `\MacFwdLeverKbarDollars` | `112.5` | mean strike of the asymmetric board (dollars) |
| `\MacFwdLeverKbarKernDollars` | `102.1` | kernel-weighted mean strike (dollars) |
| `\MacFwdLeverKernBpPerPct` | `0.31` | forward error per 1% rate error, spot-kernel level mean (bp) |
| `\MacFwdLeverKernLeverDollars` | `0.6` | lever arm of the spot-kernel level mean (dollars) |
| `\MacFwdLeverNaiveBpPerPct` | `50.0` | forward error per 1% rate error, intercept-over-slope (bp) |
| `\MacFwdLeverUnifBpPerPct` | `5.4` | forward error per 1% rate error, uniform level mean (bp) |
| `\MacFwdLeverUnifLeverDollars` | `11.0` | lever arm of the uniform level mean (dollars) |
| `\MacFwdDivCashDollars` | `0.65` | quarterly cash dividend of the running schedule (dollars) |
| `\MacFwdDivElasTwoYr` | `1.053` | cash-schedule spot elasticity at two years |
| `\MacFwdDivFirstDays` | `30` | days to the first ex-date |
| `\MacFwdDivPvTwoYr` | `5.01` | present value of the cash schedule to two years (dollars) |
| `\MacFwdDivQeqPct` | `2.59` | one-year equivalent continuous yield of the cash schedule (%) |
| `\MacFwdDivToothPct` | `7.9` | annualized implied yield just after the first ex-date enters (%) |
| `\MacFwdSkewBumpBp` | `10` | imposed forward error (bp of F) |
| `\MacFwdSkewCallTenBp` | `9` | IV change magnitude at k = +0.10, call side (vol bp) |
| `\MacFwdSkewGapBp` | `41` | ATM put-call IV gap per 10 bp of forward error (vol bp) |
| `\MacFwdSkewNaiveGapBp` | `278` | ATM gap the naive Section-6.2 forward would imprint (vol bp) |
| `\MacFwdSkewPutTenBp` | `11` | IV change at k = -0.10, put side (vol bp) |
| `\MacFwdBorrowFloorQBp` | `13` | identifiability floor at three months, 10 bp noise (bp) |
| `\MacFwdBorrowFloorWeekBp` | `164` | identifiability floor at one week, 10 bp noise (bp) |
| `\MacFwdBorrowFloorWideYBp` | `16` | identifiability floor at one year, 50 bp noise (bp) |
| `\MacFwdBorrowFloorYBp` | `3.2` | identifiability floor at one year, 10 bp noise (bp) |
| `\MacFwdBorrowNPairs` | `20` | paired strikes behind the floor formula |
| `\MacFwdBorrowSensQBp` | `65` | ATM vol per 100 bp of borrow at three months (vol bp) |
| `\MacFwdBorrowSensYBp` | `136` | ATM vol per 100 bp of borrow at one year (vol bp) |
| `\MacFwdBorrowSigmaPct` | `20` | flat ATM vol of the borrow illustration (%) |
