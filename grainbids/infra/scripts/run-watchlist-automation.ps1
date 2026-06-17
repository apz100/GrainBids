param(
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [string]$LogDir = "",
  [switch]$SkipPipInstall,
  [int]$Limit = 50
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
  $script:LogPath = Join-Path $resolvedLogDir "watchlist-automation-$timestamp.log"

  Write-RunLog "Starting watchlist automation digest run"
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

  $jobArgs = @("-m", "app.jobs.watchlist_automation_digest", "--limit", "$Limit")
  Write-RunLog "Running automation job ($($jobArgs -join ' '))"
  & $pythonExe @jobArgs 2>&1 | ForEach-Object {
    $line = "$_"
    $line | Out-Host
    $line | Out-File -LiteralPath $script:LogPath -Append -Encoding utf8
  }
  $jobExitCode = $LASTEXITCODE
  if ($jobExitCode -ne 0) {
    throw "Watchlist automation job failed with exit code $jobExitCode"
  }

  Write-RunLog "Watchlist automation digest completed successfully"
} catch {
  if ($script:LogPath) {
    Write-RunLog "Watchlist automation digest failed: $($_.Exception.Message)"
  }
  throw
}
