$ErrorActionPreference = "Stop"

$Root = "D:\Coding\MU\Tri-Modal_ECG"
$ScriptsDir = Join-Path $Root "scripts"
$Python = Join-Path $Root "ecg_env\Scripts\python.exe"
$RunDir = Join-Path $Root "outputs\stage_reports\stage_7_run"
$RunnerLog = Join-Path $RunDir "stage_7_runner.log"

New-Item -ItemType Directory -Path $RunDir -Force | Out-Null

$env:STAGE7_MAX_WORKERS = "20"
$env:STAGE7_RAM_RESERVE_GB = "2"
$env:STAGE7_POOL_CHUNKSIZE = "16"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"
$env:PYTHONWARNINGS = "ignore"

function Write-RunnerLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') RUNNER pid=$PID  main | $Message"
    Add-Content -Path $RunnerLog -Value $line -Encoding UTF8
}

function Invoke-StageScript {
    param(
        [string]$Script,
        [string]$StdoutName,
        [string]$StderrName
    )
    $stdout = Join-Path $RunDir $StdoutName
    $stderr = Join-Path $RunDir $StderrName
    Write-RunnerLog "starting $Script with STAGE7_MAX_WORKERS=$env:STAGE7_MAX_WORKERS STAGE7_RAM_RESERVE_GB=$env:STAGE7_RAM_RESERVE_GB STAGE7_POOL_CHUNKSIZE=$env:STAGE7_POOL_CHUNKSIZE"
    $process = Start-Process -FilePath $Python -ArgumentList @($Script) -WorkingDirectory $ScriptsDir -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    try {
        $process.PriorityClass = "High"
    } catch {
        Write-RunnerLog "could not set high priority for ${Script}: $($_.Exception.Message)"
    }
    Write-RunnerLog "started $Script child_pid=$($process.Id)"
    $process.WaitForExit()
    Write-RunnerLog "finished $Script child_pid=$($process.Id) exit_code=$($process.ExitCode)"
    if ($process.ExitCode -ne 0) {
        throw "$Script failed with exit code $($process.ExitCode)"
    }
}

Write-RunnerLog "stage 7 all-lead SQI rerun begin"
Invoke-StageScript -Script "phase1_dataset_generation\31_waveform_qc.py" -StdoutName "31_waveform_qc.stdout.log" -StderrName "31_waveform_qc.stderr.log"
Invoke-StageScript -Script "phase1_dataset_generation\32_compute_structured_features.py" -StdoutName "32_compute_structured_features.stdout.log" -StderrName "32_compute_structured_features.stderr.log"
Write-RunnerLog "stage 7 all-lead SQI rerun complete"
