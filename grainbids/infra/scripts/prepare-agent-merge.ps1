param(
  [Parameter(Mandatory = $true)]
  [string]$TaskPath,

  [switch]$Apply,

  [string]$TestCommand = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
if (-not (Test-Path $TaskPath)) {
  throw "Task file not found: $TaskPath"
}

$task = Read-AgentTaskFile -Path $TaskPath
$taskState = $task.Metadata['state']
if ($taskState -ne 'approved') {
  throw "Task must be in approved state before merge prep. Current state: $taskState"
}

$branch = $task.Metadata['branch']
if ([string]::IsNullOrWhiteSpace($branch)) {
  throw "Task does not record a branch name."
}

$worktree = $task.Metadata['worktree']
if ([string]::IsNullOrWhiteSpace($worktree) -or -not (Test-Path $worktree)) {
  throw "Task worktree is missing or not recorded."
}

$resolvedTestCommand = $TestCommand
if ([string]::IsNullOrWhiteSpace($resolvedTestCommand)) {
  $resolvedTestCommand = $task.Metadata['test_command']
}

git -C $repoRoot fetch origin --prune

$mainBranch = 'main'
$originMain = "origin/$mainBranch"
$currentBranch = git -C $worktree rev-parse --abbrev-ref HEAD
$branchHead = git -C $worktree rev-parse HEAD
$mainHead = git -C $repoRoot rev-parse $originMain

$mergePrepFolder = Join-Path $repoRoot '.agent\merge-prep'
if (-not (Test-Path $mergePrepFolder)) {
  New-Item -ItemType Directory -Path $mergePrepFolder -Force | Out-Null
}

$prepName = [System.IO.Path]::GetFileName($TaskPath)
$prepPath = Join-Path $mergePrepFolder $prepName
$prepLines = @(
  '---'
  "task_title: $($task.Metadata['task_title'])"
  "branch: $branch"
  "worktree: $worktree"
  "state: merge_prepared"
  "created_at: $((Get-Date).ToString('o'))"
  "updated_at: $((Get-Date).ToString('o'))"
  '---'
  '# Merge prep'
  ''
  "Approved task: $($task.Metadata['task_title'])"
  "Branch: $branch"
  "Worktree: $worktree"
  "Worktree branch: $currentBranch"
  "Branch head: $branchHead"
  "Origin main head: $mainHead"
  ''
  '## Next action'
  $(if ($Apply) { 'Apply merge to main now.' } else { 'Review the merge prep, then re-run with -Apply to merge.' })
  ''
)
Set-Content -LiteralPath $prepPath -Value $prepLines

Write-Host "Merge prep written:"
Write-Host "  $prepPath"

if (-not $Apply) {
  Write-Host "Dry run only. Re-run with -Apply to merge into main."
  exit 0
}

$dirty = git -C $repoRoot status --short
if ($dirty) {
  throw "Repo root has uncommitted changes. Clean the repo before applying merge."
}

if (-not [string]::IsNullOrWhiteSpace($resolvedTestCommand)) {
  $normalizedTestCommand = Normalize-AgentCommand -CommandText $resolvedTestCommand -RepoRoot $repoRoot
  Write-Host "Running merge-prep tests in approved worktree:"
  Write-Host "  $normalizedTestCommand"
  $exitCode = Invoke-AgentCommand -WorkingDirectory $worktree -CommandText $resolvedTestCommand -RepoRoot $repoRoot
  if ($exitCode -ne 0) {
    throw "Merge-prep tests failed with exit code $exitCode"
  }
}
else {
  Write-Host "No test command provided; continuing without extra verification."
}

git -C $repoRoot checkout $mainBranch
git -C $repoRoot merge --no-ff --no-edit $branch
git -C $repoRoot push origin $mainBranch

$doneFolder = Get-AgentStateFolder -State 'done' -RepoRoot $repoRoot
$updatedTaskPath = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $doneFolder -NewState 'done'

Write-Host "Merged and marked done:"
Write-Host "  $updatedTaskPath"
