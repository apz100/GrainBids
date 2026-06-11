param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$queueRoot = Get-AgentQueueRoot -RepoRoot $repoRoot

$states = @('queued', 'in-progress', 'review', 'approved', 'blocked', 'done')
foreach ($state in $states) {
  $folder = Join-Path $queueRoot $state
  if (-not (Test-Path $folder)) {
    continue
  }
  Write-Host "[$state]"
  Get-ChildItem -Path $folder -Filter *.md -File | ForEach-Object {
    $task = Read-AgentTaskFile -Path $_.FullName
    $title = $task.Metadata['task_title']
    if (-not $title) { $title = $_.BaseName }
    $branch = $task.Metadata['branch']
    if (-not $branch) { $branch = '-' }
    Write-Host "  $title"
    Write-Host "    branch: $branch"
    Write-Host "    path:   $($_.FullName)"
  }
}

