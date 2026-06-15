param(
  [int]$PollIntervalSeconds = 10,
  [switch]$RunOnce,
  [string]$DefaultTestCommand = '',
  [int]$AutoApproveReview = 1,
  [int]$AutoApplyApproved = 1
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$queuedFolder = Get-AgentStateFolder -State 'queued' -RepoRoot $repoRoot
$inProgressFolder = Get-AgentStateFolder -State 'in-progress' -RepoRoot $repoRoot
$reviewFolder = Get-AgentStateFolder -State 'review' -RepoRoot $repoRoot
$approvedFolder = Get-AgentStateFolder -State 'approved' -RepoRoot $repoRoot
$blockedFolder = Get-AgentStateFolder -State 'blocked' -RepoRoot $repoRoot

function Get-NextAgentTaskFile {
  param([Parameter(Mandatory = $true)][string]$Folder)
  if (-not (Test-Path $Folder)) {
    return $null
  }
  return Get-ChildItem -Path $Folder -Filter *.md -File |
    Where-Object { $_.Name -ne '.gitkeep' } |
    Sort-Object Name |
    Select-Object -First 1
}

function Get-TaskTitle {
  param([Parameter(Mandatory = $true)][string]$TaskPath)
  $task = Read-AgentTaskFile -Path $TaskPath
  $title = $task.Metadata['task_title']
  if ([string]::IsNullOrWhiteSpace($title)) {
    return (Split-Path $TaskPath -LeafBase)
  }
  return $title
}

function Resolve-TaskTestCommand {
  param([Parameter(Mandatory = $true)][string]$TaskPath)
  $task = Read-AgentTaskFile -Path $TaskPath
  $testCommand = $task.Metadata['test_command']
  if ([string]::IsNullOrWhiteSpace($testCommand)) {
    $testCommand = $DefaultTestCommand
  }
  return $testCommand
}

function Move-ToBlocked {
  param(
    [Parameter(Mandatory = $true)][string]$TaskPath,
    [string]$Reason = ''
  )
  if (-not [string]::IsNullOrWhiteSpace($Reason)) {
    Write-Host $Reason
  }
  $blockedPath = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $blockedFolder -NewState 'blocked'
  Write-Host "Blocked task:"
  Write-Host "  $blockedPath"
}

function Process-QueuedTask {
  param([Parameter(Mandatory = $true)][System.IO.FileInfo]$TaskFile)

  $taskTitle = Get-TaskTitle -TaskPath $TaskFile.FullName
  $startScript = Join-Path $repoRoot 'grainbids\infra\scripts\start-agent-task.ps1'
  & $startScript -TaskPath $TaskFile.FullName

  $inProgressTaskPath = Join-Path $inProgressFolder $TaskFile.Name
  if (-not (Test-Path $inProgressTaskPath)) {
    throw "Task was not moved to in-progress as expected: $inProgressTaskPath"
  }

  $task = Read-AgentTaskFile -Path $inProgressTaskPath
  $worktree = $task.Metadata['worktree']
  if ([string]::IsNullOrWhiteSpace($worktree) -or -not (Test-Path $worktree)) {
    Move-ToBlocked -TaskPath $inProgressTaskPath -Reason "Task worktree missing for '$taskTitle'."
    return $true
  }

  $testCommand = Resolve-TaskTestCommand -TaskPath $inProgressTaskPath
  if ([string]::IsNullOrWhiteSpace($testCommand)) {
    Move-ToBlocked -TaskPath $inProgressTaskPath -Reason "No test_command set for '$taskTitle'."
    return $true
  }

  Write-Host "Running tests for '$taskTitle':"
  Write-Host "  $(Normalize-AgentCommand -CommandText $testCommand -RepoRoot $repoRoot)"
  $exitCode = Invoke-AgentCommand -WorkingDirectory $worktree -CommandText $testCommand -RepoRoot $repoRoot
  if ($exitCode -ne 0) {
    Move-ToBlocked -TaskPath $inProgressTaskPath -Reason "Tests failed for '$taskTitle' (exit code $exitCode)."
    return $true
  }

  $reviewPath = Move-AgentTaskFile -SourcePath $inProgressTaskPath -TargetFolder $reviewFolder -NewState 'review'
  Write-Host "Task ready for review:"
  Write-Host "  $reviewPath"
  return $true
}

function Process-ReviewTask {
  param([Parameter(Mandatory = $true)][System.IO.FileInfo]$TaskFile)

  if ($AutoApproveReview -eq 0) {
    return $false
  }

  $taskTitle = Get-TaskTitle -TaskPath $TaskFile.FullName
  $task = Read-AgentTaskFile -Path $TaskFile.FullName
  $worktree = $task.Metadata['worktree']
  if ([string]::IsNullOrWhiteSpace($worktree) -or -not (Test-Path $worktree)) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "Review task worktree missing for '$taskTitle'."
    return $true
  }

  if (-not (Test-AgentWorktreeHasImplementation -Worktree $worktree -RepoRoot $repoRoot)) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "Review task '$taskTitle' has no implementation changes beyond TASK.md."
    return $true
  }

  $testCommand = Resolve-TaskTestCommand -TaskPath $TaskFile.FullName
  if ([string]::IsNullOrWhiteSpace($testCommand)) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "No review test_command set for '$taskTitle'."
    return $true
  }

  Write-Host "Auto-reviewing '$taskTitle':"
  git -C $worktree status --short
  git -C $worktree diff --stat
  Write-Host "Running review tests:"
  Write-Host "  $(Normalize-AgentCommand -CommandText $testCommand -RepoRoot $repoRoot)"
  $exitCode = Invoke-AgentCommand -WorkingDirectory $worktree -CommandText $testCommand -RepoRoot $repoRoot
  if ($exitCode -ne 0) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "Review tests failed for '$taskTitle' (exit code $exitCode)."
    return $true
  }

  $approvedPath = Move-AgentTaskFile -SourcePath $TaskFile.FullName -TargetFolder $approvedFolder -NewState 'approved'
  Write-Host "Auto-approved task:"
  Write-Host "  $approvedPath"
  return $true
}

