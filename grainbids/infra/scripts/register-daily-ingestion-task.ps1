param(
  [string]$TaskName = "GrainBids-Daily-Ingestion",
  [string]$StartTime = "06:00",
  [string]$ScriptPath = "$PSScriptRoot\run-daily-ingestion.ps1",
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api",
  [string]$LogDir = "",
  [switch]$SkipPipInstall,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$resolvedScriptPath = (Resolve-Path $ScriptPath).Path
$resolvedApiDir = (Resolve-Path $ApiDir).Path

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedScriptPath`" -ApiDir `"$resolvedApiDir`""
if ($LogDir -ne "") {
  $argument += " -LogDir `"$LogDir`""
}
if ($SkipPipInstall.IsPresent) {
  $argument += " -SkipPipInstall"
}

try {
  $at = [DateTime]::ParseExact($StartTime, "HH:mm", $null)
} catch {
  throw "StartTime must use 24h format HH:mm (example: 06:00)."
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -Daily -At $at
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$description = "Runs GrainBids daily ingestion pipeline."

if ($Apply.IsPresent) {
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $description -Force | Out-Null
  Write-Output "REGISTERED_TASK=$TaskName"
  Write-Output "START_TIME=$StartTime"
  Write-Output "SCRIPT=$resolvedScriptPath"
  exit 0
}

Write-Output "DRY_RUN=1"
Write-Output "TASK_NAME=$TaskName"
Write-Output "START_TIME=$StartTime"
Write-Output "SCRIPT=$resolvedScriptPath"
Write-Output "API_DIR=$resolvedApiDir"
Write-Output "ACTION_EXECUTE=powershell.exe"
Write-Output "ACTION_ARGUMENTS=$argument"
Write-Output ""
Write-Output "To register the task:"
Write-Output "  .\register-daily-ingestion-task.ps1 -Apply"
