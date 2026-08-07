# Chapter 7 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch07/gen_figures.py` into `ch07_macros.tex`. Last write 2026-08-07.

| Macro | Value | Meaning |
|---|---|---|
| `\MacDeamWedgeAtmBiasBp` | `92` | naive bias at the strike nearest the forward (vol bp) |
| `\MacDeamWedgeForward` | `98.02` | forward of the running synthetic board (dollars) |
| `\MacDeamWedgeMaxBiasBp` | `3872` | largest naive-inversion bias across the board (vol bp) |
| `\MacDeamWedgeMaxPremiumDollars` | `2.35` | largest early-exercise premium on the board (dollars) |
| `\MacDeamWedgeRootRmsBp` | `0.7` | rms error of the recovered sigma* across the board (vol bp; scalar-depth inversion of converged-tree quotes) |
| `\MacDeamWexAmDollars` | `11.7856` | worked strike: American tree price at the true vol (dollars) |
| `\MacDeamWexBiasBp` | `219` | worked strike: naive bias over the true 25% (vol bp) |
| `\MacDeamWexEuDollars` | `11.2725` | worked strike: European leg at the same vol (dollars) |
| `\MacDeamWexNaivePct` | `27.19` | worked strike: naive European implied vol (%) |
| `\MacDeamWexPremiumDollars` | `0.5131` | worked strike: the premium A - E (dollars) |
| `\MacDeamWexPremiumPct` | `4.4` | worked strike: premium as a share of the option's value (%) |
| `\MacDeamWexRootPct` | `25.00` | worked strike: the recovered de-Americanized root (%) |
| `\MacDeamMapCallBdryPct` | `78` | call plateau onset at t=0.5 (strike, % of spot) |
| `\MacDeamMapCallMaxDollars` | `6.65` | largest call premium on the map (dollars per 100 spot) |
| `\MacDeamMapMertonMaxDollars` | `\ensuremath{0}` | largest \|A-E\| for no-dividend calls anywhere on the grid (dollars; Merton's theorem measured) |
| `\MacDeamMapPutBdryPct` | `129` | put plateau onset at t=0.5 (strike, % of spot) |
| `\MacDeamMapPutMaxDollars` | `8.35` | largest put premium on the map (dollars per 100 spot) |
| `\MacDeamConvAmErrCents` | `0.10` | American price error at N_t=256 (cents) |
| `\MacDeamConvPremErrCents` | `0.11` | error of the difference A-E at N_t=256 (cents) |
| `\MacDeamConvRatio` | `3` | median ratio of American-leg to difference error, N_t>=64 |
| `\MacDeamTreeContDown` | `17.37` | hand tree: continuation value at the down node |
| `\MacDeamTreeContUp` | `2.40` | hand tree: continuation value at the up node |
| `\MacDeamTreeDownFactor` | `0.8607` | hand tree: down factor 1/u |
| `\MacDeamTreeGrowth` | `1.0151` | hand tree: one-step growth factor exp(r dt) |
| `\MacDeamTreeIntrDown` | `18.93` | hand tree: intrinsic value at the down node |
| `\MacDeamTreePayDD` | `30.92` | hand tree: terminal payoff at the double-down node |
| `\MacDeamTreePayUD` | `5.00` | hand tree: terminal payoff at the middle node |
| `\MacDeamTreePremTwoStep` | `0.75` | hand tree: the two-step premium A - E |
| `\MacDeamTreeProbDown` | `0.4872` | hand tree: down probability 1 - p |
| `\MacDeamTreeProbUp` | `0.5128` | hand tree: risk-neutral up probability |
| `\MacDeamTreeRootAm` | `10.30` | hand tree: American value at the root |
| `\MacDeamTreeRootEu` | `9.55` | hand tree: European value at the root |
| `\MacDeamTreeSpotDD` | `74.08` | hand tree: spot after two down moves |
| `\MacDeamTreeSpotDown` | `86.07` | hand tree: spot at the down node |
| `\MacDeamTreeSpotUU` | `134.99` | hand tree: spot after two up moves |
| `\MacDeamTreeSpotUp` | `116.18` | hand tree: spot at the up node |
| `\MacDeamTreeStepDisc` | `0.9851` | hand tree: one-step discount factor exp(-r dt) |
| `\MacDeamTreeUpFactor` | `1.1618` | hand tree: up factor exp(sigma sqrt(dt)) |
| `\MacDeamTreeValDownEu` | `17.37` | hand tree: European value at the down node |
| `\MacDeamRootDeepIntr` | `60` | intrinsic value of the deep put (dollars) |
| `\MacDeamRootPlateauGapCents` | `0.00` | time value of the K=160 put at the true vol (cents): the quote IS the intrinsic floor |
| `\MacDeamRootQuoteItm` | `12.34` | converged put price at K=110 (dollars) |
| `\MacDeamRootQuoteOtm` | `0.61` | converged put price at K=80 (dollars) |
| `\MacDeamEscrowCashPreExMax` | `\ensuremath{0}` | largest cash-model premium before the ex-date (dollars; Merton verbatim) |
| `\MacDeamEscrowFlatPreExMax` | `0.65` | largest flat-yield premium before the ex-date (dollars; invented) |
| `\MacDeamEscrowFlatQPct` | `6.14` | the schedule's one-year-equivalent flat yield (%/yr) |
| `\MacDeamEscrowFwd` | `94.99` | forward of the cash schedule at t=0.5 (dollars) |
| `\MacDeamEscrowQeqPct` | `12.29` | yield matching that forward at t=0.5 (%/yr) |
| `\MacDeamEscrowRatioMax` | `3.1` | largest cash-to-yield premium ratio on panel (a), where the yield premium exceeds one cent |
| `\MacDeamBowFDeam` | `768.20` | de-Americanized parity root after two passes (dollars) |
| `\MacDeamBowFNaive` | `762.71` | naive parity root (dollars) |
| `\MacDeamBowFResolved` | `767.92` | the snapshot's stored resolved forward (dollars) |
| `\MacDeamBowGapToResolvedBp` | `4` | de-Americanized root vs stored forward (bp of forward) |
| `\MacDeamBowMatchRmsDollars` | `0.17` | rms mismatch between measured residuals and the predicted arch (dollars) |
| `\MacDeamBowNDropped` | `35` | pairs dropped: at least one leg on the intrinsic plateau |
| `\MacDeamBowNKept` | `123` | pairs where both legs inverted (plateau lanes dropped) |
| `\MacDeamBowNPairs` | `158` | paired strikes on the running node (as in fig. 6.1) |
| `\MacDeamBowNaiveGapBp` | `68` | naive root vs stored forward (bp; fig. 6.1's 68) |
| `\MacDeamBowPassDeltaBp` | `2.6` | movement of the root between pass 1 and pass 2 (bp) |
| `\MacDeamBowRmsAfterDollars` | `0.17` | rms residual after de-Americanization (dollars) |
| `\MacDeamBowRmsBeforeDollars` | `2.97` | rms residual of the naive line (dollars; fig. 6.1's 2.97) |
| `\MacDeamGalItmDead` | `35` | discarded ITM puts on the intrinsic plateau (no inversion) |
| `\MacDeamGalItmMaxBp` | `448` | running node: worst discarded-ITM-put wedge (vol bp) |
| `\MacDeamGalItmMedianBp` | `161` | running node: median \|wedge\| on discarded ITM puts (vol bp) |
| `\MacDeamGalItmN` | `12` | discarded ITM puts that still invert (running node) |
| `\MacDeamGalSelCallMedianBp` | `-1.7` | running node: median wedge, fitted calls (vol bp) |
| `\MacDeamGalSelMaxBp` | `61` | running node: worst fitted-quote wedge (vol bp) |
| `\MacDeamGalSelMedianBp` | `3.6` | running node: median \|wedge\| on fitted quotes (vol bp) |
| `\MacDeamGalSelN` | `93` | fitted quotes on the running node (inverted both ways) |
| `\MacDeamGalSelPutMedianBp` | `11.2` | running node: median wedge, fitted puts (vol bp) |
| `\MacDeamGalShortMedianBp` | `1.32` | shortest expiry's fitted median wedge (vol bp) |
| `\MacDeamGalWorstMaxBp` | `221` | largest single fitted-quote wedge across the gallery (vol bp) |
| `\MacDeamGalWorstMedianBp` | `6.8` | largest per-expiry fitted median across the gallery (vol bp) |
| `\MacDeamTblDepthMaxBp` | `8` | worst such shift (vol bp) |
| `\MacDeamTblDepthMedianBp` | `2.0` | median \|sigma*\| shift, tree depth 256 vs 128, running node fitted quotes (vol bp) |
