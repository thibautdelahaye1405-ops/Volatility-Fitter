# Intraday async-replay campaign launcher (framework §16.1) — USER'S-WINDOW job.
#
# Runs the seven pre-registered arms of FINDINGS_dynamic_intraday.md over the
# stored intraday sessions. Parts are per (tag, day) and SKIPPED when present,
# so the whole campaign is resumable: rerun this script after any interruption
# and it continues where it stopped. Expect a few hours for the full
# 8-session ETF triangle (states are rebuilt per instant; fits dominate).
#
# Usage (any cwd):
#   powershell -ExecutionPolicy Bypass -File backend\backtest\run_dynamic_intraday.ps1
#   ... -Db backtest\results\intraday_names.sqlite -Tickers SPY,NVDA,AAPL   # richer universe
#   ... -Arms intra_dyn_hl01,intra_dyn_mless                                # subset
#
# Afterwards:  cd backend ; ..\.venv\Scripts\python -m backtest.graph_intraday report

param(
    [string]$Db = '',
    [string]$Tickers = 'SPY,QQQ,IWM',
    [string]$Hub = 'SPY',
    [string]$Arms = 'intra_base,intra_msg,intra_dyn_mless,intra_dyn_desk,intra_dyn_hl1,intra_dyn_hl01,intra_dyn_hl002',
    [string]$RegimesR = '0,1',
    [int]$LitIdx = 3
)

$ErrorActionPreference = 'Stop'
$backend = Split-Path $PSScriptRoot
$repo = Split-Path $backend
$python = Join-Path $repo '.venv\Scripts\python.exe'
$env:PYTHONUNBUFFERED = '1'
# `-m backtest.graph_intraday` resolves the package from the working directory.
Push-Location $backend

# Arm -> (mode, half-life, memoryless) per the pre-registered table.
$armSpec = @{
    'intra_base'      = @('smooth_field', $null, $false)
    'intra_msg'       = @('precision_messages', $null, $false)
    'intra_dyn_mless' = @('layered_dynamic_harmonic', $null, $true)
    'intra_dyn_desk'  = @('layered_dynamic_harmonic', 'inf', $false)
    'intra_dyn_hl1'   = @('layered_dynamic_harmonic', '1.0', $false)
    'intra_dyn_hl01'  = @('layered_dynamic_harmonic', '0.1', $false)
    'intra_dyn_hl002' = @('layered_dynamic_harmonic', '0.02', $false)
}

try {
    foreach ($arm in ($Arms -split ',')) {
        $arm = $arm.Trim()
        if (-not $armSpec.ContainsKey($arm)) { throw "unknown arm '$arm'" }
        $mode, $hl, $memoryless = $armSpec[$arm]
        Write-Host ('=== {0}: mode={1} hl={2} memoryless={3}' -f $arm, $mode, $hl, $memoryless)
        $argList = @('-m', 'backtest.graph_intraday', 'run',
            '--tag', $arm, '--mode', $mode,
            '--tickers', $Tickers, '--hub', $Hub,
            '--regimes-r', $RegimesR, '--lit-idx', $LitIdx)
        if ($Db) { $argList += @('--db', $Db) }
        if ($null -ne $hl) { $argList += @('--half-life', $hl) }
        if ($memoryless) { $argList += '--memoryless' }
        & $python @argList
        if ($LASTEXITCODE -ne 0) {
            Write-Host ('{0} exited {1} - rerun this script to resume (finished days skip)' `
                -f $arm, $LASTEXITCODE)
            exit $LASTEXITCODE
        }
    }
    Write-Host 'All arms complete. Aggregate with: python -m backtest.graph_intraday report'
}
finally {
    Pop-Location
}
