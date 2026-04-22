param(
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api"
)

$ErrorActionPreference = "Stop"

Set-Location $ApiDir
if (!(Test-Path ".venv")) {
  python -m venv .venv
}

$pythonExe = Join-Path $ApiDir ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
  throw "Virtual environment is incomplete. Delete apps/api/.venv and rerun."
}

& $pythonExe -m pip install -r requirements.txt | Out-Host
& $pythonExe -m app.jobs.daily_source_ingestion
