param(
  [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..\\..\\apps\\web")
try {
  if (!(Test-Path "node_modules")) {
    npm install | Out-Host
  }
  if (!(Test-Path ".env.local") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env.local"
  }
  $env:PORT = "$Port"
  npm run dev
} finally {
  Pop-Location
}
