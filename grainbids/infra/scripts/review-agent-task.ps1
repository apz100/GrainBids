param(
  [Parameter(Mandatory = $true)]
  [string]$TaskPath,

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
$worktree = $task.Metadata['worktree']
if (-not $worktree) {
  throw "Task does not record a worktree path."
}

Write-Host "Diff summary:"
git -C $worktree status --short
git -C $worktree diff --stat

if ($TestCommand) {
  $normalizedTestCommand = Normalize-AgentCommand -CommandText $TestCommand -RepoRoot $repoRoot
  Write-Host "Running test command:"
  Write-Host "  $normalizedTestCommand"
  $exitCode = Invoke-AgentCommand -WorkingDirectory $worktree -CommandText $TestCommand -RepoRoot $repoRoot
  if ($exitCode -ne 0) {
    throw "Review test command failed with exit code $exitCode"
  }
}

$reviewFolder = Get-AgentStateFolder -State 'review' -RepoRoot $repoRoot
$updatedPath = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $reviewFolder -NewState 'review'

Write-Host "Moved to review:"
Write-Host "  $updatedPath"
