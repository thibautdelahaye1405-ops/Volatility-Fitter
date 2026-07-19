# Message-arc Phase-4 adjudication — precision-message operator vs the
# smooth-field graph, ABSORBING the parked R3 item-14 learned-betas sweep
# (one combined campaign; spec Docs/graph_precision_message_framework.md
# §22-23, ROADMAP "PRECISION-MESSAGE GRAPH ARC" P4).
#
# Run in YOUR OWN PowerShell window (tool-managed background jobs get killed
# on this box). Resumable: each variant writes tagged part files under
# backend\backtest\results\benchmark\; existing parts are skipped, so re-run
# after any interruption and it picks up where it stopped.
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_message_adjudication.ps1
#
# Scores the STRICT-TIME-SPLIT evaluation half only (--pair-start 10: the
# learned-beta/amplitude presets saw only pairs < 10 in every regime, so
# pairs 10-18 are strictly out-of-sample). SIX variants, each its own tag:
#
#   _b14_base       smooth-field, production edges (hand-set betas)  <- baseline
#   _b14_learned    smooth-field + learned beta overrides            (item 14)
#   _p4_msg_desk    message operator, DESK amplitudes (rho = 1)      (full force)
#   _p4_msg_learned message operator, LEARNED amplitudes
#                   (--amp-cal 0.23, --amp-cross 0.39 — the Phase-0
#                   single-source targets; node-linked corroboration
#                   lifts multi-source receivers automatically)
#   _p4_msg_a05     message learned amplitudes, alphaT = 0.5         (shape ablation)
#   _p4_msg_const   message learned amplitudes, constant calendar
#                   precision                                        (decay ablation)
#
# Second wave (only if the verdict warrants): _b14_ot (OT probe), alphaT=0,
# amplitude refinement around the winner, hybrid.
#
# Expect roughly half a normal pack sweep PER VARIANT (10 of 19 pairs x 3
# regimes x 2 designs) — budget several hours for all six; interrupt and
# re-run freely.
#
# TRAP (learned the hard way): do NOT add --max-pairs here. --max-pairs caps
# the TOTAL pair count, so "--max-pairs 1 --pair-start 10" scores an EMPTY
# range and silently does nothing. --pair-start alone is what you want.
#
# --------------------------------------------------------------------------
# PRE-REGISTERED ADOPTION GATE (spec §22.4 — decide from these, not vibes):
#   Precision-message becomes the product default ONLY IF, on liquid_split
#   dark names over the OOS window:
#     1. calendar/ATM skill improves materially vs the transported prior AND
#        the smooth-field baseline (_b14_base);
#     2. non-degrading in the stressed regimes (spike_aug2024, high_oct2022);
#     3. calm-regime (low_jul2023) skill not negative beyond tolerance;
#     4. zeta std stays ~1 and 50/80/95% band coverage (cov80/cov95 columns)
#        stays near nominal after the idio floor;
#     5. no unstable cycles (cycleDiagnostics stayed empty — the taxonomy is
#        gauge-consistent by construction);
#     6. wing RMS (reconstructed smiles) does not deteriorate.
#   Desk full-force (_p4_msg_desk) is EXPECTED to lose RMS at this horizon —
#   it ships as the opt-in preset either way; the gate decides the DEFAULT
#   amplitude preset. Item-14 rule carries over unchanged for _b14_learned
#   (activate learned betas only on positive spike delta, non-negative
#   elsewhere, zeta std not degrading).
# --------------------------------------------------------------------------

param(
    [int]$PairStart = 10,                          # strict OOS eval window
    [int]$Chunk = 2,                               # day pairs per resumable part
    [string]$Designs = "full_loo,liquid_split",
    [string[]]$Variants = @("base", "learned", "msg_desk", "msg_learned",
                            "msg_a05", "msg_const")
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

# 0) fresh learned-beta artifact (offline over stored rows; regenerable)
Invoke-Step "fit learned betas" @("-m", "backtest.learn_betas", "fit")

$common = @("--pair-start", "$PairStart", "--chunk", "$Chunk", "--designs", $Designs)
$msgLearned = @("--mode", "precision_messages", "--amp-cal", "0.23", "--amp-cross", "0.39")

if ($Variants -contains "base") {
    Invoke-Step "sweep: smooth-field baseline (_b14_base)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_b14_base") + $common)
}
if ($Variants -contains "learned") {
    Invoke-Step "sweep: smooth-field + learned betas (_b14_learned)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_b14_learned",
           "--beta-table", $betaTable) + $common)
}
if ($Variants -contains "msg_desk") {
    Invoke-Step "sweep: message DESK rho=1 (_p4_msg_desk)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p4_msg_desk",
           "--mode", "precision_messages") + $common)
}
if ($Variants -contains "msg_learned") {
    Invoke-Step "sweep: message LEARNED amplitudes (_p4_msg_learned)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p4_msg_learned") `
         + $msgLearned + $common)
}
if ($Variants -contains "msg_a05") {
    Invoke-Step "sweep: message alphaT=0.5 (_p4_msg_a05)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p4_msg_a05",
           "--alpha-t", "0.5") + $msgLearned + $common)
}
if ($Variants -contains "msg_const") {
    Invoke-Step "sweep: message constant calendar precision (_p4_msg_const)" `
        (@("-m", "backtest.benchmark_pack", "run", "--tag", "_p4_msg_const",
           "--cal-decay", "constant") + $msgLearned + $common)
}

# verdict table — skill deltas vs the smooth-field baseline on the SHARED set
Invoke-Step "verdict table" `
    @("-m", "backtest.benchmark_compare", "--tags",
      "_b14_base,_b14_learned,_p4_msg_desk,_p4_msg_learned,_p4_msg_a05,_p4_msg_const")

Write-Host "`nAdjudicate on the liquid_split rows per the PRE-REGISTERED gate above." -ForegroundColor Green
Write-Host "Verdict JSON: backtest\results\benchmark\ablation_compare.json"
Write-Host "Record the decision in backtest\FINDINGS_message_phase4.md"
