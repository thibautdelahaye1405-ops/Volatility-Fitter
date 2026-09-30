# Chapter 9 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch09/gen_figures.py` into `ch09_macros.tex`. Last write 2026-09-30.

| Macro | Value | Meaning |
|---|---|---|
| `\MacSsrFanMovePct` | `4` | the fan's forward move magnitude, % (down) |
| `\MacSsrHeroAtmPct` | `14.8` | hero node ATM implied vol, % |
| `\MacSsrHeroDays` | `137` | hero node: calendar days to expiry |
| `\MacSsrHeroSkew` | `-0.430` | hero node ATM skew s0 (vol per unit log-moneyness) |
| `\MacSsrMarkSlope` | `-0.558` | today's smile slope at the marked k=-0.10 strike |
| `\MacSsrMarkSpreadBp` | `445` | spread of the marked strike's vol across regimes at the fan move (R=0 minus R=2 readings), vol bp |
| `\MacSsrMarkVolPct` | `20.1` | today's vol at the marked k=-0.10 strike, % |
| `\MacSsrSignMovePct` | `4` | the sign figure's move, % (up) |
| `\MacSsrSignQuoteVolPct` | `14.0` | vol of the tracked fixed strike, % |
| `\MacSsrDialAtmMoveBp` | `344` | linear ATM response R s0 H at the fan move for R=2, vol bp |
| `\MacSsrDialBendBp` | `54` | second-order ATM bend at H=-6% under R=1 (sticky-strike), vol bp |
| `\MacSsrDialBendRatio` | `2.5` | ratio of the R=2 bend to the R=1 bend at H=-6% (about 4) |
| `\MacSsrDialBendTwoBp` | `133` | second-order ATM bend at H=-6% under R=2, vol bp |
| `\MacSsrDeltaAtmPts` | `21.0` | regime delta gap at the money, delta pts |
| `\MacSsrDeltaGapPts` | `18.7` | R=0 vs R=2 total-delta gap at the marked strike, delta pts |
| `\MacSsrDeltaMarkPutDelta` | `19` | Black forward put delta magnitude at the marked strike, pts |
| `\MacSsrDeltaMaxK` | `-0.03` | log-moneyness where the regime delta gap peaks |
| `\MacSsrDeltaMaxPts` | `24.4` | largest regime delta gap across the span, delta pts |
| `\MacSsrHalfAtmMoveBp` | `+140` | measured ATM change after the frozen-field -4% move, vol bp |
| `\MacSsrHalfAtmPredBp` | `+140` | half-rule prediction 2 s0 H, vol bp |
| `\MacSsrHalfGapCallBp` | `10` | relabeling-vs-linear gap at k=+0.15 under a -5% move, bp |
| `\MacSsrHalfGapPutBp` | `86` | relabeling-vs-linear gap at k=-0.24 under a -5% move, bp |
| `\MacSsrHalfMoveWingPct` | `5` | the wing-gap panel's move magnitude, % |
| `\MacSsrHalfRatio` | `0.499` | measured implied-to-local slope ratio at tau=0.10 |
| `\MacSsrHalfSlopeImp` | `-0.175` | measured implied ATM skew of the generator at tau=0.10 |
| `\MacSsrHalfSlopeLoc` | `-0.35` | generator vol slope per unit log-strike |
| `\MacSsrRepAtmDlrBp` | `+170` | dollar-strike field: repriced ATM response to the move, vol bp |
| `\MacSsrRepAtmLogBp` | `+175` | log-strike field: repriced ATM response to the move, vol bp |
| `\MacSsrRepAuditPct` | `0.00` | dt-check: relative change of the bent field's ratio at the comparison maturity between dt and dt/4, % |
| `\MacSsrRepBentBigMean` | `2.11` | bent field: mean realized ratio across maturities at H=-4% |
| `\MacSsrRepBentBigPred` | `2.11` | closed-form prediction 2+2cH/b at H=-4% |
| `\MacSsrRepBentMean` | `2.06` | bent field: mean realized ratio across maturities at H=-2% |
| `\MacSsrRepBentPred` | `2.06` | closed-form prediction 2+2cH/b at H=-2% |
| `\MacSsrRepFlatLong` | `2.00` | straight-line field: realized ratio at the longest maturity |
| `\MacSsrRepFlatShort` | `2.00` | straight-line field: realized ratio at the shortest maturity |
| `\MacSsrRepFlatSpread` | `0.001` | straight-line field: max-min spread of the ratio across maturities |
| `\MacSsrRepRatioMovePct` | `2` | panel (c) realized-ratio move magnitude, % (down) |
| `\MacSsrRepRespMovePct` | `5` | panel (b) response-comparison move magnitude, % (down) |
| `\MacSsrRepSepCallBp` | `36` | wing separation of the two answers at k=+0.30, vol bp |
| `\MacSsrRepSepPutBp` | `26` | wing separation of the two answers at k=-0.30, vol bp |
| `\MacSsrRepTcmp` | `0.25` | maturity of the two-field comparison, years |
| `\MacSsrScenGapHeroPts` | `22.2` | 25-delta-put delta gap at the hero expiry, delta pts |
| `\MacSsrScenGapLongPts` | `20.9` | 25-delta-put delta gap at the longest expiry, delta pts |
| `\MacSsrScenGapShortPts` | `15.9` | 25-delta-put delta gap at the shortest expiry, delta pts |
| `\MacSsrScenLongAtmMovePts` | `3.0` | longest expiry: spread of the ATM readings between R=0 and R=2 under the scenario, vol pts |
| `\MacSsrScenLongSkew` | `-0.29` | longest expiry's ATM skew s0 |
| `\MacSsrScenMovePct` | `5` | the board scenario's move magnitude, % (down) |
| `\MacSsrScenRootScaledSkew` | `0.25` | the two-day skew scaled by sqrt(tau) to the hero maturity (the 1/sqrt(tau)-decay prediction), absolute value |
| `\MacSsrScenShortAtmMovePts` | `27.3` | shortest expiry: spread of the ATM readings between R=0 and R=2 under the scenario, vol pts |
| `\MacSsrScenShortDays` | `2` | shortest board expiry, days |
| `\MacSsrScenShortLinearPts` | `21.0` | shortest expiry: the linear law's R=2 ATM response 2\|s0 H\|, vol pts |
| `\MacSsrScenShortReindexPct` | `25.7` | shortest expiry: sticky-strike ATM after the move, the fit read at k = H, % |
| `\MacSsrScenShortRtwoPct` | `37.0` | shortest expiry: R=2 ATM after the move, the fit read at k = 2H, % |
| `\MacSsrScenShortRzeroPct` | `9.6` | shortest expiry: sticky-moneyness ATM after the move (= today's, exactly), % |
| `\MacSsrScenShortSkew` | `-2.10` | shortest expiry's ATM skew s0 |
| `\MacSsrScenShortTodayPct` | `9.6` | shortest expiry: today's ATM vol, % |
| `\MacSsrScenSlopeHero` | `-0.570` | smile slope at the hero expiry's 25-delta put |
| `\MacSsrScenSlopeLong` | `-0.281` | smile slope at the longest expiry's 25-delta put |
| `\MacSsrScenSlopeShort` | `-3.39` | smile slope at the shortest expiry's 25-delta put |
