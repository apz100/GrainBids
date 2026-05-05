param(
  [Parameter(Mandatory=$true)]
  [string]$ApiBaseUrl,
  [string]$WebBaseUrl = "",
  [switch]$CheckWeb
)

$ErrorActionPreference = "Stop"

function Invoke-HealthCheck {
  param(
    [Parameter(Mandatory=$true)]
    [string]$Url,
    [int]$ExpectedStatus = 200
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing
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
Invoke-HealthCheck -Url "$api/health/live"
Invoke-HealthCheck -Url "$api/health/ready"
Invoke-HealthCheck -Url "$api/api/health/db"
Invoke-HealthCheck -Url "$api/api/ingestion/sla"
Invoke-HealthCheck -Url "$api/api/normalized-prices/summary"

if ($CheckWeb.IsPresent -and $WebBaseUrl.Trim() -ne "") {
  $web = $WebBaseUrl.TrimEnd("/")
  Invoke-HealthCheck -Url $web
}

Write-Output "SMOKE_TEST_COMPLETE=1"
