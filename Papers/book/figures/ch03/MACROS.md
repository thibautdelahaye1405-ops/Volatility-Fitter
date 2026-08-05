# Chapter 3 macro inventory (auto-generated -- do not edit)

Emitted by `scripts/ch03/gen_figures.py` into `ch03_macros.tex`. Last write 2026-08-05.

| Macro | Value | Meaning |
|---|---|---|
| `\MacSviSpyAtmVolPct` | `14.89` | sqrt(v_J), ATM implied vol of the SVI fit, percent |
| `\MacSviSpyBetaL` | `0.126` | actual left wing slope |
| `\MacSviSpyBetaR` | `0.066` | actual right wing slope |
| `\MacSviSpyC` | `0.724` | c_J of the SPY fit |
| `\MacSviSpyMinVolPct` | `12.41` | sqrt(vtilde_J), minimum implied vol, percent |
| `\MacSviSpyP` | `1.384` | p_J of the SPY fit |
| `\MacSviSpyPsi` | `-0.2634` | psi_J of the SPY fit |
| `\MacSviSpyRmsBp` | `7.5` | SVI structural-chart mid fit rms on SPY Dec-2026, vol bp |
| `\MacSviSpyTangent` | `-0.430` | plotted ATM IV tangent slope psi_J/sqrt(tau) |
| `\MacSviBetaMax` | `1.95` | the buffered wing-slope cap of the reference implementation |
| `\MacSviBoundaryGTen` | `-0.0485` | g_D(10) of the boundary slice (a=0.04, b=2, rho=0, m=0, s=0.2) |
| `\MacSviPstarCap` | `\ensuremath{1.6\times10^{-4}}` | moment budget p* remaining at the buffered cap beta_max |
| `\MacSviVogtGmin` | `-0.033` | Vogt minimum of g_D (the belly violation) |
| `\MacSviVogtKdip` | `0.88` | log-moneyness of the Vogt g_D dip |
| `\MacSviVogtLee` | `0.174` | Vogt larger wing slope (far under the cap) |
| `\MacSviVogtTail` | `0.25` | Vogt right tail limit of g_D (positive) |
| `\MacSviVogtWmin` | `0.0116` | Vogt minimum total variance |
| `\MacSviStratumSpread` | `\ensuremath{1.1\times10^{-17}}` | max spread of the five handles across the three stratum slices |
| `\MacSviChartAgreeBp` | `0.00` | max \|structural - raw chart\| IV gap on SPY Dec, vol bp |
| `\MacSviSpyKappastar` | `0.397` | structural vertex curvature kappa* of the SPY fit |
| `\MacSviSpyKstar` | `0.108` | structural vertex location k* of the SPY fit |
| `\MacSviSpyWstar` | `0.0058` | structural floor w* of the SPY fit |
| `\MacMcsBaseMaxErrBp` | `118.2` | max IV miss of the convex base (M=0) on the WW target, vol bp |
| `\MacMcsCores` | `2` | cores actually placed by the M=2 fit |
| `\MacMcsFitGmin` | `0.420` | min g_D of the M=2 fit on \|k\|<=2 (analytic jets) |
| `\MacMcsFullMaxErrBp` | `0.7` | max IV miss of the M=2 fit on the WW target, vol bp |
| `\MacMcsTargetGmin` | `0.277` | min g_D of the WW target on \|k\|<=12 (analytic jets) |
| `\MacMcsTargetTailG` | `0.250` | analytic tail limit of the WW target's g_D |
| `\MacCmpMixLqdGmin` | `0.371` | LQD min g_D on the quoted range, mixture fit |
| `\MacCmpMixLqdRms` | `3.6` | LQD rms on the mixture target, vol bp |
| `\MacCmpMixMcsGmin` | `-0.066` | MCS min g_D on the quoted range, mixture fit |
| `\MacCmpMixMcsRms` | `87.3` | MCS rms on the mixture target, vol bp |
| `\MacCmpMixSviGmin` | `0.431` | SVI min g_D on the quoted range, mixture fit |
| `\MacCmpMixSviRms` | `166.4` | SVI rms on the mixture target, vol bp |
| `\MacCmpMixTargetGmin` | `0.369` | min g_D of the mixture target on the quoted range (exact density) |
| `\MacCmpSpyLqdBetaL` | `0.178` | LQD left wing slope, SPY Dec fit |
| `\MacCmpSpyLqdBetaR` | `0.034` | LQD right wing slope, SPY Dec fit |
| `\MacCmpSpyLqdGmin` | `0.192` | LQD min g_D on the SPY Dec traded range |
| `\MacCmpSpyLqdPar` | `17` | LQD free parameters on SPY Dec |
| `\MacCmpSpyLqdRms` | `3.4` | LQD rms on SPY Dec-2026 mid quotes, vol bp |
| `\MacCmpSpyMcsBetaL` | `0.117` | MCS left wing slope, SPY Dec fit |
| `\MacCmpSpyMcsBetaR` | `0.054` | MCS right wing slope, SPY Dec fit |
| `\MacCmpSpyMcsGmin` | `-0.001` | MCS min g_D on the SPY Dec traded range |
| `\MacCmpSpyMcsPar` | `14` | MCS free parameters on SPY Dec |
| `\MacCmpSpyMcsRms` | `5.6` | MCS rms on SPY Dec-2026 mid quotes, vol bp |
| `\MacCmpSpySviBetaL` | `0.126` | SVI left wing slope, SPY Dec fit |
| `\MacCmpSpySviBetaR` | `0.066` | SVI right wing slope, SPY Dec fit |
| `\MacCmpSpySviGmin` | `0.199` | SVI min g_D on the SPY Dec traded range |
| `\MacCmpSpySviPar` | `5` | SVI free parameters on SPY Dec |
| `\MacCmpSpySviRms` | `7.5` | SVI rms on SPY Dec-2026 mid quotes, vol bp |
| `\MacCmpNodes` | `16` | nodes in the three-family comparison |
| `\MacCmpTabLqdMedGmin` | `0.184` | LQD median traded-range min g_D across the 16 nodes |
| `\MacCmpTabLqdMedRms` | `7.3` | LQD median rms across the 16 nodes, vol bp |
| `\MacCmpTabLqdNegNodes` | `0` | LQD nodes with a negative traded-range margin |
| `\MacCmpTabLqdWorstGmin` | `0.112` | LQD worst traded-range min g_D across the 16 nodes |
| `\MacCmpTabLqdWorstRms` | `34.0` | LQD worst rms across the 16 nodes, vol bp |
| `\MacCmpTabMcsMedGmin` | `-0.026` | MCS median traded-range min g_D across the 16 nodes |
| `\MacCmpTabMcsMedRms` | `11.8` | MCS median rms across the 16 nodes, vol bp |
| `\MacCmpTabMcsNegNodes` | `10` | MCS nodes with a negative traded-range margin |
| `\MacCmpTabMcsWorstGmin` | `-0.143` | MCS worst traded-range min g_D across the 16 nodes |
| `\MacCmpTabMcsWorstRms` | `38.5` | MCS worst rms across the 16 nodes, vol bp |
| `\MacCmpTabMcszeroMedGmin` | `0.179` | MCS base (R=0) median traded-range min g_D |
| `\MacCmpTabMcszeroMedRms` | `18.1` | MCS base (R=0) median rms across the 16 nodes, vol bp |
| `\MacCmpTabMcszeroNegNodes` | `0` | MCS base (R=0) nodes with a negative traded-range margin |
| `\MacCmpTabSviMedGmin` | `0.173` | SVI median traded-range min g_D across the 16 nodes |
| `\MacCmpTabSviMedRms` | `19.0` | SVI median rms across the 16 nodes, vol bp |
| `\MacCmpTabSviNegNodes` | `0` | SVI nodes with a negative traded-range margin |
| `\MacCmpTabSviWorstGmin` | `0.091` | SVI worst traded-range min g_D across the 16 nodes |
| `\MacCmpTabSviWorstRms` | `68.0` | SVI worst rms across the 16 nodes, vol bp |
