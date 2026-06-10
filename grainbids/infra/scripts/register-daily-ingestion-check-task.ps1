param(
  [string]$TaskName = "GrainBids-Daily-Ingestion-Check",
  [string]$StartTimes = "08:50,15:50",
  [string]$ScriptPath = "$PSScriptRoot\check-daily-ingestion.ps1",
  [string]$ApiBaseUrl = "https://api.grainbids.com",
  [string]$OrgId = $env:NEXT_PUBLIC_ORG_ID,
  [string]$UserRole = "admin",
  [string]$ExpectedStartTimes = "08:00,15:00",
  [int]$GraceMinutes = 45,
  [int]$Limit = 25,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$resolvedScriptPath = (Resolve-Path $ScriptPath).Path

if ([string]::IsNullOrWhiteSpace($OrgId)) {
  throw "OrgId is required."
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedScriptPath`" -ApiBaseUrl `"$ApiBaseUrl`" -OrgId `"$OrgId`" -UserRole `"$UserRole`" -ExpectedStartTimes `"$ExpectedStartTimes`" -GraceMinutes $GraceMinutes -Limit $Limit"

if ([string]::IsNullOrWhiteSpace($StartTimes)) {
  throw "StartTimes cannot be empty."
}

$triggerList = @()
foreach ($token in ($StartTimes -split ",")) {
  $trimmed = $token.Trim()
  if ($trimmed -eq "") { continue }
  try {
    $at = [DateTime]::ParseExact($trimmed, "HH:mm", $null)
  } catch {
    throw "Each StartTimes value must use HH:mm format. Invalid value: $trimmed"
  }
  $triggerList += (New-ScheduledTaskTrigger -Daily -At $at)
}
if ($triggerList.Count -eq 0) {
  throw "No valid StartTimes values provided."
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$description = "Checks whether GrainBids daily ingestion completed in the expected window."

if ($Apply.IsPresent) {
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggerList -Settings $settings -Description $description -Force | Out-Null
  Write-Output "REGISTERED_TASK=$TaskName"
  Write-Output "START_TIMES=$StartTimes"
  Write-Output "SCRIPT=$resolvedScriptPath"
  exit 0
}

Write-Output "DRY_RUN=1"
Write-Output "TASK_NAME=$TaskName"
Write-Output "START_TIMES=$StartTimes"
Write-Output "SCRIPT=$resolvedScriptPath"
Write-Output "API_BASE_URL=$ApiBaseUrl"
Write-Output "ORG_ID=$OrgId"
Write-Output "ACTION_EXECUTE=powershell.exe"
Write-Output "ACTION_ARGUMENTS=$argument"
Write-Output ""
Write-Output "To register the task:"
Write-Output "  .\register-daily-ingestion-check-task.ps1 -Apply"
