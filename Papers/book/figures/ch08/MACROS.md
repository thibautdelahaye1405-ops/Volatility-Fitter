# Chapter 8 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch08/gen_figures.py` into `ch08_macros.tex`. Last write 2026-09-30.

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
| `\MacClkIdentDenseWidthD` | `28` | width of the dense board's event-bearing interval (days) |
| `\MacClkIdentFlatDays` | `0.000` | days installed on a flat 20% ladder (exactly zero) |
| `\MacClkIdentFloorDenseD` | `0.84` | smallest event the rule reports on the dense board (days) |
| `\MacClkIdentFloorQuartD` | `2.73` | smallest event the rule reports on the quarterly board (days) |
| `\MacClkIdentMaxErrD` | `5.9e-14` | largest \|recovered - planted\| above the floors, all boards |
| `\MacClkIdentQuartWidthD` | `91` | width of the quarterly board's event-bearing interval (days) |
| `\MacClkIdentVolDiffD` | `0.0e+00` | largest difference between the 40% and 20% recoveries (days) |
| `\MacClkIdentWallWidthD` | `67` | interval width beyond which a 2-day event is below the floor |
| `\MacClkReadFullMarchAfter` | `0.1707` | Dec->Mar forward variance after the clip (var/yr) |
| `\MacClkReadFullMarchBefore` | `0.2568` | Dec->Mar forward variance before (var/yr) |
| `\MacClkReadFullMarchD` | `45.9` | extra days the unrestricted read puts on Dec->Mar alone |
| `\MacClkReadFullSpreadAfterBp` | `904` | full-board spread after (var bp) |
| `\MacClkReadFullSpreadBeforeBp` | `1444` | full-board spread before (var bp) |
| `\MacClkReadFullTotalD` | `50.2` | total extra days installed with candidates everywhere |
| `\MacClkReadHeroEarnAfter` | `0.1707` | earnings interval forward variance after the clip (var/yr) = its higher neighbour, the Sep-Dec interval |
| `\MacClkReadHeroEarnD` | `4.3` | extra days the year-end read puts on the earnings interval |
| `\MacClkReadHeroFrontLevel` | `0.1890` | the 2-day interval's forward variance (var/yr) |
| `\MacClkReadHeroFrontRef` | `0.1954` | the 2-day interval's reference: the back's decay continued |
| `\MacClkReadHeroLullLevel` | `0.1408` | the pre-earnings lull's forward variance (var/yr), left as is |
| `\MacClkReadHeroSpreadAfterBp` | `482` | in-horizon forward-variance spread after (var bp) |
| `\MacClkReadHeroSpreadBeforeBp` | `560` | in-horizon forward-variance spread before (var bp) |
| `\MacClkReadHeroTotalD` | `4.3` | total extra days installed by the year-end read |
| `\MacClkReadSpyDecBp` | `2` | largest decrease anywhere in SPY's calendar ladder (var bp) |
| `\MacClkReadSpyMidVolPct` | `15` | SPY median forward variance quoted as a volatility (%) |
| `\MacClkReadSpyPeakExcessPct` | `1.3` | relative excess of SPY's only local peak over its higher neighbour (%) |
| `\MacClkReadSpySpreadBp` | `253` | SPY forward-variance spread left in place (var bp) |
| `\MacClkReadSpyTotalD` | `0.0` | total extra days installed on the SPY board |
