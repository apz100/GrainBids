param(
  [Parameter(Mandatory = $true)]
  [string]$ApiBaseUrl,
  [Parameter(Mandatory = $true)]
  [string]$OrgId,
  [string]$UserRole = "admin",
  [string]$ExpectedStartTimes = "08:00,15:00",
  [int]$GraceMinutes = 45,
  [int]$Limit = 25
)

$ErrorActionPreference = "Stop"

function Get-EasternNow {
  $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
  return [System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $tz)
}

function Parse-TimeList {
  param([string]$Value)

  $times = @()
  foreach ($token in ($Value -split ",")) {
    $trimmed = $token.Trim()
    if ($trimmed -eq "") { continue }
    try {
      $times += [DateTime]::ParseExact($trimmed, "HH:mm", $null).TimeOfDay
    } catch {
      throw "Each ExpectedStartTimes value must use HH:mm format. Invalid value: $trimmed"
    }
  }

  if ($times.Count -eq 0) {
    throw "ExpectedStartTimes cannot be empty."
  }

  return $times
}

function Format-Run {
  param($Run)

  return "id=$($Run.id) status=$($Run.status) started_at=$($Run.started_at) completed_at=$($Run.completed_at) parse_success_rate=$($Run.parse_success_rate)"
}

$api = $ApiBaseUrl.TrimEnd("/")
$headers = @{
  "X-Org-Id" = $OrgId.Trim()
  "X-User-Role" = $UserRole.Trim()
}

$runs = (Invoke-RestMethod -Method Get -Uri "$api/api/ingestion/runs?limit=$Limit" -Headers $headers).rows
if (-not $runs) {
  Write-Output "FAIL no ingestion runs returned for org=$OrgId"
  exit 1
}

$expectedTimes = Parse-TimeList -Value $ExpectedStartTimes
$now = Get-EasternNow
$window = [TimeSpan]::FromMinutes($GraceMinutes)
$failures = @()

Write-Output "CHECK_TIME=$($now.ToString('yyyy-MM-dd HH:mm:ss')) ET"
Write-Output "EXPECTED_START_TIMES=$ExpectedStartTimes"
Write-Output "GRACE_MINUTES=$GraceMinutes"
Write-Output "RUNS_FETCHED=$($runs.Count)"

foreach ($startTime in $expectedTimes) {
  $windowStart = $now.Date.Add($startTime)
  if ($now -lt $windowStart) {
    Write-Output "SKIP future_window start=$($windowStart.ToString('yyyy-MM-dd HH:mm:ss'))"
    continue
  }

  $windowEnd = $windowStart.Add($window)
  $windowRuns = @($runs | Where-Object {
    $_.started_at -and
    ([DateTimeOffset]$_.started_at).LocalDateTime -ge $windowStart -and
    ([DateTimeOffset]$_.started_at).LocalDateTime -le $windowEnd
  })

  if ($windowRuns.Count -gt 0) {
    $completed = @($windowRuns | Where-Object { $_.status -eq "completed" })
    if ($completed.Count -gt 0) {
      $best = $completed | Sort-Object started_at -Descending | Select-Object -First 1
      Write-Output "PASS window_start=$($windowStart.ToString('HH:mm')) run=$((Format-Run -Run $best))"
      continue
    }

    $running = @($windowRuns | Where-Object { $_.status -eq "running" })
    if ($running.Count -gt 0 -and $now -lt $windowEnd) {
      $bestRunning = $running | Sort-Object started_at -Descending | Select-Object -First 1
      Write-Output "PENDING window_start=$($windowStart.ToString('HH:mm')) run=$((Format-Run -Run $bestRunning))"
      continue
    }
  }

  $latestBeforeCutoff = @($runs | Where-Object {
    $_.started_at -and
    ([DateTimeOffset]$_.started_at).LocalDateTime -ge $windowStart -and
    ([DateTimeOffset]$_.started_at).LocalDateTime -le $windowEnd -and
    $_.status -eq "completed"
  } | Sort-Object started_at -Descending | Select-Object -First 1)

  if ($latestBeforeCutoff.Count -eq 0) {
    $failures += "missing completed run for window starting $($windowStart.ToString('HH:mm'))"
    Write-Output "FAIL window_start=$($windowStart.ToString('HH:mm')) missing completed run in $GraceMinutes minute window"
  }
}

if ($failures.Count -gt 0) {
  Write-Output "SUMMARY=failed"
  foreach ($failure in $failures) {
    Write-Output "REASON=$failure"
  }
  exit 1
}

Write-Output "SUMMARY=passed"
