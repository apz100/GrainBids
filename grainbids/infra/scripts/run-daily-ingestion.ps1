param(
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [string]$LogDir = "",
  [switch]$SkipPipInstall,
  [string]$CommodityId = "",
  [int]$MaxAttempts = 0,
  [int]$StatementTimeoutMinutes = 45,
  [switch]$SingleSource
)

$ErrorActionPreference = "Stop"

function Write-RunLog {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Write-Output $line
  $line | Out-File -LiteralPath $script:LogPath -Append -Encoding utf8
}

try {
  $resolvedApiDir = (Resolve-Path $ApiDir).Path
  $repoRoot = (Resolve-Path (Join-Path $resolvedApiDir "..\..")).Path
  $resolvedLogDir = if ($LogDir -ne "") { $LogDir } else { Join-Path $repoRoot ".runlogs" }
  $resolvedLogDir = (New-Item -ItemType Directory -Force -Path $resolvedLogDir).FullName
  $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $script:LogPath = Join-Path $resolvedLogDir "daily-ingestion-$timestamp.log"

  Write-RunLog "Starting daily ingestion run"
  Write-RunLog "ApiDir=$resolvedApiDir"
  Write-RunLog "LogPath=$script:LogPath"

  Set-Location $resolvedApiDir
  if (!(Test-Path ".venv")) {
    Write-RunLog "Creating Python virtual environment"
    python -m venv .venv
  }

  $pythonExe = Join-Path $resolvedApiDir ".venv\Scripts\python.exe"
  if (!(Test-Path $pythonExe)) {
    throw "Virtual environment is incomplete. Delete apps/api/.venv and rerun."
  }

  if (-not $SkipPipInstall.IsPresent) {
    Write-RunLog "Installing/updating API dependencies"
    & $pythonExe -m pip install -r requirements.txt 2>&1 | ForEach-Object {
      $_ | Out-Host
      $_ | Out-File -LiteralPath $script:LogPath -Append -Encoding utf8
    }
    if ($LASTEXITCODE -ne 0) {
      throw "Dependency install failed with exit code $LASTEXITCODE"
    }
  } else {
    Write-RunLog "Skipping dependency install (-SkipPipInstall)"
  }

  $jobArgs = @("-m", "app.jobs.daily_source_ingestion")
  if ($CommodityId -ne "") {
    $jobArgs += "--commodity-id"
    $jobArgs += $CommodityId
  }
  if ($MaxAttempts -gt 0) {
    $jobArgs += "--max-attempts"
    $jobArgs += "$MaxAttempts"
  }
  if ($SingleSource.IsPresent) {
    $jobArgs += "--single-source"
  }
  if ($StatementTimeoutMinutes -gt 0) {
    $jobArgs += "--statement-timeout-minutes"
    $jobArgs += "$StatementTimeoutMinutes"
  }

  Write-RunLog "Running ingestion job ($($jobArgs -join ' '))"
  $jobOutput = @()
  & $pythonExe @jobArgs 2>&1 | ForEach-Object {
    $line = "$_"
    $jobOutput += $line
    $line | Out-Host
    $line | Out-File -LiteralPath $script:LogPath -Append -Encoding utf8
  }
  $jobExitCode = $LASTEXITCODE
  if ($jobExitCode -ne 0) {
    throw "Ingestion job failed with exit code $jobExitCode"
  }

  Write-RunLog "Daily ingestion completed successfully"
} catch {
  if ($script:LogPath) {
    Write-RunLog "Daily ingestion failed: $($_.Exception.Message)"
  }
  throw
}
