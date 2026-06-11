param(
  [Parameter(Mandatory = $true)]
  [string]$TaskTitle,

  [string]$BranchName,

  [string]$WorktreePath,

  [string]$TaskFilePath,

  [switch]$OpenTaskTemplate
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (git rev-parse --show-toplevel).Trim()
if (-not $repoRoot) {
  throw "Unable to determine git repository root."
}

function Convert-ToSlug {
  param([string]$Value)
  $slug = $Value.ToLowerInvariant()
  $slug = $slug -replace '[^a-z0-9]+', '-'
  $slug = $slug.Trim('-')
  if ([string]::IsNullOrWhiteSpace($slug)) {
    throw "Task title produced an empty slug."
  }
  return $slug
}

$slug = Convert-ToSlug -Value $TaskTitle
if (-not $BranchName) {
  $BranchName = "agent/$slug"
}
if (-not $WorktreePath) {
  $WorktreePath = Join-Path $repoRoot ".worktrees\$slug"
}

$parentDir = Split-Path -Parent $WorktreePath
if (-not (Test-Path $parentDir)) {
  New-Item -ItemType Directory -Path $parentDir | Out-Null
}

if (Test-Path $WorktreePath) {
  throw "Worktree path already exists: $WorktreePath"
}

git worktree add -b $BranchName $WorktreePath

$taskTemplatePath = Join-Path $repoRoot "grainbids\docs\operations\TASK.template.md"
$taskPath = Join-Path $WorktreePath "TASK.md"
if ($TaskFilePath) {
  Copy-Item -LiteralPath $TaskFilePath -Destination $taskPath
}
else {
  Copy-Item $taskTemplatePath $taskPath
}

@"
Worktree created:
  path:   $WorktreePath
  branch: $BranchName
  task:   $taskPath

Next steps:
  1. Fill in TASK.md.
  2. Do the work in this worktree only.
  3. Run the relevant tests before review.
"@ | Write-Host

if ($OpenTaskTemplate) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Get-Content -Path '$taskPath'"
}
