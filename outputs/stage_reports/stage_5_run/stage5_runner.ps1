Set-Location 'D:\Coding\MU\Tri-Modal_ECG'
$ErrorActionPreference = 'Continue'
$runDir = 'outputs\stage_reports\stage_5_run'
function Write-Heartbeat([string]$status, [string]$step, [int]$exitCode) {
  $payload = [ordered]@{
    stage = 5
    status = $status
    step = $step
    exit_code = $exitCode
    updated_at_utc = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
  } | ConvertTo-Json
  Set-Content -Path (Join-Path $runDir 'stage5_heartbeat.json') -Value $payload -Encoding UTF8
}
Write-Heartbeat 'running' '21_generate_scanlike_images' 0
& .\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\21_generate_scanlike_images.py 1> (Join-Path $runDir '21_stdout.log') 2> (Join-Path $runDir '21_stderr.log')
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Heartbeat 'failed' '21_generate_scanlike_images' $code
  exit $code
}
Write-Heartbeat 'running' '21b_pack_scanlike' 0
& .\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\21b_pack_scanlike.py 1> (Join-Path $runDir '21b_stdout.log') 2> (Join-Path $runDir '21b_stderr.log')
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Heartbeat 'failed' '21b_pack_scanlike' $code
  exit $code
}
Write-Heartbeat 'complete' 'stage_5' 0
