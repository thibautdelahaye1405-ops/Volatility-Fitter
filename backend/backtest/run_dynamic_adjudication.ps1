# Dynamic-harmonic Phase-5 adjudication — the layered operator vs the
# adjudicated message/smooth-field arms (framework
# Docs/dynamic_directed_harmonic_graph_framework.md §16, ROADMAP "DYNAMIC
# DIRECTED-HARMONIC ARC" Phase 5).
#
# Run in YOUR OWN PowerShell window (tool-managed background jobs get killed
# on this box). Resumable: each variant writes tagged part files under
# backend\backtest\results\benchmark\; existing parts are skipped.
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_dynamic_adjudication.ps1
#
# COMPARATORS: the completed campaign-1 parts (_b14_base smooth-field
# baseline, _p4_msg_learned message winner) are already on disk — do NOT
# re-run them; the decision table reads them directly.
#
# FOUR first-wave variants (second wave — D6 joint anchors, screened,
# Kalman-vs-hard — only if the verdict warrants):
#
#   _p5_dyn_desk   layered, residuals fully persistent (no half-life)
#   _p5_dyn_hl1    residual half-life 1 day   (fast reversion)
#   _p5_dyn_hl5    residual half-life 5 days  (the a-priori favourite)
#   _p5_dyn_hl20   residual half-life 20 days (slow reversion)
#
# CHUNKING CAVEAT (why -Chunk 9, unlike campaign 1's 2): the layered mode
# threads a persistent residual store CHRONOLOGICALLY through each chunk's
# day pairs, and chunks cold-start the store. A large chunk keeps the OOS
# window (pairs 10-18) in ONE part so persistence actually spans it; the
# price is coarser resumability (an interrupted variant restarts its
# regime's part). The FIRST OOS pair of each chunk is store-cold — identical
# across variants, so comparisons stay fair; the FINDINGS template carries
# this caveat.
#
# Same strict OOS window as campaign 1 (--pair-start 10). Budget roughly
# half a pack sweep per variant — several hours for all four.
# TRAP: never add --max-pairs (it caps the TOTAL count; with --pair-start 10
# it silently scores an empty range).
#
# --------------------------------------------------------------------------
# PRE-REGISTERED ADOPTION GATE (framework §16.3 — decide from these):
#   layered_dynamic_harmonic becomes a product-selectable default ONLY IF,
#   on the OOS window:
#     1. full_loo dark-target RMS improves vs the transported prior AND
#        _b14_base AND _p4_msg_learned (the temporal residual must EARN its
#        state — full_loo is the lit->dark one-step transition test);
#     2. liquid_split non-degrading vs _p4_msg_learned (names are dark all
#        week there, so no residual memory — this isolates the directed
#        systematic layer + boundary clamp);
#     3. stressed regimes (spike_aug2024, high_oct2022) non-degrading;
#     4. zeta std ~1 and cov80/cov95 near nominal (the boundary-variance +
#        residual-variance accounting must stay honest);
#     5. reverse leakage identically ZERO (structural — verified by the
#        Phase-2/4 test locks, reported for completeness);
#     6. wing RMS does not deteriorate.
#   The half-life sweep picks the default H by full_loo skill x coverage;
#   ties break toward LONGER H (fewer invented reversions).
# --------------------------------------------------------------------------

param(
    [int]$PairStart = 10,                          # strict OOS eval window
    [int]$Chunk = 9,                               # ONE part per regime: warm store
    [string]$Designs = "full_loo,liquid_split",
    [string[]]$Variants = @("dyn_desk", "dyn_hl1", "dyn_hl5", "dyn_hl20")
)

$backend = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"
Set-Location $backend

function Invoke-Step($label, $stepArgs) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    & $py @stepArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "$label FAILED ($LASTEXITCODE)"; exit $LASTEXITCODE }
}

$common = @("--pair-start", "$PairStart", "--chunk", "$Chunk", "--designs", $Designs,
            "--mode", "layered_dynamic_harmonic")

if ($Variants -contains "dyn_desk") {
    Invoke-Step "sweep: layered, persistent residuals (_p5_dyn_desk)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p5_dyn_desk") + $common)
}
if ($Variants -contains "dyn_hl1") {
    Invoke-Step "sweep: layered, half-life 1d (_p5_dyn_hl1)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p5_dyn_hl1",
           "--residual-half-life", "1") + $common)
}
if ($Variants -contains "dyn_hl5") {
    Invoke-Step "sweep: layered, half-life 5d (_p5_dyn_hl5)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p5_dyn_hl5",
           "--residual-half-life", "5") + $common)
}
if ($Variants -contains "dyn_hl20") {
    Invoke-Step "sweep: layered, half-life 20d (_p5_dyn_hl20)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p5_dyn_hl20",
           "--residual-half-life", "20") + $common)
}

Write-Host "`nAll requested variants complete. Next: ask the agent to score the"
Write-Host "parts against the section-16.3 gate and fill in"
Write-Host "backend\backtest\FINDINGS_dynamic_phase5.md."
