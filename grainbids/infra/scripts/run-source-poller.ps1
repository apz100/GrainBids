param(
  [switch]$Loop,
  [int]$SleepSeconds = 60,
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [switch]$SkipPipInstall
)

$ErrorActionPreference = "Stop"

$apiRoot = (Resolve-Path $ApiDir).Path

Push-Location $apiRoot
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }
  $pythonExe = Join-Path $apiRoot ".venv\Scripts\python.exe"
  if (-not $SkipPipInstall.IsPresent) {
    & $pythonExe -m pip install -r requirements.txt | Out-Host
  }
  $args = @("-m", "app.jobs.poll_sources")
  if ($Loop.IsPresent) {
    $args += "--loop"
    $args += "--sleep-seconds"
    $args += "$SleepSeconds"
  }
  & $pythonExe @args
} finally {
  Pop-Location
}
