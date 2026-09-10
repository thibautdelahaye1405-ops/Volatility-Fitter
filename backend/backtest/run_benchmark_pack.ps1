# Full 25-asset graph-LOO benchmark pack (resumable) — run in YOUR OWN
# PowerShell window (tool-managed background jobs get killed on this box).
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_benchmark_pack.ps1 [-Tag _mytag]
#
# Scores every captured regime chunk-by-chunk (part files under
# backend\backtest\results\benchmark\; existing parts of the SAME tag are
# skipped, so rerun after any interruption), then renders the report
# (benchmark_report<tag>.html + benchmark_pack<tag>.json).
# Expect several hours for the full_loo sweep over 3 regimes x ~19 pairs.
#
# THE KNOBS ARE THE RATIFIED ONES (R0 wrap; the July `_topofix_eta10` /
# `_idiofloor_eta10` sweeps): --eta 10 --cross-mult 25 (index weight 2 x 25 =
# 50). The 2026-09-09 `_lvop` sweep ran without them (eta 1, cross-mult 1) and
# its liquid-split skill read 0 everywhere — not an adjudication (STATUS item 1,
# wrap 2026-09-10b). Override deliberately with -Eta / -CrossMult; -DryRun
# prints the argument list and exits.
param(
    [string]$Regime = "",       # empty = all captured regimes
    [int]$Chunk = 2,            # day pairs per resumable part file
    [string]$Designs = "full_loo,liquid_split",
    [string]$RValues = "0,1",
    [double]$Eta = 10.0,        # the ratified signal-to-prior ratio (NOT the CLI default of 1)
    [double]$CrossMult = 25.0,  # the ratified cross-asset weight multiplier (index 2 -> 50)
    [string]$Tag = "",          # names the sweep's part files / report (e.g. "_v3flips")
    [switch]$DryRun             # print the python argument list and exit
)

$backend = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"
Set-Location $backend

$args = @("-m", "backtest.benchmark_pack", "run", "--chunk", "$Chunk",
          "--designs", $Designs, "--regimes-r", $RValues,
          "--eta", "$Eta", "--cross-mult", "$CrossMult")
if ($Regime -ne "") { $args += @("--regime", $Regime) }
if ($Tag -ne "") { $args += @("--tag", $Tag) }

$reportArgs = @("-m", "backtest.benchmark_pack", "report")
if ($Tag -ne "") { $reportArgs += @("--tag", $Tag) }

if ($DryRun) {
    Write-Host "run:    $py $($args -join ' ')"
    Write-Host "report: $py $($reportArgs -join ' ')"
    exit 0
}

& $py @args
if ($LASTEXITCODE -ne 0) { Write-Host "run failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

& $py @reportArgs
