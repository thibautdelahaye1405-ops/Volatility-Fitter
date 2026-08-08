# Chapter 11 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch11/gen_figures.py` into `ch11_macros.tex`. Last write 2026-08-07.

| Macro | Value | Meaning |
|---|---|---|
| `\MacGrAnchorMovePts` | `0.80` | the constructed systematic move at the SPY December anchor |
| `\MacGrBetaBlend` | `1.2` | the blend's stated beta on the index |
| `\MacGrBetaNvda` | `1.6` | NVDA's stated beta on the index |
| `\MacGrBetaSister` | `1.44` | the sister's true beta on the index |
| `\MacGrDarkCount` | `12` | dark nodes this morning |
| `\MacGrLitCount` | `8` | lit nodes this morning |
| `\MacGrNodeCount` | `20` | universe node count |
| `\MacGrNvdaSepObs` | `+4.30` | measured innovation at the lit NVDA September node, vol pts |
| `\MacGrObsSd` | `0.10` | lit observation noise sd, vol points |
| `\MacGrScatterSd` | `0.30` | per-node idiosyncratic scatter sd, vol points |
| `\MacGrSpyDecObs` | `+0.86` | measured innovation at the lit SPY December node, vol pts |
| `\MacGrSpyShortObs` | `+6.17` | measured innovation at the lit 18-day SPY node, vol pts |
| `\MacGrContractFlat` | `\ensuremath{3.3\times10^{-9}}` | max deviation of the swept posterior means from +2.00 / +0.50 |
| `\MacGrContractSdRatio` | `2.00` | measured 3M/1Y posterior sd ratio (the beta-squared units law) |
| `\MacGrHopGap` | `\ensuremath{2.2\times10^{-16}}` | max gap between solved chain sds and the accumulation law |
| `\MacGrHopMean` | `+1.00` | posterior mean at hop six (undamped) |
| `\MacGrVoteBeta` | `+0.75` | same signals under calendar betas: receiver-unit average |
| `\MacGrVoteCancel` | `+0.00` | equal-trust beta-one opposing signals at the 6M receiver |
| `\MacGrVoteOut` | `-0.50` | the 3p short leg outvotes: 6M posterior |
| `\MacGrDeadAvgEq` | `0.40` | averaging-assembly transfer at equal configured trust |
| `\MacGrDeadAvgHigh` | `0.00` | averaging-assembly transfer at 1000x dead trust |
| `\MacGrDeadPairMin` | `1.0000` | factor-assembly transfer, minimum across the trust sweep |
| `\MacGrRepeatJoint` | `1.667` | joint marginal variance at the target, 1/p units (5/3) |
| `\MacGrRepeatNaive` | `1.200` | naive per-route variance claim, 1/p units (6/5) |
| `\MacGrRepeatOverstatePct` | `39` | precision overstatement of per-route accounting, percent |
| `\MacGrAnchorLawGap` | `\ensuremath{2.5\times10^{-9}}` | max gap between the solver's transfer and kp/(kappa+kp) |
| `\MacGrStoryDeskB` | `11.0` | the desk path's B mark at t=4 (dislocation kept) |
| `\MacGrStorySnapA` | `10.0` | the snapshot solve's A mark at t=3.5 (dragged to the print) |
| `\MacGrStorySnapB` | `14.0` | the snapshot solve's B mark at t=4 (dislocation erased) |
| `\MacGrAuditFloor` | `1.08` | std(Z) with the idiosyncratic floor added to the bands |
| `\MacGrAuditOver` | `6.1` | std(Z) under 25x overtrusted relation precisions |
| `\MacGrAuditStated` | `1.55` | std(Z) under stated precisions, no floor |
| `\MacGrCalmBase` | `0.21` | baseline error at the called-out idiosyncratic node |
| `\MacGrCalmGraph` | `0.97` | graph error at the called-out idiosyncratic node |
| `\MacGrNvdaDecBand` | `0.38` | floored posterior sd at the withheld node, vol pts |
| `\MacGrNvdaDecFromNvda` | `+1.04` | contribution of the two lit NVDA neighbours, vol pts |
| `\MacGrNvdaDecFromRes` | `+0.05` | contribution routed through the sister's carried residual |
| `\MacGrNvdaDecFromSpy` | `+0.30` | contribution of the six lit index nodes, vol pts |
| `\MacGrNvdaDecPost` | `+1.39` | posterior innovation at the withheld NVDA December node |
| `\MacGrNvdaDecQuotes` | `167` | prepared quote count at the withheld NVDA December node |
| `\MacGrNvdaDecTrue` | `+1.08` | true innovation at the withheld NVDA December node |
| `\MacGrRetargetRmsBp` | `1.2` | rms gap between the retargeted smile and the shifted target, vol bp |
| `\MacGrRmsBase` | `3.01` | dark-node rms error of riding the baseline, vol pts |
| `\MacGrRmsGraph` | `0.47` | dark-node rms error of the graph posterior, vol pts |
| `\MacGrShortDarkPost` | `+10.19` | posterior at the dark 18-day NVDA node |
| `\MacGrShortDarkTrue` | `+9.47` | true innovation at the dark 18-day NVDA node |
| `\MacGrSisterCarried` | `-0.69` | the sister's carried dislocation this morning, vol pts |
| `\MacGrSisterSepPost` | `+2.96` | posterior at the dark sister September node |
| `\MacGrSisterSepSys` | `+3.79` | its lit-source (systematic) part |
| `\MacGrSisterSepTrue` | `+2.92` | true innovation at the sister September node |
| `\MacGrSkillBetter` | `10` | dark nodes where the graph beats the baseline |
| `\MacGrSkillWorse` | `2` | dark nodes where riding the baseline would have been better |
