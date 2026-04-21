param(
  [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

$webRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\apps\web")).Path
if ($webRoot.StartsWith("\\")) {
  throw "UNC paths are not supported for Next.js runtime. Run from a drive-letter path (for example P:\...)."
}

Push-Location $webRoot
try {
  $npmCmd = "C:\Program Files\nodejs\npm.cmd"
  if (!(Test-Path $npmCmd)) {
    $npmCmd = "npm"
  }

  $needsInstall = (!(Test-Path "node_modules")) -or (!(Test-Path "node_modules\.bin\next.cmd"))
  if ($needsInstall) {
    # Avoid workspace symlink creation issues on some Windows/network setups.
    & $npmCmd install --workspaces=false | Out-Host
  }
  if (!(Test-Path ".env.local") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env.local"
  }
  $env:PORT = "$Port"
  & $npmCmd run dev
} finally {
  Pop-Location
}
