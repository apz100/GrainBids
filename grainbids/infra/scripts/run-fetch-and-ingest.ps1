param(
  [ValidateSet("dynamic", "playwright", "grainbidder")]
  [string]$Fetcher = "dynamic",
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [string]$SourceFilePath = "",
  [string]$CommodityId = "",
  [int]$MaxAttempts = 0,
  [switch]$SkipPipInstall
)

$ErrorActionPreference = "Stop"

function Resolve-FetchScriptPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ApiRoot,
    [Parameter(Mandatory = $true)]
    [string]$Profile
  )

  $sourcesRoot = Join-Path $ApiRoot "app\platform\market_data\sources"
  switch ($Profile) {
    "dynamic" {
      return Join-Path $sourcesRoot "cash_bids_dynamic.py"
    }
    "playwright" {
      return Join-Path $sourcesRoot "cash_bids_via_playwright.py"
    }
    "grainbidder" {
      return Join-Path $sourcesRoot "orchestrator\GrainBidder.py"
    }
    default {
      throw "Unsupported fetcher profile: $Profile"
    }
  }
}

function Resolve-LatestOutputPath {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$LogLines,
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [Parameter(Mandatory = $true)]
    [string]$ApiRoot
  )

  for ($i = $LogLines.Count - 1; $i -ge 0; $i--) {
    $line = [string]$LogLines[$i]
    $match = [regex]::Match($line, "Updated latest(?: CSV at| Excel workbook at| file at)\s+(.+)$")
    if ($match.Success) {
      return $match.Groups[1].Value.Trim()
    }
  }

  $sourcesRoot = Join-Path $ApiRoot "app\platform\market_data\sources"
  switch ($Profile) {
    "dynamic" {
      return Join-Path $sourcesRoot "OntarioBids\Ontario_CashBids_latest.csv"
    }
    "playwright" {
      return Join-Path $sourcesRoot "output\EasternOntario_CashBids_latest.csv"
    }
    "grainbidder" {
      return Join-Path $sourcesRoot "Ontario_CashBids_latest.xlsx"
    }
    default {
      throw "Unsupported fetcher profile: $Profile"
    }
  }
}

$apiRoot = (Resolve-Path $ApiDir).Path
Push-Location $apiRoot
try {
  if (!(Test-Path ".venv")) {
    python -m venv .venv
  }

  $pythonExe = Join-Path $apiRoot ".venv\Scripts\python.exe"
  if (!(Test-Path $pythonExe)) {
    throw "Virtual environment is incomplete. Delete apps/api/.venv and rerun."
  }

  if (-not $SkipPipInstall.IsPresent) {
    & $pythonExe -m pip install -r requirements.txt | Out-Host
  }

  $fetchScript = Resolve-FetchScriptPath -ApiRoot $apiRoot -Profile $Fetcher
  if (!(Test-Path $fetchScript)) {
    throw "Fetcher script not found: $fetchScript"
  }

  Write-Output "Running fetcher profile '$Fetcher' from $fetchScript"
  $fetchOutput = & $pythonExe $fetchScript 2>&1
  $fetchOutput | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "Fetcher failed with exit code $LASTEXITCODE"
  }

  $resolvedSourcePath = if ($SourceFilePath) {
    $SourceFilePath
  } else {
    Resolve-LatestOutputPath -LogLines $fetchOutput -Profile $Fetcher -ApiRoot $apiRoot
  }

  if (!(Test-Path $resolvedSourcePath)) {
    throw "Resolved latest source file does not exist: $resolvedSourcePath"
  }

  $env:DAILY_SOURCE_FILE_PATH = $resolvedSourcePath
  Write-Output "Using DAILY_SOURCE_FILE_PATH=$resolvedSourcePath"

  $dailyScript = Join-Path (Resolve-Path (Join-Path $apiRoot "..\..")).Path "infra\scripts\run-daily-ingestion.ps1"
  if (!(Test-Path $dailyScript)) {
    throw "Ingestion runner script not found: $dailyScript"
  }

  $dailyArgs = @{
    ApiDir = $apiRoot
    SingleSource = $true
    SkipPipInstall = $true
  }
  if ($CommodityId -ne "") {
    $dailyArgs["CommodityId"] = $CommodityId
  }
  if ($MaxAttempts -gt 0) {
    $dailyArgs["MaxAttempts"] = $MaxAttempts
  }

  & $dailyScript @dailyArgs
} finally {
  Pop-Location
}
