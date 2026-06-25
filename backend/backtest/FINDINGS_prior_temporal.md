# Prior-persistence — temporal mode-scoring findings (2026-06-25)

Empirical results from `backtest/temporal.py` (the Phase-8 temporal axis of
`Docs/prior_persistence_roadmap.md`). Method: for each consecutive captured day
pair (T-1, T) and asset, freeze T-1's full-chain fit as the active prior, thin day
T to its ATM region (`|k| ≤ c_atm·σ√τ`, `c_atm=0.5`), refit LQD-6 under each
`priorPersistenceMode`, and score the reconstructed MODERATE wing
(`c_atm·σ√τ < |k| ≤ c_wing·σ√τ`, `c_wing=2.0`, held out) vs the true day-T quotes.
`off` (no prior) is the baseline each mode must beat. Metrics are per-(mode,
bandwidth, probe): median wing RMS (bp), median improvement over off (bp,
per-node), and win-rate (fraction of nodes the prior beats its own off baseline).

## Run 1 — full spike_aug2024, default knobs (8 assets, 1117 nodes, all 19 pairs)

    mode             bw  probe    n   medRMS   medImp   win
    hybrid          0.06   1.4 1116    95.1    +32.4   0.66
    strike_gap      0.06   1.4 1116   106.9    +28.2   0.63
    quote_operator  0.06   1.4 1117   150.9     0.0    0.30
    smile_factor    0.06   1.4 1117   150.9     0.0    0.34

`off` baseline median ≈ 151 bp (quote_operator/smile_factor are inert at the median
⇒ they fit identically to off on > 50% of nodes).

## Run 2 — bandwidth × probe sweep (spike, 4 pairs/asset, 237 nodes)

`hybrid` is best at EVERY (bw, probe) — medImp +30 to +41 bp, win ≈ 0.64–0.65.
`quote_operator` medImp ≈ 0 at EVERY (bw, probe); at bw=0.12 it degrades (win 0.02).

    mode             bw  probe   medRMS   medImp   win
    hybrid          0.12   1.0   130.7    +39.6   0.65
    hybrid          0.06   1.0   130.7    +32.7   0.65
    hybrid          0.02   1.0   136.7    +41.3   0.65
    hybrid          0.06   1.4   132.0    +32.5   0.65
    quote_operator  0.02   1.0   191.0     0.0    0.44
    quote_operator  0.06   1.4   205.7     0.0    0.35
    quote_operator  0.12   1.0   228.3     0.0    0.02

(Run-2 absolute RMS sits higher than Run-1 because `--max-pairs 4` keeps only the
earliest, pre-spike pairs; the baseline-relative *improvement* — the robust signal —
matches Run-1 at +32 bp.)

## Verdict

1. **`hybrid` is the correct default** — validated across the full regime and the
   knob sweep; it reconstructs the held-out wing ~32 bp better than no-prior, ~66%
   of the time. `strike_gap` is a close second.
2. **`priorOperatorBandwidth` (0.06) is NOT a productive lever.** Pure
   `quote_operator` / `smile_factor` never beat `off` at the median, at any
   bandwidth. The wing reconstruction comes from the **tail / strike anchor**
   (present in `hybrid` and `strike_gap`), not the signed RR/BF operators — so the
   "leaky bandwidth" concern flagged at Phase 8 is real but immaterial to the
   winning mode. **No change made.**
3. **Var-swap probe (`_VARSWAP_PROBE_STD`, 1.4σ): leave at 1.4 for now.** Probe 1.0
   marginally edges 1.4 for `hybrid` (+39.6 vs +32.7 bp at bw=0.12), but the gap is
   small and measured on the pre-spike subset only. The one candidate worth a
   full-regime (and cross-regime) confirmation before flipping a shipped default;
   not changed unilaterally.

**Net: the temporal harness confirms the shipped defaults; no tuning change is
warranted on this evidence.** Next: re-run across `high_oct2022` / `low_jul2023`
to confirm the mode ranking and the probe-1.0 candidate are regime-robust.