function Process-ApprovedTask {
  param([Parameter(Mandatory = $true)][System.IO.FileInfo]$TaskFile)

  if ($AutoApplyApproved -eq 0) {
    return $false
  }

  $taskTitle = Get-TaskTitle -TaskPath $TaskFile.FullName
  $task = Read-AgentTaskFile -Path $TaskFile.FullName
  $worktree = $task.Metadata['worktree']
  if ([string]::IsNullOrWhiteSpace($worktree) -or -not (Test-Path $worktree)) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "Approved task worktree missing for '$taskTitle'."
    return $true
  }
  if (-not (Test-AgentWorktreeHasImplementation -Worktree $worktree -RepoRoot $repoRoot)) {
    Move-ToBlocked -TaskPath $TaskFile.FullName -Reason "Approved task '$taskTitle' has no implementation changes to merge."
    return $true
  }
  Write-Host "Auto-merging approved task '$taskTitle'..."
  $mergeScript = Join-Path $repoRoot 'grainbids\infra\scripts\prepare-agent-merge.ps1'
  try {
    & $mergeScript -TaskPath $TaskFile.FullName -Apply
    return $true
  }
  catch {
    Write-Host "Auto-merge deferred for '$taskTitle': $($_.Exception.Message)"
    return $false
  }
}

do {
  $didWork = $false

  $nextApproved = Get-NextAgentTaskFile -Folder $approvedFolder
  if ($nextApproved) {
    $didWork = (Process-ApprovedTask -TaskFile $nextApproved) -or $didWork
  }

  if (-not $didWork) {
    $nextReview = Get-NextAgentTaskFile -Folder $reviewFolder
    if ($nextReview) {
      $didWork = (Process-ReviewTask -TaskFile $nextReview) -or $didWork
    }
  }

  if (-not $didWork) {
    $nextQueued = Get-NextAgentTaskFile -Folder $queuedFolder
    if ($nextQueued) {
      $didWork = (Process-QueuedTask -TaskFile $nextQueued) -or $didWork
    }
  }

  if (-not $didWork) {
    Write-Host "No agent work found."
    if (-not $RunOnce) {
      Start-Sleep -Seconds ([Math]::Max(1, $PollIntervalSeconds))
    }
  }
}
while (-not $RunOnce)
