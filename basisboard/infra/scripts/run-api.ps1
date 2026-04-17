param(
  [string]$HostAddr = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..\\..\\apps\\api")
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt | Out-Host
  $env:APP_ENV = "development"
  if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
  }
  uvicorn app.main:app --host $HostAddr --port $Port --reload
} finally {
  Pop-Location
}
