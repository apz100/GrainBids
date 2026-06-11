param(
  [Parameter(Mandatory = $true)]
  [string]$TaskPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
if (-not (Test-Path $TaskPath)) {
  throw "Task file not found: $TaskPath"
}

$task = Read-AgentTaskFile -Path $TaskPath
$title = $task.Metadata['task_title']
if (-not $title) {
  $title = Split-Path $TaskPath -LeafBase
}

$slug = $task.Metadata['slug']
if (-not $slug) {
  $slug = Convert-ToAgentSlug -Value $title
}

$branch = $task.Metadata['branch']
if (-not $branch) {
  $branch = "agent/$slug"
}

$worktree = $task.Metadata['worktree']
if (-not $worktree) {
  $worktree = Join-Path $repoRoot ".worktrees\$slug"
}

$worktreeParent = Split-Path -Parent $worktree
if (-not (Test-Path $worktreeParent)) {
  New-Item -ItemType Directory -Path $worktreeParent -Force | Out-Null
}

if (-not (Test-Path $worktree)) {
  $newWorktreeScript = Join-Path $repoRoot 'grainbids\infra\scripts\new-agent-worktree.ps1'
  & $newWorktreeScript -TaskTitle $title -BranchName $branch -WorktreePath $worktree -TaskFilePath $TaskPath
}
else {
  $worktreeTaskPath = Join-Path $worktree 'TASK.md'
  if (-not (Test-Path $worktreeTaskPath)) {
    throw "Worktree already exists but TASK.md is missing: $worktreeTaskPath"
  }
  Write-Host "Reusing existing worktree:"
  Write-Host "  path:   $worktree"
  Write-Host "  branch: $branch"
}

$inProgressFolder = Get-AgentStateFolder -State 'in-progress' -RepoRoot $repoRoot
$updatedPath = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $inProgressFolder -NewState 'in_progress'

$worktreeTaskPath = Join-Path $worktree 'TASK.md'
if (Test-Path $worktreeTaskPath) {
  Copy-Item -LiteralPath $updatedPath -Destination $worktreeTaskPath -Force
}

Write-Host "Started task:"
Write-Host "  task:     $updatedPath"
Write-Host "  branch:   $branch"
Write-Host "  worktree: $worktree"
