param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$matches = @(
  Find-AgentTasks -RepoRoot $repoRoot -States @('queued', 'in-progress', 'review', 'approved', 'blocked', 'done') -IncludeMergePrep
)

if ($matches.Count -eq 0) {
  Write-Host 'No agent tasks found.'
  exit 0
}

$issues = New-Object System.Collections.Generic.List[string]
$groups = $matches | Group-Object { $_.Metadata['branch'] } | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Name) }

foreach ($group in $groups) {
  $branch = $group.Name
  if ($group.Count -gt 1) {
    $issues.Add("Duplicate queue artifacts for branch '$branch':")
    foreach ($artifact in $group.Group | Sort-Object State, Path) {
      $issues.Add("  [$($artifact.State)] $($artifact.Path)")
    }
  }

  if (Test-AgentBranchMergedIntoMain -Branch $branch -RepoRoot $repoRoot) {
    foreach ($artifact in $group.Group | Where-Object { $_.State -in @('blocked', 'merge-prep') }) {
      $issues.Add("Stale applied artifact for merged branch '$branch' is still in $($artifact.State): $($artifact.Path)")
    }
  }
}

if ($issues.Count -gt 0) {
  $issues | ForEach-Object { Write-Host $_ }
  exit 1
}

Write-Host 'Queue is consistent.'
