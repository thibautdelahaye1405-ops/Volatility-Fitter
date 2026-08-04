# Requested macros — figures/paper_macros.tex

Contract: the figure generator emits `figures/paper_macros.tex` containing one
`\newcommand` per macro below.  Each macro renders the number **with the unit
shown in the "renders like" column** (the surrounding text supplies no unit
unless noted).  The master file carries `\providecommand` fallbacks that
render `[Name?]`, so the paper builds legibly before the generator runs;
generator definitions win automatically because the file is `\input` first.

Canonical data nodes: "SPY Dec" = SPY expiry 2026-12-18; "NVDA Dec" = NVDA
2026-12-18; "NVDA 1d" = NVDA 2026-08-05; all from the frozen snapshot.
The hand-priced ticket is the k = +0.05 call on SPY Dec.

## Snapshot-level (used in §13 Examples, Annex C)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacSpySpot` | SPY spot in the snapshot | `757.67` |
| `\MacNvdaSpot` | NVDA spot in the snapshot | `206.80` |
| `\MacSnapNodeCount` | total fitted nodes | `16` |
| `\MacSnapMedianRmsBp` | median per-node quote rms, vol bp | `5.9` |
| `\MacSnapWorstRmsBp` | worst per-node quote rms, vol bp | `24.6` |

## Constant-speed audit (§4 fig_exact + text, §13)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacExactMaxErr` | worst abs. error of m and x(z) vs closed forms over the scale sweep | `$2\times10^{-15}$` |

## Tails and Lee (§6, fig_tails / fig_lee)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacSpyLamL` / `\MacSpyLamR` | fitted λ− / λ+ of SPY Dec | `0.21` |
| `\MacSpyBetaL` / `\MacSpyBetaR` | Lee slopes of SPY Dec via eq. (leeclosed) | `0.093` |
| `\MacNvdaLamL` / `\MacNvdaLamR` | fitted λ− / λ+ of NVDA Dec | `0.34` |
| `\MacNvdaBetaL` / `\MacNvdaBetaR` | Lee slopes of NVDA Dec | `0.15` |
| `\MacLeeRatioTenDeltaPut` | (effective slope w(k)/\|k\|) / (Lee limit) at the 10Δ put, SPY Dec | `4.1` |
| `\MacLeeRatioOneDeltaPut` | same at the 1Δ put | `1.9` |
| `\MacLeeRatioTenDeltaCall` | same at the 10Δ call | `5.6` |
| `\MacLeeRatioOneDeltaCall` | same at the 1Δ call | `2.3` |

NOTE direction: ratios are effective/limit and must come out > 1 (the
effective slope descends to the limit from above).  If the generator finds
otherwise, stop and tell the lead — the text asserts this direction.

## Order guard and latency cliff (§9)

From the implementation's order-guard study (the ~19-quote same-day strip),
not from the snapshot:

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacGuardQuoteCountZeroDte` | quote count of the study strip | `19` |
| `\MacGuardEffOrderZeroDte` | guarded effective order on that strip | `8` |
| `\MacCliffLoRatio` / `\MacCliffLoEvals` / `\MacCliffLoMs` | params/quotes ratio; solver evals; wall time at the low point | `0.47` / `7` / `20 ms` |
| `\MacCliffMidRatio` / `\MacCliffMidEvals` / `\MacCliffMidMs` | same, mid point | `0.58` / `63` / `166 ms` |
| `\MacCliffHiRatio` / `\MacCliffHiEvals` / `\MacCliffHiMs` | same, past the cliff | `0.68` / `2568` / `7.6 s` |

## Analytic Jacobian (§10, §12 timing caption)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacJacSpeedupMin` / `\MacJacSpeedupMax` | min / max median speedup analytic vs FD across orders | `1.44` / `1.97` |
| `\MacJacFdMaxRel` | worst relative analytic-vs-central-FD disagreement, all strikes × params (fig_jacobian) | `$8\times10^{-4}$` |
| `\MacJacSameOptCost` | relative cost agreement analytic vs FD optimum | `$\sim10^{-11}$` |
| `\MacJacSameOptParams` | parameter agreement analytic vs FD optimum | `$\lesssim10^{-5}$` |

