# Chapter 8 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch08/gen_figures.py` into `ch08_macros.tex`. Last write 2026-08-07.

| Macro | Value | Meaning |
|---|---|---|
| `\MacClkBoardDipBp` | `429` | drop from the 4-day to the 18-day reading (vol bp) |
| `\MacClkBoardHotDays` | `28` | calendar days in the earnings interval (18d -> 46d) |
| `\MacClkBoardHotFwd` | `0.1969` | earnings interval forward variance per calendar year |
| `\MacClkBoardHotOverLull` | `1.40` | ratio of the two accrual rates |
| `\MacClkBoardHotPerDay` | `5.39` | earnings interval: variance bp accrued per calendar day |
| `\MacClkBoardLullDays` | `14` | calendar days in the lull interval (4d -> 18d) |
| `\MacClkBoardLullFwd` | `0.1408` | lull interval forward variance per calendar year |
| `\MacClkBoardLullPerDay` | `3.86` | lull interval: variance bp accrued per calendar day |
| `\MacClkBoardVolEighteenDPct` | `38.84` | NVDA 18-day calendar ATM vol (%) |
| `\MacClkBoardVolFortySixDPct` | `42.29` | NVDA 46-day calendar ATM vol (%) |
| `\MacClkBoardVolFourDPct` | `43.13` | NVDA 4-day calendar ATM vol (%) |
| `\MacClkBoardVolTwoDPct` | `43.48` | NVDA 2-day calendar ATM vol (%) |
| `\MacClkBoardWEighteenBp` | `74.4` | ATM total variance at the Eighteen-day expiry (var bp) |
| `\MacClkBoardWFortySixBp` | `225.4` | ATM total variance at the FortySix-day expiry (var bp) |
| `\MacClkBoardWFourBp` | `20.4` | ATM total variance at the Four-day expiry (var bp) |
| `\MacClkWalkDailyPct` | `2` | one ordinary day's return sd (%) |
| `\MacClkWalkDays` | `30` | trading days simulated |
| `\MacClkWalkEnvKinkPct` | `1.08` | envelope jump across the event day (% points) |
| `\MacClkWalkEventDay` | `20` | index of the event day |
| `\MacClkWalkEventUnits` | `5` | day-units of variance on the event day |
| `\MacClkWalkPaths` | `5` | paths drawn |
| `\MacClkClockEventDay` | `10` | worked calendar: event date in calendar days |
| `\MacClkClockExtraDays` | `4` | worked calendar: extra equivalent days N_e |
| `\MacClkClockNormFactor` | `0.9892` | normalization factor 365/(365+4) for the worked calendar |
| `\MacClkClockPeakPct` | `18.3` | the same peak as a percent lift of the reading |
| `\MacClkClockPeakRatio` | `1.183` | reading ratio sqrt(tau/t) at the event-day expiry |
| `\MacClkClockRatioTwoWeeks` | `1.134` | reading ratio at the 14-day expiry (the hand example) |
| `\MacClkCrushDropBp` | `1243` | the overnight crush of the reading (vol bp) |
| `\MacClkCrushPeakPct` | `42.4` | last pre-event calendar reading of the day-14 expiry (%) |
| `\MacClkCrushPostPct` | `30.0` | morning-after calendar reading (%) |
| `\MacClkCrushRampStartPct` | `34.0` | day-0 calendar reading of the day-14 expiry (%) |
| `\MacClkCrushTermPeakPct` | `35.5` | term-structure hump peak at the event-day expiry (%) |
| `\MacClkInterpEventDay` | `45` | event date of the interpolation construction (calendar day) |
| `\MacClkInterpExactBp` | `0.00` | max \|linear-in-tau minus generator\| reading gap (vol bp) |
| `\MacClkInterpOverBp` | `33` | max phantom vol BEFORE the event (vol bp) |
| `\MacClkInterpOverDay` | `45` | calendar day of the max overshoot |
| `\MacClkInterpUnderBp` | `97` | max understatement PAST the event (vol bp) |
| `\MacClkInterpUnderDay` | `45` | calendar day of the max understatement |
| `\MacClkIdentBlindD` | `2.5` | largest planted event the quarterly 20% board misses (days) |
| `\MacClkIdentFlatDays` | `0.000` | days installed on a flat 20% ladder (exactly zero) |
| `\MacClkIdentShrinkStrongD` | `0.03` | max shrinkage, dense board at 40% vol (planted >= 2d) |
| `\MacClkIdentShrinkWeakD` | `0.40` | max shrinkage, dense board at 20% vol (planted >= 2d) |
| `\MacClkIdentWallQuarterlyPct` | `22` | lowest vol at which the quarterly board sees it (%) |
| `\MacClkIdentWallWeeklyPct` | `12` | lowest vol at which the dense board sees a 2-day event (%) |
| `\MacClkReadFullMarchD` | `112` | extra days the unrestricted solve puts on Dec->Mar alone |
| `\MacClkReadFullSpreadAfterBp` | `44` | full-board spread after (var bp) |
| `\MacClkReadFullSpreadBeforeBp` | `1444` | full-board spread before (var bp) |
| `\MacClkReadFullTotalD` | `250` | total extra days installed with candidates everywhere |
| `\MacClkReadHeroEarnAfter` | `0.1559` | earnings interval forward variance after the solve (var/yr) |
| `\MacClkReadHeroEarnD` | `7.3` | extra days the year-end solve puts on the earnings interval |
| `\MacClkReadHeroFlatLevel` | `0.1409` | level the three pre-earnings intervals meet at (var/yr) |
| `\MacClkReadHeroShortD` | `1.3` | extra days on the two short-dated intervals combined |
| `\MacClkReadHeroSpreadAfterBp` | `299` | in-horizon forward-variance spread after (var bp) |
| `\MacClkReadHeroSpreadBeforeBp` | `560` | in-horizon forward-variance spread before (var bp) |
| `\MacClkReadHeroTotalD` | `8.6` | total extra days installed by the year-end solve |
| `\MacClkReadSpyDecBp` | `2` | largest decrease anywhere in SPY's calendar ladder (var bp) |
| `\MacClkReadSpyMidVolPct` | `15` | SPY median forward variance quoted as a volatility (%) |
| `\MacClkReadSpySpreadBp` | `253` | SPY forward-variance spread left in place (var bp) |
| `\MacClkReadSpyTotalD` | `0.9` | total extra days installed on the SPY board |
