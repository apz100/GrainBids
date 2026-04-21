param(
  [switch]$Loop,
  [int]$SleepSeconds = 60
)

$ErrorActionPreference = "Stop"

$apiRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\apps\api")).Path
if ($apiRoot.StartsWith("\\")) {
  throw "UNC paths are not supported for runtime on this machine. Run from a drive-letter path."
}

Push-Location $apiRoot
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }
  $pythonExe = Join-Path $apiRoot ".venv\Scripts\python.exe"
  & $pythonExe -m pip install -r requirements.txt | Out-Host
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
