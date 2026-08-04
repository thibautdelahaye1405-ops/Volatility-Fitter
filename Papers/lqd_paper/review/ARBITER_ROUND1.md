# Arbiter findings — round 1 (lead's own review, independent of the student)

Compiled 2026-08-03 after the first full build (47 pp) and cross-checking
the draft against the figure engineer's measured results.

## A. Text–data conflicts (MUST fix in round 2)

1. **SPY "haircut bands" that do not exist.** §13.1 ("quotes as haircut
   bands"), fig:spy_gallery caption ("quote haircut bands (whiskers)"),
   and fig:spy_node caption ("haircut bands and the fitted slice") clash
   with the data: every SPY spread in the snapshot (4–14 vol bp) is
   tighter than 2h = 100 vol bp, so under eq (haircut) every SPY quote
   degenerates to a mid target, and the figures correctly draw raw
   bid–ask whiskers + mids. Fix: reword gallery/node text + captions to
   raw bid–ask; ADD the degeneracy as the live example of §9.2's collapse
   clause (SPY: 0% live bands; NVDA 1d/long: ~47%/52% live — macros
   exist: \Mac*BandLivePct). This strengthens the paper: the haircut
   mechanism's degeneracy guard is not hypothetical.
2. **Order-control overclaim.** §13.4 says at N=6 "the density is
   unimodal: the trough is smoothed away entirely"; fig:order_control
   caption says "smooths the trough away". Measured: N=6 KEEPS both
   modes (distorted, trough half-filled, modes displaced); the honest
   carrier of the claim is the L1 distance doubling (0.047 → 0.108) and
   the valley/peak ratio macros. Reword text + caption; the
   information-vs-convention lesson survives intact, stated honestly.
3. **Lee effective-slope direction is two-sided on real data.** §6.4 +
   fig:lee caption claim the effective slope "descends toward the limit
   from above" and "still exceeds the limit" at 10Δ/1Δ. Measured on the
   fitted SPY December slice: right wing approaches from above (1Δ ratio
   ≈ 1.05); LEFT wing UNDERSHOOTS (1Δ ratio ≈ 0.70 — below the limit).
   Rewrite the honesty clause two-sided: the effective slope differs
   from the asymptote by economically large factors IN EITHER DIRECTION
   at tradable strikes — which makes the "never price a wing off β"
   conclusion stronger, not weaker. Verify the macro values' convention
   (ratio effective/limit) against what the generator emits.
4. **Unmeasured claim in §9.5.** "on the liquid strips of §13 ten
   randomized starts converge to one basin, a measurement, not a
   theorem" — no such measurement exists yet. Engineer has been asked to
   run a 10-random-start audit on SPY Dec + NVDA long and emit macros
   (\MacMultiStartNodes, \MacMultiStartCount, \MacMultiStartWorstDTheta
   or similar). If the audit is not run, the sentence must be struck.
   (If the audit FAILS — multiple basins — that is a finding to report,
   not to hide.)
5. **fig:doublehump caption encoding.** Caption says "true mixture
   density (line) and the fitted LQD density (shaded)"; the produced
   figure shades the true density and dashes the recovered one. Align
   caption with the actual encoding (check the PDF).

## B. Constant-audit values (verify wording, no overshoot)

6. §4/F3 and §13.5: the exact-audit agreement is ~1e-11 (transport
   linearity) and ~3e-9 (normalization), NOT machine epsilon; ensure no
   phrasing implies 1e-15. \MacExactMaxErr = worst of the trio.
7. \MacCalPriceGridWorst: generator computed the actual worst
   price-space calendar gap on the display grid (~2.2e-15 of forward);
   the number replaces the README's "< 1e-6" inequality phrasing.

## C. Resolutions of AUTHOR_NOTES open questions

1. Cold-start bias 6(log2)^2/pi as derived constant: KEEP; F3 inset
   confirms measured ≈ −8% at the 20%-vol toy. No macro needed.
2. Latency-cliff source: DECIDED — recomputed on the frozen NVDA
   2026-08-05 node (17 quotes), macros from the generator; §9.4's
   "same-day strip" phrasing already fits. Ensure §9.4 does not claim a
   19-quote strip anywhere.
3. Canonical node: SPY 2026-12-18 confirmed as the single shared slice
   across F5/F7/F8/F9/F12/F14 + ticket (engineer loads it once).
4. \MacCalPriceGridWorst: see B.7 — the number, not the inequality.
5. Title: KEEP "The Log-Quantile-Density Model of the Volatility Smile:
   Validity, Information, and Convention".
6. Benaim–Friz exact theorem number: OPEN — verify at final polish
   (lead will check the 2009 paper; right-tail case is Theorem 1 /
   left-tail Theorem 2 in MF 19(1), to be confirmed before submission).

## D. Verified by the lead (no action)

- Order-guard formula (§9.4, eq orderguard) matches the implementation
  including the min(N,6) floor and predicts N_eff=7 on 17 quotes. ✓
- Envelope theorem proof (§10) and the barrier chain
  ∂λ₊/∂θ = λ₊·(0,1,1,−1,…) sign pattern. ✓
- Vega formula ∂_σ B = φ(d₊)√τ for the normalized call. ✓
- Full build: 47 pp, bibtex clean, zero undefined references/citations,
  zero missing-figure placeholders with all 14 PDFs present. Macro gap:
  65 names pending generator aliases/computations (engineer running).
