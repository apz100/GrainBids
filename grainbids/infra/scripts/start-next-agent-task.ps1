param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$queuedFolder = Get-AgentStateFolder -State 'queued' -RepoRoot $repoRoot

if (-not (Test-Path $queuedFolder)) {
  Write-Host "No queued tasks folder found."
  exit 0
}

$nextTask = Get-ChildItem -Path $queuedFolder -Filter *.md -File | Sort-Object Name | Select-Object -First 1
if (-not $nextTask) {
  Write-Host "No queued tasks found."
  exit 0
}

$startScript = Join-Path $repoRoot 'grainbids\infra\scripts\start-agent-task.ps1'
& $startScript -TaskPath $nextTask.FullName

