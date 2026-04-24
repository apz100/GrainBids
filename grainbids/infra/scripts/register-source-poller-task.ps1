param(
  [string]$TaskName = "GrainBids-Source-Poller",
  [string]$StartTimes = "08:00,15:00",
  [string]$ScriptPath = "$PSScriptRoot\run-source-poller.ps1",
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [switch]$SkipPipInstall,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$resolvedScriptPath = (Resolve-Path $ScriptPath).Path
$resolvedApiDir = (Resolve-Path $ApiDir).Path

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedScriptPath`" -ApiDir `"$resolvedApiDir`""
if ($SkipPipInstall.IsPresent) {
  $argument += " -SkipPipInstall"
}

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
$description = "Runs GrainBids automated source polling."

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
Write-Output "API_DIR=$resolvedApiDir"
Write-Output "ACTION_EXECUTE=powershell.exe"
Write-Output "ACTION_ARGUMENTS=$argument"
Write-Output ""
Write-Output "To register the task:"
Write-Output "  .\register-source-poller-task.ps1 -Apply"
