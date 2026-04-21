param(
  [string]$DatabaseUrl = "",
  [string]$Revision = "head"
)

$ErrorActionPreference = "Stop"

$apiRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\apps\api")).Path
Push-Location $apiRoot
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }
  $pythonExe = Join-Path ((Resolve-Path ".venv").Path) "Scripts\python.exe"
  if (!(Test-Path $pythonExe)) {
    throw "Virtual environment is incomplete. Delete apps/api/.venv and rerun this script."
  }
  & $pythonExe -m pip install -r requirements.txt | Out-Host

  if (Test-Path ".env") {
    # alembic env.py will load settings from .env via pydantic-settings
  } elseif (Test-Path ".env.example") {
    Write-Host "No apps/api/.env found. You can copy .env.example to .env and set DATABASE_URL."
  }

  if ($DatabaseUrl -ne "") {
    $env:DATABASE_URL = $DatabaseUrl
  }

  if ($env:DATABASE_URL -eq "" -and !(Test-Path ".env")) {
    throw "DATABASE_URL not provided. Pass -DatabaseUrl or create apps/api/.env with DATABASE_URL."
  }

  & $pythonExe -m alembic -c alembic.ini upgrade $Revision
} finally {
  Pop-Location
}
