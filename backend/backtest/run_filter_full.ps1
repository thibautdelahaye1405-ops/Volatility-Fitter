# Full-regime observation-filter backtest (Phase 7, Note 15) — resumable.
#
# Runs backtest.observation_filter per (regime, asset) as separate processes
# (a crash on one asset never kills the batch) and SKIPS an asset whose result
# file already holds a full run (> 200 rows; the 1-pair pilot files hold ~110,
# so they are redone). Relaunch after any interruption to resume.
#
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_filter_full.ps1
#   ... -Regimes spike_aug2024            # one regime only
#
# Aggregate afterwards with backtest.observation_filter's summarize over the
# per-asset JSONs (see FINDINGS_observation_filter.md).
param(
    [string[]]$Regimes = @("spike_aug2024", "high_oct2022", "low_jul2023"),
    [string[]]$Assets = @("SPX", "NDX", "RUT", "EEM", "EFA", "AAPL", "JPM", "NVDA"),
    [string]$ProcessBps = "30",
    [string]$Modes = "overlay,active",
    [string]$Tag = "v2"
)

$backend = Split-Path $PSScriptRoot -Parent
$py = Join-Path (Split-Path $backend -Parent) ".venv\Scripts\python.exe"
Push-Location $backend
try {
    foreach ($regime in $Regimes) {
        foreach ($a in $Assets) {
            $suffix = if ($Tag) { "_$a`_$Tag" } else { "_$a" }
            $out = Join-Path $PSScriptRoot "results\${regime}_observation_filter$suffix.json"
            if (Test-Path $out) {
                try { $rows = (Get-Content $out -Raw | ConvertFrom-Json).rows.Count } catch { $rows = 0 }
                if ($rows -gt 200) {
                    Write-Host "skip $regime $a (already $rows rows)"
                    continue
                }
            }
            Write-Host (">>> {0} {1}  {2}" -f $regime, $a, (Get-Date -Format "yyyy-MM-dd HH:mm"))
            & $py -m backtest.observation_filter --regime $regime --asset $a `
                --process-bps $ProcessBps --modes $Modes --tag $Tag
            if ($LASTEXITCODE -ne 0) {
                Write-Host "!!! $regime $a exited $LASTEXITCODE (continuing)"
            }
        }
    }
    Write-Host ("=== batch complete {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))
}
finally {
    Pop-Location
}
