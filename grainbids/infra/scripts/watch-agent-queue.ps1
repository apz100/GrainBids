param(
  [int]$PollIntervalSeconds = 10,
  [switch]$RunOnce,
  [string]$DefaultTestCommand = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$queuedFolder = Get-AgentStateFolder -State 'queued' -RepoRoot $repoRoot
$inProgressFolder = Get-AgentStateFolder -State 'in-progress' -RepoRoot $repoRoot
$reviewFolder = Get-AgentStateFolder -State 'review' -RepoRoot $repoRoot
$blockedFolder = Get-AgentStateFolder -State 'blocked' -RepoRoot $repoRoot

function Get-NextQueuedTask {
  param([string]$Folder)
  if (-not (Test-Path $Folder)) {
    return $null
  }
  return Get-ChildItem -Path $Folder -Filter *.md -File | Sort-Object Name | Select-Object -First 1
}

function Move-InProgressTask {
  param([string]$TaskPath)
  if (-not (Test-Path $TaskPath)) {
    throw "Task file not found: $TaskPath"
  }
  $updated = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $inProgressFolder -NewState 'in_progress'
  return $updated
}

function Invoke-TaskTestCommand {
  param(
    [Parameter(Mandatory = $true)][string]$Worktree,
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$CommandText
  )

  $pythonExe = Join-Path (Join-Path $RepoRoot 'grainbids\apps\api') '.venv\Scripts\python.exe'
  $normalizedCommand = $CommandText.Trim()
  if ($normalizedCommand -match '^(?i)pytest(\s|$)') {
    if (!(Test-Path $pythonExe)) {
      throw "Repo Python executable not found: $pythonExe"
    }
    $rest = $normalizedCommand.Substring(6).TrimStart()
    $normalizedCommand = "& `"$pythonExe`" -m pytest"
    if (-not [string]::IsNullOrWhiteSpace($rest)) {
      $normalizedCommand += " $rest"
    }
  } elseif ($normalizedCommand -match '^(?i)python\s+-m\s+pytest(\s|$)') {
    if (!(Test-Path $pythonExe)) {
      throw "Repo Python executable not found: $pythonExe"
    }
    $rest = [regex]::Replace($normalizedCommand, '^(?i)python\s+-m\s+pytest\s*', '').Trim()
    $normalizedCommand = "& `"$pythonExe`" -m pytest"
    if (-not [string]::IsNullOrWhiteSpace($rest)) {
      $normalizedCommand += " $rest"
    }
  }

  Push-Location $Worktree
  try {
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $normalizedCommand
    return $LASTEXITCODE
  }
  finally {
    Pop-Location
  }
}

function Start-And-Process-Task {
  param([Parameter(Mandatory = $true)][string]$QueuedTaskPath)

  $taskBeforeStart = Read-AgentTaskFile -Path $QueuedTaskPath
  $taskTitle = $taskBeforeStart.Metadata['task_title']
  if (-not $taskTitle) {
    $taskTitle = Split-Path -Path $QueuedTaskPath -LeafBase
  }

  $startScript = Join-Path $repoRoot 'grainbids\infra\scripts\start-agent-task.ps1'
  & $startScript -TaskPath $QueuedTaskPath

  $inProgressTaskPath = Join-Path $inProgressFolder (Split-Path -Leaf $QueuedTaskPath)
  if (-not (Test-Path $inProgressTaskPath)) {
    throw "Task was not moved to in-progress as expected: $inProgressTaskPath"
  }

  $task = Read-AgentTaskFile -Path $inProgressTaskPath
  $worktree = $task.Metadata['worktree']
  if (-not $worktree -or -not (Test-Path $worktree)) {
    throw "Task worktree is missing or not recorded for '$taskTitle'."
  }

  $testCommand = $task.Metadata['test_command']
  if ([string]::IsNullOrWhiteSpace($testCommand)) {
    $testCommand = $DefaultTestCommand
  }

  if ([string]::IsNullOrWhiteSpace($testCommand)) {
    Write-Host "No test_command set for '$taskTitle'; moving to blocked."
    $blockedPath = Move-AgentTaskFile -SourcePath $inProgressTaskPath -TargetFolder $blockedFolder -NewState 'blocked'
    Write-Host "Blocked task:"
    Write-Host "  $blockedPath"
    return
  }

  Write-Host "Running tests for '$taskTitle':"
  Write-Host "  $testCommand"
  $exitCode = Invoke-TaskTestCommand -Worktree $worktree -RepoRoot $repoRoot -CommandText $testCommand
  if ($exitCode -ne 0) {
    Write-Host "Tests failed for '$taskTitle' (exit code $exitCode); moving to blocked."
    $blockedPath = Move-AgentTaskFile -SourcePath $inProgressTaskPath -TargetFolder $blockedFolder -NewState 'blocked'
    Write-Host "Blocked task:"
    Write-Host "  $blockedPath"
    return
  }

  $reviewPath = Move-AgentTaskFile -SourcePath $inProgressTaskPath -TargetFolder $reviewFolder -NewState 'review'
  Write-Host "Task ready for review:"
  Write-Host "  $reviewPath"
}

do {
  $nextTask = Get-NextQueuedTask -Folder $queuedFolder
  if (-not $nextTask) {
    Write-Host "No queued tasks found."
    if (-not $RunOnce) {
      Start-Sleep -Seconds ([Math]::Max(1, $PollIntervalSeconds))
    }
    continue
  }

  Start-And-Process-Task -QueuedTaskPath $nextTask.FullName
}
while (-not $RunOnce)
