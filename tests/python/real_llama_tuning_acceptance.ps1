[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$BaseUrl = 'http://127.0.0.1:11735',
    [double]$TargetTokensPerSecond = 100.0,
    [int]$Warmups = 2,
    [int]$Repeats = 5,
    [int]$CandidateLimit = 24,
    [string]$ExpectedSha256 = '626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d'
)

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = (Resolve-Path (Join-Path $scriptDirectory '..\..')).Path }
$rootPath = [IO.Path]::GetFullPath($Root)
$modelPath = Join-Path $rootPath 'models\Qwen--Qwen2.5-3B-Instruct-GGUF\qwen2.5-3b-instruct-q4_k_m.gguf'
$runtime = Join-Path $rootPath '.rift-runtime'
$reports = Join-Path $runtime 'reports'
$python = Join-Path $rootPath '.venv\Scripts\python.exe'
$configPath = Join-Path $runtime 'generated\latest.json'
$runStarted = Get-Date
# Keep the acceptance run entirely inside this checkout's existing runtime
# state; this also makes the command reproducible on locked-down Windows hosts.
$env:RIFT_HOME = $runtime
$evidence = [ordered]@{
    target_tokens_per_second = $TargetTokensPerSecond
    accuracy_tolerance = 0.05
    accuracy_case_tolerance = 0.15
    warmups = $Warmups
    repeats = $Repeats
    candidate_limit = $CandidateLimit
    model_path = $modelPath
    model_sha256 = $null
    weight_quantization = $null
    kv_precision_search = $true
    launch_command = $null
    capabilities = $null
    health = $null
    tuning = $null
    passed = $false
    failures = @()
}

function Fail([string]$Message) {
    $evidence.failures += $Message
    throw $Message
}

function JsonValue($Object, [string[]]$Names) {
    foreach ($name in $Names) {
        if ($null -ne $Object -and $null -ne $Object.PSObject.Properties[$name]) {
            return $Object.$name
        }
    }
    return $null
}

function Invoke-Rift([string[]]$Arguments, [switch]$AllowFailure) {
    if (-not (Test-Path -LiteralPath $python)) { Fail "Python executable missing: $python" }
    $out = & $python -m rift.cli --json @Arguments 2>&1
    $text = ($out | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFailure) { return $text }
        Fail "RIFT command failed ($LASTEXITCODE): $text"
    }
    try { return ($text | ConvertFrom-Json) }
    catch { return $text }
}

if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) { Fail "Exact Qwen model path is missing: $modelPath" }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { Fail "Generated deployment config is missing: $configPath" }
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$service = $config.config.services.chat
$selected = $service.model.selected_file
if (-not $selected) { $selected = $service.model.artifact.files[0].path }
if ([IO.Path]::GetFullPath([string]$selected) -ne [IO.Path]::GetFullPath($modelPath)) { Fail "Deployment model path is not the exact Qwen2.5-3B-Instruct Q4_K_M path: $selected" }
$quant = [string](JsonValue $service.model @('quantization'))
if ($quant.ToUpperInvariant() -ne 'Q4_K_M') { Fail "Weight quantization is not immutable Q4_K_M: $quant" }
$evidence.weight_quantization = $quant
$actualHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
$evidence.model_sha256 = $actualHash
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) { Fail "Model SHA-256 mismatch. Expected $ExpectedSha256, got $actualHash" }

# Probe the installed binary and the running endpoint before allowing restarts.
$health = Invoke-Rift @('backend','health','llama.cpp','--base-url',$BaseUrl)
$evidence.health = $health
if (-not [bool](JsonValue $health @('healthy'))) { Fail 'Running CUDA llama.cpp deployment is not healthy before tuning' }
$detect = Invoke-Rift @('backend','inspect','llama.cpp') -AllowFailure
$evidence.capabilities = JsonValue $detect @('capabilities','runtime_capabilities','detection')

