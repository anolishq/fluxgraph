# FluxGraph benchmark wrapper (preset-first)
# Usage:
#   .\scripts\bench.ps1 [-Preset <name>] [-Config <cfg>] [-OutputDir <path>] [-IncludeOptional]
#                      [-NoBuild] [-FailOnStatus] [-PolicyProfile <name>] [-PolicyFile <path>]
#                      [-Baseline <path>] [-NoEvaluate]

param(
    [string]$Preset = "",
    [string]$Config = "",
    [string]$OutputDir = "",
    [switch]$IncludeOptional,
    [switch]$NoBuild,
    [switch]$FailOnStatus,
    [string]$PolicyProfile = "local",
    [string]$PolicyFile = "",
    [string]$Baseline = "",
    [switch]$NoEvaluate,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThroughArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $Preset) {
    if ($env:OS -eq "Windows_NT") {
        $Preset = "dev-windows-release"
    }
    else {
        $Preset = "dev-release"
    }
}

if (-not $env:VCPKG_ROOT) {
    Write-Warning "VCPKG_ROOT is not set. Presets may fail to configure."
}

if (-not $OutputDir) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $RepoRoot "artifacts/benchmarks/${timestamp}_${Preset}"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot $OutputDir
}

if (-not $PolicyFile) {
    $PolicyFile = Join-Path $RepoRoot "benchmarks/policy/bench_policy.json"
}
elseif (-not [System.IO.Path]::IsPathRooted($PolicyFile)) {
    $PolicyFile = Join-Path $RepoRoot $PolicyFile
}

if ($Baseline -and -not [System.IO.Path]::IsPathRooted($Baseline)) {
    $Baseline = Join-Path $RepoRoot $Baseline
}

$Args = @("$PSScriptRoot/run_benchmarks.py", "--preset", $Preset)

if ($Config) {
    $Args += @("--config", $Config)
}
$Args += @("--output-dir", $OutputDir)
if ($IncludeOptional) {
    $Args += "--include-optional"
}
if ($NoBuild) {
    $Args += "--no-build"
}
if ($FailOnStatus) {
    $Args += "--fail-on-status"
}
if ($PassThroughArgs) {
    $Args += $PassThroughArgs
}

Push-Location $RepoRoot
try {
    Write-Host "[BENCH] python $($Args -join ' ')" -ForegroundColor Cyan
    & python @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark run failed with exit code $LASTEXITCODE"
    }

    if (-not $NoEvaluate) {
        $EvalArgs = @(
            "$PSScriptRoot/evaluate_benchmarks.py",
            "--results", (Join-Path $OutputDir "benchmark_results.json"),
            "--policy", $PolicyFile,
            "--profile", $PolicyProfile,
            "--output", (Join-Path $OutputDir "benchmark_evaluation.json")
        )
        if ($Baseline) {
            $EvalArgs += @("--baseline", $Baseline)
        }
        Write-Host "[EVAL] python $($EvalArgs -join ' ')" -ForegroundColor Cyan
        & python @EvalArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Benchmark policy evaluation failed with exit code $LASTEXITCODE"
        }
    }
}
finally {
    Pop-Location
}
