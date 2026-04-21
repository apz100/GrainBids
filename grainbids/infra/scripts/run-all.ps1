param(
  [string]$HostAddr = "127.0.0.1",
  [int]$ApiPort = 8000,
  [int]$WebPort = 3000,
  [int]$WaitSeconds = 12,
  [switch]$Restart,
  [switch]$NoHealthCheck
)

$ErrorActionPreference = "Stop"

$scriptsRoot = (Resolve-Path $PSScriptRoot).Path
if ($scriptsRoot.StartsWith("\\")) {
  throw "UNC paths are not supported for runtime start scripts on this machine. Run from a drive-letter path (for example P:\...)."
}

$repoRoot = (Resolve-Path (Join-Path $scriptsRoot "..\..\")).Path
$apiScript = Join-Path $scriptsRoot "run-api.ps1"
$webScript = Join-Path $scriptsRoot "run-web.ps1"

if (!(Test-Path $apiScript)) { throw "Missing script: $apiScript" }
if (!(Test-Path $webScript)) { throw "Missing script: $webScript" }

if ($Restart.IsPresent) {
  foreach ($port in @($ApiPort, $WebPort)) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
      try {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
      } catch {
        Write-Warning "Failed to stop PID $($listener.OwningProcess) on port $port: $($_.Exception.Message)"
      }
    }
  }
}

$runLogs = Join-Path $repoRoot ".runlogs"
New-Item -ItemType Directory -Force -Path $runLogs | Out-Null

$apiOut = Join-Path $runLogs "api.log"
$apiErr = Join-Path $runLogs "api.err.log"
$webOut = Join-Path $runLogs "web.log"
$webErr = Join-Path $runLogs "web.err.log"

$apiProc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
  "-ExecutionPolicy", "Bypass",
  "-File", $apiScript,
  "-HostAddr", $HostAddr,
  "-Port", "$ApiPort"
) -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru

$webProc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
  "-ExecutionPolicy", "Bypass",
  "-File", $webScript,
  "-Port", "$WebPort"
) -RedirectStandardOutput $webOut -RedirectStandardError $webErr -PassThru

Write-Output "API_PID=$($apiProc.Id)"
Write-Output "WEB_PID=$($webProc.Id)"
Write-Output "API_LOG=$apiOut"
Write-Output "WEB_LOG=$webOut"

Start-Sleep -Seconds $WaitSeconds

if (-not $NoHealthCheck.IsPresent) {
  $apiUrl = "http://$HostAddr`:$ApiPort/health"
  $webUrl = "http://127.0.0.1:$WebPort"

  try {
    $apiResp = Invoke-WebRequest -Uri $apiUrl -UseBasicParsing -TimeoutSec 10
    Write-Output "API_STATUS=$($apiResp.StatusCode)"
  } catch {
    Write-Output "API_STATUS=DOWN"
  }

  try {
    $webResp = Invoke-WebRequest -Uri $webUrl -UseBasicParsing -TimeoutSec 10
    Write-Output "WEB_STATUS=$($webResp.StatusCode)"
  } catch {
    Write-Output "WEB_STATUS=DOWN"
  }
}