$before = Get-ChildItem -LiteralPath $reports -Filter '*chat-profiled-tuning-speed.json' -File | Sort-Object LastWriteTime | Select-Object -Last 1
$tuning = Invoke-Rift @('tune','--service','chat','--profile','speed','--allow-restart','--yes','--budget','60m','--candidate-limit',([string]$CandidateLimit),'--warmups',([string]$Warmups),'--repeats',([string]$Repeats),'--target-tokens-per-second',([string]$TargetTokensPerSecond),'--accuracy-tolerance','0.05','--accuracy-case-tolerance','0.15','--kv-precision-search')
$after = Get-ChildItem -LiteralPath $reports -Filter '*chat-profiled-tuning-speed.json' -File | Where-Object { $_.LastWriteTime -ge $runStarted } | Sort-Object LastWriteTime | Select-Object -Last 1
if (-not $after) { $after = Get-ChildItem -LiteralPath $reports -Filter '*chat-profiled-tuning-speed.json' -File | Sort-Object LastWriteTime | Select-Object -Last 1 }
if (-not $after) { Fail 'Tuning completed without a persisted speed report' }
$report = Get-Content -Raw -LiteralPath $after.FullName | ConvertFrom-Json
$evidence.tuning = $report
$evidence.tuning_report_path = $after.FullName
$winner = JsonValue $report @('winner','selection')
$winnerConfig = if ($winner) { JsonValue $winner @('config','configuration','selected') } else { $null }
$evidence.launch_command = if ($winner) { JsonValue $winner @('launch_command','command','display') } else { $null }
if (-not $winnerConfig -and $report.baseline) { $winnerConfig = $report.baseline.tuning }
if ($winnerConfig) {
    if ([string](JsonValue $winnerConfig @('model_path')) -and [IO.Path]::GetFullPath([string]$winnerConfig.model_path) -ne [IO.Path]::GetFullPath($modelPath)) { Fail 'Selected configuration changed model path' }
    if ([string](JsonValue $winnerConfig @('weight_quantization','quantization')) -and [string](JsonValue $winnerConfig @('weight_quantization','quantization')) -ne $quant) { Fail 'Selected configuration changed weight quantization' }
}
$target = JsonValue $report @('target','target_status')
$accuracy = JsonValue $report @('accuracy','accuracy_summary')
$targetReached = [bool](JsonValue $target @('validated','reached','passed'))
$finalMeasurement = JsonValue $report @('final_measurement','validated_measurement')
$speed = [double](JsonValue $finalMeasurement @('tokens_per_second','tokens_per_second_estimate','decode_tokens_per_second'))
if ($speed -le 0 -and $winner) { $speed = [double](JsonValue (JsonValue $winner @('measurement','final_measurement')) @('tokens_per_second','tokens_per_second_estimate','decode_tokens_per_second')) }
$confidence = JsonValue $finalMeasurement @('confidence_interval','confidence')
$confidenceAvailable = [bool](JsonValue $confidence @('available'))
$confidenceLowerBound = [double](JsonValue $confidence @('lower_bound','lower'))
$evidence.validated_tokens_per_second = $speed
$evidence.confidence_lower_bound = $confidenceLowerBound
$evidence.confidence_interval = $confidence
$accuracyPassed = [bool](JsonValue $accuracy @('passed','valid','gate_passed'))
if ($null -eq $accuracy) { $accuracyPassed = $false }
if (-not $targetReached -or $speed -lt $TargetTokensPerSecond) { Fail "Validated throughput target not reached: ${speed} tok/s (target ${TargetTokensPerSecond})" }
if (-not $confidenceAvailable -or $confidenceLowerBound -lt $TargetTokensPerSecond) { Fail "Measured throughput lacks a 95% confidence lower bound at the target: ${confidenceLowerBound} tok/s (target ${TargetTokensPerSecond})" }
if (-not $accuracyPassed) { Fail 'Deterministic accuracy gate did not pass' }
$finalHealth = Invoke-Rift @('backend','health','llama.cpp','--base-url',$BaseUrl)
$evidence.health_final = $finalHealth
if (-not [bool](JsonValue $finalHealth @('healthy'))) { Fail 'Final llama.cpp health check failed' }
$evidence.passed = $true

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$evidencePath = Join-Path $reports "task-6-acceptance-$stamp.json"
$evidence | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $evidencePath -Encoding utf8
$evidence | ConvertTo-Json -Depth 8
Write-Host "Task 6 acceptance PASS; report: $evidencePath"
exit 0

trap {
    $evidencePath = Join-Path $reports ("task-6-acceptance-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    try { $evidence | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $evidencePath -Encoding utf8 } catch {}
    Write-Error $_
    exit 1
}
