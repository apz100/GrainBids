param(
  [Parameter(Mandatory=$true)]
  [string]$ApiBaseUrl,
  [string]$WebBaseUrl = "",
  [switch]$CheckWeb,
  [string]$OrgId = "",
  [string]$UserRole = "admin",
  [string]$UserEmail = ""
)

$ErrorActionPreference = "Stop"

function Invoke-HealthCheck {
  param(
    [Parameter(Mandatory=$true)]
    [string]$Url,
    [int]$ExpectedStatus = 200,
    [hashtable]$Headers = @{}
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing -Headers $Headers
    if ($response.StatusCode -ne $ExpectedStatus) {
      throw "Expected $ExpectedStatus, got $($response.StatusCode)"
    }
    Write-Output "PASS $Url ($($response.StatusCode))"
  } catch {
    Write-Output "FAIL $Url ($($_.Exception.Message))"
    throw
  }
}

$api = $ApiBaseUrl.TrimEnd("/")

$scopedHeaders = @{}
if ($OrgId.Trim() -ne "") {
  $scopedHeaders["X-Org-Id"] = $OrgId.Trim()
}
if ($UserRole.Trim() -ne "") {
  $scopedHeaders["X-User-Role"] = $UserRole.Trim()
}
if ($UserEmail.Trim() -ne "") {
  $scopedHeaders["X-User-Email"] = $UserEmail.Trim()
}

Invoke-HealthCheck -Url "$api/health/live"
Invoke-HealthCheck -Url "$api/health/ready"
Invoke-HealthCheck -Url "$api/api/health/db"

if ($scopedHeaders.ContainsKey("X-Org-Id")) {
  Invoke-HealthCheck -Url "$api/api/ingestion/sla" -Headers $scopedHeaders
  Invoke-HealthCheck -Url "$api/api/normalized-prices/summary" -Headers $scopedHeaders
  Invoke-HealthCheck -Url "$api/api/normalized-prices/facets" -Headers $scopedHeaders
  Invoke-HealthCheck -Url "$api/api/normalized-prices/preview?limit=10" -Headers $scopedHeaders
} else {
  Write-Output "SKIP org-scoped endpoints (missing -OrgId)"
}

if ($CheckWeb.IsPresent -and $WebBaseUrl.Trim() -ne "") {
  $web = $WebBaseUrl.TrimEnd("/")
  Invoke-HealthCheck -Url $web
}

Write-Output "SMOKE_TEST_COMPLETE=1"
