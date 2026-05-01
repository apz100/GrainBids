param(
  [string]$HostAddr = "127.0.0.1",
  [int]$Port = 8000,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$apiRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\apps\api")).Path
if ($apiRoot.StartsWith("\\")) {
  throw "UNC paths are not supported for API runtime on this machine. Run from a drive-letter path (for example P:\...)."
}

Push-Location $apiRoot
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }
  $pythonExe = Join-Path $apiRoot ".venv\Scripts\python.exe"
  if (!(Test-Path $pythonExe)) {
    throw "Virtual environment is incomplete. Delete apps/api/.venv and rerun."
  }
  & $pythonExe -m pip install -r requirements.txt | Out-Host
  if ([string]::IsNullOrWhiteSpace($env:APP_ENV)) {
    $env:APP_ENV = "development"
  }
  if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
  }

  $args = @("-m", "uvicorn", "app.main:app", "--host", $HostAddr, "--port", "$Port")
  if ($Reload.IsPresent) {
    $args += "--reload"
  }
  & $pythonExe @args
} finally {
  Pop-Location
}
