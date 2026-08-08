# Chapter 10 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch10/gen_figures.py` into `ch10_macros.tex`. Last write 2026-08-08.

| Macro | Value | Meaning |
|---|---|---|
| `\MacPriorFlatBandRmsBp` | `1.0` | thinned-morning band rms at the valley floor (bp) |
| `\MacPriorFlatEnsembleSpreadPts` | `0.3` | wing spread of eight reference-implementation band fits |
| `\MacPriorFlatHeroDays` | `137` | days to expiry of the running node |
| `\MacPriorFlatNFull` | `94` | quotes on the full frozen chain |
| `\MacPriorFlatNThin` | `31` | quotes kept in the staged morning (\|k\| <= 0.10) |
| `\MacPriorFlatPinHiPct` | `36` | highest imposed wing vol (%) |
| `\MacPriorFlatPinLoPct` | `24` | lowest imposed wing vol (%) |
| `\MacPriorFlatPinSpanPts` | `12` | span of the imposed wing sweep (vol points) |
| `\MacPriorFlatSuppAtm` | `21.0` | quote support at the money on the staged morning |
| `\MacPriorFlatSuppWing` | `0.01` | quote support at k = -0.30 on the staged morning |
| `\MacPriorFlatVHalfPts` | `0.5` | full-chain V half-width at +5 bp of rms (vol points) |
| `\MacPriorFlatValleyBp` | `0.02` | total variation of the thinned-morning rms across the sweep |
| `\MacPriorGateRidgeSharePct` | `33` | posterior share a unit-weight ridge carries at twice the required precision |
| `\MacPriorBasketCrossBf` | `0.09` | band half-width where the BF basket reaches the requirement |
| `\MacPriorBasketCrossRr` | `0.17` | band half-width where the RR basket reaches the requirement |
| `\MacPriorBasketFactor` | `4` | BF-to-RR precision ratio on the same symmetric legs |
| `\MacPriorBasketLeg` | `0.18` | wing-leg location of the sweep's baskets |
| `\MacPriorBasketRrDead` | `0.10` | RR precision with call support 6, put support 0.1 |
| `\MacPriorJumpAnchorErrDeep` | `4.5` | absolute-anchor fit \|error\| vs lifted truth at k=-0.30 (pts) |
| `\MacPriorJumpAtmGapBp` | `26.9` | ATM gap between shape-basket and data-only fits (vol bp) |
| `\MacPriorJumpBasketErrDeep` | `0.28` | shape-basket fit \|error\| vs lifted truth at k=-0.30 (pts) |
| `\MacPriorJumpDataErrDeep` | `6.4` | data-only fit \|error\| vs lifted truth at k=-0.30 (pts) |
| `\MacPriorJumpGateAtm` | `0.00` | computed gate of the level row on the staged morning |
| `\MacPriorJumpGateBfDeep` | `0.99` | computed gate of the deep-wing BF row |
| `\MacPriorJumpGateBfMod` | `0.00` | computed gate of the moderate-wing BF row |
| `\MacPriorJumpGateRr` | `0.68` | computed gate of the moderate-wing RR row |
| `\MacPriorJumpGateRrDeep` | `1.00` | computed gate of the deep-wing RR row |
| `\MacPriorJumpPts` | `4` | overnight level jump (vol points) |
| `\MacPriorJumpSuppAtm` | `9.8` | ATM quote support on the staged morning |
| `\MacFiltCaseGainCurv` | `0.027` | computed gain of the curvature |
| `\MacFiltCaseGainLevel` | `0.80` | computed gain of the ATM level |
| `\MacFiltCaseGainSkew` | `0.72` | computed gain of the skew |
| `\MacFiltCasePostCurv` | `0.112` | posterior curvature |
| `\MacFiltCasePostLevelPct` | `20.32` | posterior ATM level (%) |
| `\MacFiltCasePostSdLevelBp` | `13` | posterior ATM sd (vol bp) |
| `\MacFiltCasePostSkew` | `-0.364` | posterior skew |
| `\MacFiltCovarBaseSdBp` | `9.8` | clean-chain ATM observation sd (vol bp) at 30 bp noise |
| `\MacFiltCovarGainCurvClean` | `0.85` | curvature gain on the clean chain |
| `\MacFiltCovarGainCurvKinked` | `0.33` | curvature gain at the 3-point kink |
| `\MacFiltCovarGainLevelClean` | `0.97` | level gain on the clean chain |
| `\MacFiltCovarGainLevelKinked` | `0.77` | level gain at the 3-point kink |
| `\MacFiltCovarMultMax` | `11` | misfit multiple at the 3-point kink (after the cap) |
| `\MacFiltCovarNq` | `21` | synthetic chain quote count |
| `\MacFiltCovarSlope` | `1.000` | log-log slope of ATM observation sd in stated noise |
| `\MacFiltAuditDayThreeStarved` | `1.6` | starved-budget \|error\| three days after the jump (pts) |
| `\MacFiltAuditDayZeroGate` | `0.49` | surprise-widened \|error\| on the jump day (pts) |
| `\MacFiltAuditDayZeroHonest` | `2.0` | true-scale \|error\| on the jump day (pts) |
| `\MacFiltAuditDayZeroStarved` | `3.8` | starved-budget \|error\| on the jump day (pts) |
| `\MacFiltAuditDays` | `500` | length of the synthetic history (days) |
| `\MacFiltAuditQTrueBp` | `30` | true walk scale (vol bp per sqrt day) |
| `\MacFiltAuditShockPts` | `5` | jump size (vol points) |
| `\MacFiltAuditZstdGated` | `1.01` | std of Z at the true scale with the surprise widening |
| `\MacFiltAuditZstdHonest` | `1.14` | std of Z at the true walk scale (30 bp) |
| `\MacFiltAuditZstdStarved` | `3.0` | std of Z under the starved budget (10 bp) |
