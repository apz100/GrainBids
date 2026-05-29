param(
  [ValidateSet("dynamic", "playwright", "grainbidder")]
  [string]$Fetcher = "dynamic",
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [string]$SourceFilePath = "",
  [string]$CommodityId = "",
  [int]$MaxAttempts = 0,
  [int]$StatementTimeoutMinutes = 45,
  [switch]$SkipPipInstall,
  [switch]$UploadToSupabase,
  [string]$SupabaseUrl = $env:SUPABASE_URL,
  [string]$SupabaseServiceRoleKey = $env:SUPABASE_SERVICE_ROLE_KEY,
  [string]$SupabaseBucket = "ingestion",
  [string]$SupabasePrefix = "ontario",
  [switch]$TriggerCloudIngestion,
  [string]$CloudApiBaseUrl = $env:GRAINBIDS_API_URL,
  [string]$CloudOrgId = $env:NEXT_PUBLIC_ORG_ID,
  [string]$CloudUserRole = "admin"
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

function Join-ObjectKey {
  param(
    [string]$Prefix,
    [string]$FileName
  )
  if ([string]::IsNullOrWhiteSpace($Prefix)) {
    return $FileName
  }
  return ($Prefix.TrimEnd("/") + "/" + $FileName)
}

function Get-ObjectUrlPath {
  param(
    [string]$ObjectKey
  )
  $segments = $ObjectKey -split "/"
  $encoded = $segments | ForEach-Object { [System.Uri]::EscapeDataString($_) }
  return ($encoded -join "/")
}

function Upload-ToSupabaseStorage {
  param(
    [Parameter(Mandatory = $true)]
    [string]$LocalPath,
    [Parameter(Mandatory = $true)]
    [string]$ObjectKey,
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [Parameter(Mandatory = $true)]
    [string]$ServiceRoleKey,
    [Parameter(Mandatory = $true)]
    [string]$Bucket
  )

  if (!(Test-Path $LocalPath)) {
    throw "File not found for upload: $LocalPath"
  }

  $objectUrlPath = Get-ObjectUrlPath -ObjectKey $ObjectKey
  $uploadUrl = "$($BaseUrl.TrimEnd('/'))/storage/v1/object/$Bucket/$objectUrlPath"
  $publicUrl = "$($BaseUrl.TrimEnd('/'))/storage/v1/object/public/$Bucket/$objectUrlPath"
  $bytes = [System.IO.File]::ReadAllBytes($LocalPath)
  $headers = @{
    "apikey"        = $ServiceRoleKey
    "Authorization" = "Bearer $ServiceRoleKey"
    "x-upsert"      = "true"
  }
  Invoke-RestMethod -Method Post -Uri $uploadUrl -Headers $headers -ContentType "application/octet-stream" -Body $bytes | Out-Null
  return $publicUrl
}

function Invoke-CloudIngestionRun {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl,
    [Parameter(Mandatory = $true)]
    [string]$OrgId,
    [string]$UserRole = "admin"
  )
  $headers = @{
    "X-Org-Id" = $OrgId
    "X-User-Role" = $UserRole
  }
  $uri = "$($ApiBaseUrl.TrimEnd('/'))/api/ingestion/source-files/run"
  return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers
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
  # Run via cmd to avoid PowerShell treating Python stderr warnings as terminating errors.
  $fetchOutput = & cmd /c "`"$pythonExe`" `"$fetchScript`" 2>&1"
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

  if ($UploadToSupabase.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($SupabaseUrl)) {
      throw "SUPABASE_URL is required when -UploadToSupabase is set."
    }
    if ([string]::IsNullOrWhiteSpace($SupabaseServiceRoleKey)) {
      throw "SUPABASE_SERVICE_ROLE_KEY is required when -UploadToSupabase is set."
    }

    $resolvedItem = Get-Item -LiteralPath $resolvedSourcePath
    $baseDir = $resolvedItem.DirectoryName
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedItem.Name)
    if ($baseName.EndsWith("_latest")) {
      $rootName = $baseName.Substring(0, $baseName.Length - "_latest".Length)
    } else {
      $rootName = $baseName
    }
    $csvPath = Join-Path $baseDir "$rootName`_latest.csv"
    $xlsxPath = Join-Path $baseDir "$rootName`_latest.xlsx"
    $uploadTargets = @()
    if (Test-Path $csvPath) { $uploadTargets += $csvPath }
    if (Test-Path $xlsxPath) { $uploadTargets += $xlsxPath }
    if ($uploadTargets.Count -eq 0) {
      $uploadTargets += $resolvedSourcePath
    }

    Write-Output "Uploading latest source files to Supabase bucket '$SupabaseBucket'..."
    foreach ($target in $uploadTargets) {
      $fileName = [System.IO.Path]::GetFileName($target)
      $objectKey = Join-ObjectKey -Prefix $SupabasePrefix -FileName $fileName
      $publicUrl = Upload-ToSupabaseStorage `
        -LocalPath $target `
        -ObjectKey $objectKey `
        -BaseUrl $SupabaseUrl `
        -ServiceRoleKey $SupabaseServiceRoleKey `
        -Bucket $SupabaseBucket
      Write-Output "UPLOADED_FILE=$target"
      Write-Output "PUBLIC_URL=$publicUrl"
    }
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
  if ($StatementTimeoutMinutes -gt 0) {
    $dailyArgs["StatementTimeoutMinutes"] = $StatementTimeoutMinutes
  }

  & $dailyScript @dailyArgs

  if ($TriggerCloudIngestion.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($CloudApiBaseUrl)) {
      throw "GRAINBIDS_API_URL is required when -TriggerCloudIngestion is set."
    }
    if ([string]::IsNullOrWhiteSpace($CloudOrgId)) {
      throw "NEXT_PUBLIC_ORG_ID is required when -TriggerCloudIngestion is set."
    }
    Write-Output "Triggering cloud ingestion cycle on $CloudApiBaseUrl ..."
    $cloudResult = Invoke-CloudIngestionRun -ApiBaseUrl $CloudApiBaseUrl -OrgId $CloudOrgId -UserRole $CloudUserRole
    $summary = $cloudResult.summary
    if ($summary) {
      Write-Output "CLOUD_TOTAL_SOURCES=$($summary.total_sources)"
      Write-Output "CLOUD_COMPLETED_SOURCES=$($summary.completed_sources)"
      Write-Output "CLOUD_FAILED_SOURCES=$($summary.failed_sources)"
    } else {
      Write-Output "CLOUD_RESULT=completed"
    }
  }
} finally {
  Pop-Location
}