## Calendar (§11, fig_calendar, Annex C)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacCalGapVolBp` | vol-space order-audit worst gap, SPY 1d/3d pair | `1840.6` |
| `\MacCalGapArgmaxK` | argmax log-moneyness of that gap | `+0.981` |
| `\MacCalSpanLo` / `\MacCalSpanHi` | common quote span of the pair | `-0.028` / `+0.016` |
| `\MacCalWingPriceOrder` | order of magnitude of both call prices at the argmax, as fraction of forward | `$10^{-20}$` |
| `\MacCalPriceGridWorst` | worst price-space violation over all adjacent pairs, full display grid | `$<10^{-6}$` |
| `\MacPhantomDragFromBp` / `\MacPhantomDragToBp` | far-expiry fit error without / with the full-grid ledger floor (the phantom-drag incident), vol bp | `10.6` / `1095` |

## Computation: audit, certificates, timing (§12; PreFixFly also Annex A)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacAuditSliceCount` | randomized-audit slice count | `60` |
| `\MacAuditBoundsWorst` | worst call-bound violation, normalized price | `$1.2\times10^{-9}$` |
| `\MacAuditFlyWorst` | worst butterfly violation (four widths) | `$1.0\times10^{-14}$` |
| `\MacAuditDigitalWorst` | worst digital-bound violation | `$3.7\times10^{-12}$` |
| `\MacAuditGridAgreeWorst` | worst 8001-vs-32001-grid price disagreement | `$2.6\times10^{-9}$` |
| `\MacAuditPreFixFly` | butterfly violation before the log-space cash-leg fix | `$10^{-2}$` |
| `\MacAuditPostFixFly` | same after the fix | `$3\times10^{-13}$` |
| `\MacBellyCertMs` | belly-certificate wall time | `0.05 ms` |
| `\MacFitMsOrderSixteen` | median one-slice fit, 40-quote strip, N=16 | `29 ms` |
| `\MacFitMsZeroDte` | median warm same-day slice fit at guarded order | `20 ms` |
| `\MacTwoGridParamAgree` | converged-parameter agreement, 2001- vs 8001-point grid | `$\sim10^{-6}$` |
| `\MacChartEquivParamAgree` | cross-chart optimum parameter agreement on live nodes | `$\sim10^{-5}$` |
| `\MacTimingRows` | **table-body macro**: full booktabs rows for tab:timing, 5 columns `Configuration & Order & Median & IQR & ratio`, one `\\` per row (no trailing `\\` on the last row — the table source adds it) | multi-row |

## Examples (§13)

| Macro | Meaning | Renders like |
|---|---|---|
| `\MacSpyGalleryMedianRmsBp` / `\MacSpyGalleryWorstRmsBp` | median / worst rms across the 8 SPY slices, vol bp | `4.8` / `12.1` |
| `\MacSpyDecRmsBp` | SPY Dec quote rms, vol bp | `3.9` |
| `\MacSpyDecNQuotes` | SPY Dec retained quote count | `212` |
| `\MacSpyDecAtmVolPct` | SPY Dec exact ATM vol (renders with %) | `15.83\%` |
| `\MacSpyDecSkew` | SPY Dec exact σ′(0), vol per unit log-moneyness | `-0.221` |
| `\MacSpyDecCurv` | SPY Dec exact σ″(0) | `0.87` |
| `\MacSpyDecVarSwapPct` | SPY Dec var-swap strike (with %) | `17.2\%` |
| `\MacSpyDecForwardRankPct` | SPY Dec forward rank u\* (with %) | `55.4\%` |
| `\MacTicketRankPct` | ticket: rank u_k at k=+0.05 (with %) | `86.2\%` |
| `\MacTicketShare` | ticket: G(z_k), 4–5 sig figs | `0.16642` |
| `\MacTicketCash` | ticket: e^k(1−u_k), same precision | `0.14506` |
| `\MacTicketPrice` | ticket: normalized call price | `0.02136` |
| `\MacTicketIvPct` | ticket: implied vol (with %) | `14.9\%` |
| `\MacTicketDollarPrice` | ticket: dollar price per share via node F and D | `\$16.31` |
| `\MacNvdaOneDayNQuotes` | NVDA 1d retained quotes | `21` |
| `\MacNvdaOneDayEffOrder` | NVDA 1d guarded effective order | `9` |
| `\MacNvdaOneDayRmsBp` | NVDA 1d rms, vol bp (should equal `\MacSnapWorstRmsBp`) | `24.6` |
| `\MacNvdaLongNQuotes` | NVDA Dec retained quotes | `118` |
| `\MacNvdaLongRmsBp` | NVDA Dec rms, vol bp | `7.4` |
| `\MacHumpFitRmsBp` | double-hump: N=16 fit error vs target, vol bp | `1.5` |
| `\MacHumpIvAgreeBp` | double-hump: max IV gap between N=6 and N=16 fits, vol bp | `3.2` |
| `\MacHumpLOneNSixteen` / `\MacHumpLOneNSix` | L1 density error vs truth at N=16 / N=6 | `0.011` / `0.087` |

