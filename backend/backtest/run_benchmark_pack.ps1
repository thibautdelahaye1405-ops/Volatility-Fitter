# Full 25-asset graph-LOO benchmark pack (resumable) — run in YOUR OWN
# PowerShell window (tool-managed background jobs get killed on this box).
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_benchmark_pack.ps1
#
# Scores every captured regime chunk-by-chunk (part files under
# backend\backtest\results\benchmark\; existing parts are skipped, so rerun
# after any interruption), then renders benchmark_report.html + the JSON.
# Expect several hours for the full_loo sweep over 3 regimes x ~19 pairs.
param(
    [string]$Regime = "",       # empty = all captured regimes
    [int]$Chunk = 2,            # day pairs per resumable part file
    [string]$Designs = "full_loo,liquid_split",
    [string]$RValues = "0,1"
)

$backend = Split-Path -Parent $PSScriptRoot
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"
Set-Location $backend

$args = @("-m", "backtest.benchmark_pack", "run", "--chunk", "$Chunk",
          "--designs", $Designs, "--regimes-r", $RValues)
if ($Regime -ne "") { $args += @("--regime", $Regime) }

& $py @args
if ($LASTEXITCODE -ne 0) { Write-Host "run failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

& $py -m backtest.benchmark_pack report
