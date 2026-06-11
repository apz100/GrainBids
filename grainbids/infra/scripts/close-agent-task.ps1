param(
  [Parameter(Mandatory = $true)]
  [string]$TaskPath,

  [ValidateSet('approved', 'done', 'blocked')]
  [string]$State = 'done'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
if (-not (Test-Path $TaskPath)) {
  throw "Task file not found: $TaskPath"
}

$targetFolder = Get-AgentStateFolder -State $State -RepoRoot $repoRoot
$updatedPath = Move-AgentTaskFile -SourcePath $TaskPath -TargetFolder $targetFolder -NewState $State

Write-Host "Moved task to ${State}:"
Write-Host "  $updatedPath"
