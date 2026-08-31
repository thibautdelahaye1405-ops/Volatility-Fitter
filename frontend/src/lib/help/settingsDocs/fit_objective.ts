// Help Center settings corpus — FitSettings, objective knobs (HELP CENTER ARC,
// H2). One SettingDoc per FitSettings field that decides WHAT the fit targets
// and how residuals are weighted, whatever the model: the haircut band
// shrink, the quote-weighting scheme, the band mid anchor and its τ-ref
// attenuation, the band tick floor, the IRLS robust loss + scale, and the
// price-space overlay residuals. These render in the Options ▸ Calibration
// card (HyperparamPanel group="calibration"); the model-family FitSettings
// live in fit_models.ts and fit.ts concatenates both into FIT_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py FitSettings
// (authoritative), volfit/calib/band.py + weights.py docstrings, the labels of
// components/HyperparamPanel.tsx, and the 2026-08-25 short-dated session wrap
// in ROADMAP.md. Machine facts (type / default / range / enum) come from
// settingsSchema.json. Every FitSettings field folds into the fit-cache key.
import type { SettingDoc } from "../types";

export const FIT_OBJECTIVE_DOCS: SettingDoc[] = [
  {
    key: "haircut",
    model: "fit",
    section: "opt-calibration",
    label: "Haircut (vol pts)",
    unit: "vol, absolute (0.005 = 0.5 vol pt)",
    summary: "How far each side of the bid-ask IV band is pulled toward mid in the Haircut fit target.",
    details:
      "In `haircut` mode the band the fit must stay inside is `[min(bid + h, mid), max(mid, ask − h)]`: each side moves h toward mid and never past it, so a quote tighter than 2h collapses to a mid fit on that strike. The default 0.005 (0.5 vol pt) trims the routine half-spread padding of liquid screens without discarding the band information of wide quotes.\n\n" +
      "A larger haircut makes the fit behave more like a mid fit; 0 makes Haircut identical to Bid-Ask. `bandTickFloorTicks` is applied after it and can widen the band back out.",
    example:
      "Set `haircut` to 0.01 on a wide-spread single name: the band shrinks by 1 vol pt each side, the fit hugs mids more, RMS to mid drops, and band violations may appear in Quality on the strikes whose trimmed band the curve can no longer reach.",
    activation: "Read only while the fit target (`fitMode`) is `haircut`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["fitMode", "bandTickFloorTicks", "midAnchorWeight", "help:guides:options"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "weightScheme",
    model: "fit",
    section: "opt-calibration",
    label: "Quote weighting",
    summary: "How much each quote counts in the objective: equal, or a density-corrected economic weight (time value, vega or delta).",
    details:
      "`equal` (default, the historical scheme) gives every quote's residual the same weight. The three density schemes multiply an economic shape by the quote's Voronoi cell width in log-strike, so a crowded strike region does not outvote the wings just by having more listings: `tv_density` follows time value (fastest wing decay), `vega_density` follows Black vega (flattest — the natural choice when the target metric is vol error) and `delta_density` follows the OTM |forward delta| (in between). The spacing multiplier is capped at 10× so one isolated far-wing quote cannot dominate.\n\n" +
      "Weights are normalized to mean 1, so switching schemes never changes the balance against `regLambda` or `sigmoidRidge`. It applies in every fit target and to every model, and it is orthogonal to `fitMode`: the mode chooses each quote's target, the scheme chooses how much each quote matters.",
    example:
      "Switch `weightScheme` to `vega_density` on a 60-quote SPY slice with dense 5-point strikes near ATM: the ATM cluster's aggregate weight falls, the 10Δ put and call quotes gain relative weight, and the wing RMS in Quality improves by a few bp while the ATM RMS worsens slightly.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["fitMode", "regLambda", "varSwapWeightPct", "help:guides:options"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "midAnchorWeight",
    model: "fit",
    section: "opt-calibration",
    label: "Band mid anchor",
    unit: "weight, relative to the band hinge (= 1)",
    summary: "Weight of the soft pull toward mid inside the band, in the Bid-Ask and Haircut fit targets.",
    details:
      "The band objective per quote is `max(model − hi, 0)² + max(lo − model, 0)² + midAnchorWeight · (model − mid)²`: free anywhere inside the band, pulled back hard outside it, gently centred on mid. The default 0.05 keeps the band dominant, so the curve can trade strikes off against each other while still resolving where in the band it sits.\n\n" +
      "At 1 a band fit becomes a mid fit with extra hinges; at 0 the curve floats anywhere in-band and the solution stops being unique on wide quotes. Applies to every model; `midAnchorTauRef` can attenuate it at short maturities.",
    example:
      "Raise `midAnchorWeight` to 0.5 in Bid-Ask mode on a name with 3-vol-pt spreads: the fitted curve moves from the smooth in-band path to a wigglier line tracking the mids, RMS to mid drops, and the smile's second derivative gets noisier in the density view.",
    activation: "Read only in the band fit targets (`bidask` / `haircut`).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["fitMode", "midAnchorTauRef", "haircut", "bandTickFloorTicks"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "midAnchorTauRef",
    model: "fit",
    section: "opt-calibration",
    label: "Mid anchor τ-ref (yrs)",
    unit: "years",
    summary: "Reference maturity below which the band-mode mid anchor fades like √(τ/ref), so short-dated tick staircases stop outgunning the shape regularization.",
    details:
      "A slice's data rows scale like 1/√τ at short maturities while the shape ridge is τ-free, so at one week the tick-quantized mid staircase outguns the regularization about 7×. With a reference set, the effective anchor is `midAnchorWeight · min(1, √(τ/ref))`: full strength at and beyond the reference, fading below it — a maturity-uniform anchor-versus-shape contest.\n\n" +
      "Empty (null) is the historical constant anchor, byte-identical. It only moves a band fit whose hinge rows are active: an all-in-band fit is a pure rescale with the same optimum.",
    example:
      "Set `midAnchorTauRef` to 0.25 in Haircut mode on a 1-week slice (τ ≈ 0.02): the anchor drops to about 28% of `midAnchorWeight`, the fitted smile stops following the 1-tick staircase of the far-wing mids and smooths through the bands, while the 6-month slices refit identically.",
    activation: "Read only in the band fit targets (`bidask` / `haircut`).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["midAnchorWeight", "bandTickFloorTicks", "robustLoss", "fitMode"],
    docs: ["07_calibration_objective_measure", "11_event_market_clock"],
  },
  {
    key: "bandTickFloorTicks",
    model: "fit",
    section: "opt-calibration",
    label: "Band tick floor (ticks)",
    unit: "ticks (price tick size of the chain)",
    summary: "Floor each quote's IV band half-width at the IV width of this many price ticks, so a spread narrower than a tick no longer implies sub-tick IV certainty.",
    details:
      "A short-dated wing quote whose bid-ask prints below the price tick grid carries an IV band tighter than the market ever quoted. In the band fit targets each quote's band is widened about its mid to at least `ticks × tick / vega` in IV (vega floored at 1e-4 so deep-wing quotes saturate instead of diverging), applied AFTER the haircut so the floor wins, and only ever widening — a side already wider than the floor keeps its asymmetry.\n\n" +
      "0 is off and byte-identical. It needs a feed with a known tick size, so synthetic or IV-exact chains are unaffected.",
    example:
      "Set `bandTickFloorTicks` to 1 in Bid-Ask mode on a 3-day SPX book: the 5Δ put quotes with 2-tick spreads get bands about a vol point wide instead of two or three tenths, the ragged far-wing staircase stops binding and the fitted wing smooths, while the high-vega ATM bands are untouched.",
    activation: "Read only in the band fit targets (`bidask` / `haircut`), on chains with a tick size.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["haircut", "midAnchorTauRef", "overlayPriceResiduals", "fitMode"],
    docs: ["07_calibration_objective_measure", "09_wings_last_quote"],
  },
  {
    key: "robustLoss",
    model: "fit",
    section: "opt-calibration",
    label: "Robust loss",
    summary: "Down-weight gross off-market quotes through an IRLS re-solve on the data rows only (Huber or Cauchy).",
    details:
      "After the base fit, each quote's residual magnitude is compared with `robustFScale`; residuals beyond it get a multiplier — `huber`: `min(1, f/|r|)`, a linear taper; `cauchy`: `1/(1 + (r/f)²)`, a harder redescending cut — and the slice is refit warm-started (two passes). Only the QUOTE rows are reweighted: a global robust loss would also soften the no-arbitrage, calendar and prior rows, which must stay quadratic. Reported weights and RMS stay on the original weights.\n\n" +
      "`off` is a single fit, byte-identical. It is not a substitute for excluding a quote in the smile editor — a robust fit still passes near a bad print, it just stops the print from bending the whole smile.",
    example:
      "Set `robustLoss` to `huber` with `robustFScale` at 0.005 on a slice where one 15Δ call prints 3 vol pt off its neighbours: the second pass gives that quote about one sixth of its weight, the smile no longer dips toward it, and its residual in the Quality table grows while every other residual shrinks.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["robustFScale", "weightScheme", "midAnchorTauRef", "help:guides:quality"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "robustFScale",
    model: "fit",
    section: "opt-calibration",
    label: "Robust f-scale",
    unit: "vol (the residual's own units)",
    summary: "Residual size below which a quote keeps full weight under `robustLoss`.",
    details:
      "Expressed in the residual's own units — vol for the SVI / MCS vol-space objective, vega-normalized price (≈ vol) for LQD and for overlays under `overlayPriceResiduals`. The default 0.005 (0.5 vol pt) is about one liquid half-spread: routine misfit keeps full weight, anything beyond it starts to taper.\n\n" +
      "Too small and the robust pass down-weights half the book so the fit under-uses the data; too large and it never engages.",
    example:
      "Lower `robustFScale` from 0.005 to 0.001 with `cauchy` on a normal SPY slice: most quotes now sit past the scale, their multipliers fall to 0.1-0.5, the effective quote count halves and the smile loosens toward the regularizer; at 0.02 the same slice is byte-identical to the non-robust fit.",
    activation: "Read only while `robustLoss` is not `off`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["robustLoss", "haircut"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "overlayPriceResiduals",
    model: "fit",
    section: "opt-calibration",
    label: "Price-space overlays",
    summary: "Fit SVI / MCS on vega-normalized price residuals (the LQD convention) instead of raw vol residuals.",
    details:
      "LQD has always fitted in vega-normalized price space: a deep-wing quote whose one-tick price quantum is worth several vol points enters at its price weight, not its vol weight. Historically the SVI and MCS overlays fitted raw vol residuals, so on a short-dated far wing that multi-vol-point tick quantum entered at full weight and bent the overlay. With this on, the overlay residuals switch to price space — vega frozen at the mid and floored, band edges converted to price — closing the committee R1 deferral; SVI keeps its analytic Jacobian in price mode, MCS rides finite differences while the toggle is on.\n\n" +
      "Off is the historical vol-space objective, byte-identical. It does not change what `weightScheme` does — weights multiply whichever residual is in use.",
    example:
      "Turn `overlayPriceResiduals` on for `svi` on a 2-day single-name slice with 1-tick far-put quotes: the SVI put wing, which used to kink toward a deep put printing 4 vol pt off, now runs smoothly under it; the overlay's vol RMS rises on that one strike and falls everywhere else, and the LQD fit is unchanged.",
    activation: "Read for `svi` / `sigmoid` fits.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["model", "bandTickFloorTicks", "weightScheme", "robustFScale"],
    docs: ["07_calibration_objective_measure", "09_wings_last_quote"],
  },
];
