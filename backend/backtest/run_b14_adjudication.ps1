# R3 item-14 adjudication sweep — learned shrunk betas + OT ablation.
# Run in YOUR OWN PowerShell window (tool-managed background jobs get killed
# on this box). Resumable: each variant writes tagged part files under
# backend\backtest\results\benchmark\; existing parts are skipped, so re-run
# after any interruption and it picks up where it stopped.
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_b14_adjudication.ps1
#
# Scores the STRICT-TIME-SPLIT evaluation half only (--pair-start 10; the
# regressions in learned_betas.json saw only pairs < 10, so pairs 10-18 are
# strictly out-of-sample everywhere). Three variants, each its own tag:
#   _b14_base     production edges (hand-set betas, OT off)  <- baseline
#   _b14_learned  learned betas injected as edge overrides
#   _b14_ot       OT flux on at lambda=1.0 (comparable to the kappa belief)
# then benchmark_compare prints the verdict table (skill deltas vs baseline).
#
# Expect ~half a normal pack sweep (10 of 19 pairs x 3 regimes x 2 designs).
#
# TRAP (learned the hard way): do NOT add --max-pairs here. --max-pairs caps
# the TOTAL pair count, so "--max-pairs 1 --pair-start 10" scores an EMPTY
# range and silently does nothing. --pair-start alone is what you want.
#
# --------------------------------------------------------------------------
# PRE-REGISTERED DECISION RULE (FINDINGS_graph_loo.md 2026-07-17):
#   Activate learned betas ONLY IF the liquid_split dark-name ATM skill delta
#   is POSITIVE in spike_aug2024 AND NON-NEGATIVE in the other two regimes,
#   with zeta std not degrading. Same bar for OT (the lambda=1.0 probe) — else
#   REPOSITION the OT story as Bayesian graph propagation (the deck honesty
#   pass already leans that way). Otherwise the learned_betas artifact stays a
#   diagnostic, not a production input.
# --------------------------------------------------------------------------

param(
    [int]$PairStart = 10,                          # strict OOS eval window
    [int]$Chunk = 2,                               # day pairs per resumable part
    [string]$Designs = "full_loo,liquid_split",
    [double]$Lambda = 1.0                          # OT flux weight for the probe
)

$backend = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"
Set-Location $backend
$betaTable = "backtest\results\learned_betas.json"

function Invoke-Step($label, $stepArgs) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    & $py @stepArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "$label FAILED ($LASTEXITCODE)"; exit $LASTEXITCODE }
}

# 0) (Re)generate the learned-beta artifact — offline over the stored rows,
#    gitignored/regenerable, so guarantee it is fresh before the sweep.
Invoke-Step "fit learned betas" @("-m", "backtest.learn_betas", "fit")

$common = @("--pair-start", "$PairStart", "--chunk", "$Chunk", "--designs", $Designs)

# 1) baseline  2) learned betas  3) OT probe
Invoke-Step "sweep: baseline (_b14_base)" `
    (@("-m", "backtest.benchmark_pack", "run", "--tag", "_b14_base") + $common)
Invoke-Step "sweep: learned betas (_b14_learned)" `
    (@("-m", "backtest.benchmark_pack", "run", "--tag", "_b14_learned",
       "--beta-table", $betaTable) + $common)
Invoke-Step "sweep: OT lambda=$Lambda (_b14_ot)" `
    (@("-m", "backtest.benchmark_pack", "run", "--tag", "_b14_ot",
       "--lambda", "$Lambda") + $common)

# 4) verdict table — skill deltas vs baseline on the SHARED scored set.
Invoke-Step "verdict table" `
    @("-m", "backtest.benchmark_compare", "--tags", "_b14_base,_b14_learned,_b14_ot")

Write-Host "`nAdjudicate on the liquid_split rows per the decision rule above." -ForegroundColor Green
Write-Host "Verdict JSON: backtest\results\benchmark\ablation_compare.json"