All "renders like" values are **format illustrations only** (several are
placeholders); the generator computes every value from the frozen snapshot /
the audit battery / the timing protocol.  Where a macro duplicates a README
number (median 5.9 / worst 24.6), the generator should recompute and flag any
disagreement rather than copy.

---

# Round 2 amendments (2026-08-03, post-review revision)

The engineer's `figures/MACROS.md` is now the authoritative inventory; all
round-1 contract names are emitted there (aliases included).  Changes on the
author side:

**Newly consumed canonical macros** (already emitted — no new work): the toy
ticket block `\MacToyScale`, `\MacToyMu`, `\MacToyAtmPercentile`,
`\MacToyOtmPercentile`, `\MacToyShareOtm`, `\MacToyCashOtm`,
`\MacToyCallOtm`, `\MacToyIvOtmPct` (new §7 worked instance — please confirm
F1's drawn slice IS this 20%-at-6-months toy and its OTM mark is k = 0.10);
`\MacExactMapWorst`, `\MacExactMuWorst`, `\MacExactMartWorst`,
`\MacColdStartMismatchPct` (§4/F3, replacing the retired `\MacExactMaxErr`);
`\MacButterflyDensityRelErrPct` (F14 caption); `\MacNvdaLongMomentLeft`
(§6 wall-asymmetry sentence); `\MacSpyDecBandLivePct`,
`\MacSpyDecMedianSpreadBp`, `\MacNvdaOneDayBandLivePct`,
`\MacNvdaLongBandLivePct`, `\MacNvdaLongMedianSpreadBp` (§9.2 live
degeneracy example); `\MacMultiStartCount`, `\MacMultiStartNodes`,
`\MacMultiStartBasins`, `\MacMultiStartWorstDTheta`,
`\MacMultiStartWorstDIvBp` (§9.5); `\MacCalendarCallShort`,
`\MacCalendarCallLong` (§11 + Annex C); `\MacCertOrdersList`,
`\MacTimingQuoteCount` (§12); `\MacNvdaOneDayDays`, `\MacNvdaLongTYears`,
`\MacDhMaxErrBpHigh`, `\MacDhModeCountLow`, `\MacDhModeLeft`,
`\MacDhModeRight`, `\MacDhTrueModeLeft`, `\MacDhTrueModeRight`,
`\MacTicketK`, `\MacTicketStrike` (§13); `\MacRebuildWorstBp` (Annex C reproducibility gate).

**No longer used in text**: `\MacExactMaxErr` (split into the three specific
audit levels).  Aliases may stay; nothing references them.

**Conventions confirmed in the text** (author side honors MACROS.md):
- Lee ratios are effective/limit; put-side values < 1 are correct and the
  §6.4/F9 prose is now two-sided.  The round-1 "must come out > 1" note is
  VOID.
- `\MacNvdaLam*/Beta*` refer to NVDA 2027-12-17 (the fig_nvda_nodes long
  node); §6 and the F8 caption now say "NVDA December 2027" — do NOT
  re-point the alias.
- Percent policy honored: text adds `\%` after the older bare `*Pct` macros
  (`SpyDecAtmVolPct`, `SpyDecVarSwapPct`, `TicketIvPct`, `ToyIvOtmPct`,
  `ToyAtmPercentile`, `ToyOtmPercentile`) and adds nothing after
  `TicketRankPct` / `SpyDecForwardRankPct`, which carry `\%` themselves.
- `\MacCliff*` are quoted as the FLAT over-parameterization probe on the
  frozen NVDA node, not as a cliff.
- `\MacAuditPostFixFly` (= 0) is phrased as "none at all … exactly".
- `\MacFitMsOrderSixteen` attributed to the 94-quote SPY Dec node;
  `\MacTimingQuoteCount` names the synthetic timing strip.
