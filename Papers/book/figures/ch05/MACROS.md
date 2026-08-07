# Chapter 5 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch05/gen_figures.py` into `ch05_macros.tex`. Last write 2026-08-06.

| Macro | Value | Meaning |
|---|---|---|
| `\MacVsPinsBellyAgreeBp` | `13.3` | worst pairwise IV distance on the quoted span (vol bp) |
| `\MacVsPinsLqdPct` | `19.83` | LQD fair var-swap vol on the running node (%) |
| `\MacVsPinsMaxGapBp` | `58.2` | largest pairwise fair-strike gap across families (vol bp) |
| `\MacVsPinsMcsPct` | `19.25` | MCS fair var-swap vol on the running node (%) |
| `\MacVsPinsNQuotes` | `94` | prepared quotes on the running SPY December 2026 node |
| `\MacVsPinsSviPct` | `19.33` | SVI fair var-swap vol on the running node (%) |
| `\MacVsPinsWorstRmsBp` | `7.5` | worst per-family rms fit error on the node (vol bp) |
| `\MacVsAgreeFieldBp` | `2.9` | field-side backward solve vs the sheet's own strike-side replication, time step refined 8x (vol bp) |
| `\MacVsAgreeFieldCoarseBp` | `23.2` | the same two reads at the march's own time step (vol bp) |
| `\MacVsAgreeRankBp` | `0.10` | law-side closed form vs strike-side replication (vol bp) |
| `\MacVsFieldSvsPct` | `19.70` | SPY sheet fair var-swap vol at the running expiry, field side (%) |
| `\MacVsLvGapBp` | `13.7` | sheet vs running slice fair-strike gap (vol bp) — the identifiability gap |
| `\MacVsThreeSvsPct` | `19.83` | running slice fair var-swap vol, strike-side replication (%) |
| `\MacVsShareAtmPct` | `52.4` | share accrued in \|k\| <= 0.10 (%) |
| `\MacVsShareBeyondPct` | `18.4` | share accrued beyond the quoted span (%) |
| `\MacVsShareGalleryMaxPct` | `22.9` | largest beyond-quotes share across the 16 frozen nodes (%) |
| `\MacVsShareGalleryMinPct` | `3.0` | smallest beyond-quotes share across the 16 frozen nodes (%) |
| `\MacVsShareQuotedPct` | `81.6` | share of the running slice's var-swap integral accrued on the quoted span (%) |
| `\MacVsRayAboveLim` | `0.995` | B(k, 2.4 k) at k = 400 (heads to 1) |
| `\MacVsRayAtLim` | `0.486` | B(k, 2 k) at k = 400 (tends to 1/2; the second Black term dies only like 1/sqrt(k) on the boundary ray) |
| `\MacVsRayBelowLim` | `0.001` | B(k, 1.6 k) at k = 400 (heads to 0) |
| `\MacWingEnvCbar` | `\ensuremath{1.17\times10^{-4}}` | normalized call at the last quote (of forward) |
| `\MacWingEnvClearLqdHi` | `0.0016` | min clearance of the LQD wing below its own cone's upper edge |
| `\MacWingEnvClearLqdLo` | `0.0016` | min clearance of the LQD wing above its own cone's lower edge |
| `\MacWingEnvClearMcsHi` | `0.0013` | min clearance of the MCS wing below its own cone's upper edge |
| `\MacWingEnvClearMcsLo` | `0.0010` | min clearance of the MCS wing above its own cone's lower edge |
| `\MacWingEnvClearSviHi` | `0.0012` | min clearance of the SVI wing below its own cone's upper edge |
| `\MacWingEnvClearSviLo` | `0.0010` | min clearance of the SVI wing above its own cone's lower edge |
| `\MacWingEnvKbar` | `0.264` | last quoted call-side log-moneyness on the running node |
| `\MacWingEnvKzero` | `0.350` | log-moneyness where the lower envelope edge reaches zero |
| `\MacWingEnvTopAgree` | `\ensuremath{1.1\times10^{-10}}` | closed-form upper edge vs production inversion at k = 30 (total variance) |
| `\MacWingEnvTopSlopeDeep` | `1.14` | upper-edge slope dw+/dk at k = 30 (heads to 2) |
| `\MacWingHatBaseGmin` | `-0.001` | worst Durrleman factor of the fitted slice on the same range |
| `\MacWingHatGmin` | `-0.30` | worst Durrleman factor after the hat |
| `\MacWingHatKmin` | `-0.55` | log-moneyness of the worst dent |
| `\MacWingHatSlopeDiff` | `\ensuremath{0}` | measured realized wing-slope change from adding the hat (far-field finite difference at \|k\| = 8) |
| `\MacVsTermFwdVolMinPct` | `13.9` | smallest SPY forward variance between expiries, as a forward vol (%) |
| `\MacVsTermIncMinVarBp` | `1.1` | smallest adjacent-expiry increment of w_vs across both names (variance bp) |
| `\MacVsTermNvdaSpreadBp` | `529` | largest NVDA fair-strike spread over ATM vol (vol bp) |
| `\MacVsTermSpySpreadBp` | `671` | largest SPY fair-strike spread over ATM vol (vol bp) |
| `\MacWingBetaLqdL` | `0.178` | LQD left (put) asymptotic total-variance wing slope |
| `\MacWingBetaLqdR` | `0.034` | LQD right (call) asymptotic total-variance wing slope |
| `\MacWingBetaMcsL` | `0.117` | MCS left (put) asymptotic total-variance wing slope |
| `\MacWingBetaMcsR` | `0.054` | MCS right (call) asymptotic total-variance wing slope |
| `\MacWingBetaSviL` | `0.126` | SVI left (put) asymptotic total-variance wing slope |
| `\MacWingBetaSviR` | `0.066` | SVI right (call) asymptotic total-variance wing slope |
