param(
  [Parameter(Mandatory = $true)]
  [string]$TaskTitle,

  [string]$Objective = '',

  [string]$Background = '',

  [string]$Scope = '',

  [string]$FilesLikelyToChange = '',

  [string]$Constraints = '',

  [string]$AcceptanceCriteria = '',

  [string]$TestsToRun = '',

  [string]$TestCommand = '',

  [string]$Risks = '',

  [string]$OpenQuestions = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path (git rev-parse --show-toplevel).Trim() 'grainbids\infra\scripts\agent-task-lib.ps1')

$repoRoot = Get-AgentRepoRoot
$queueFolder = Get-AgentStateFolder -State 'queued' -RepoRoot $repoRoot
if (-not (Test-Path $queueFolder)) {
  New-Item -ItemType Directory -Path $queueFolder -Force | Out-Null
}

$timestamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
$slug = Convert-ToAgentSlug -Value $TaskTitle
$fileName = "$timestamp-$slug.md"
$taskPath = Join-Path $queueFolder $fileName

$branch = "agent/$slug"
$worktree = Join-Path $repoRoot ".worktrees\$slug"

$frontMatter = @{}
$frontMatter['task_title'] = $TaskTitle
$frontMatter['slug'] = $slug
$frontMatter['branch'] = $branch
$frontMatter['worktree'] = $worktree
$frontMatter['state'] = 'queued'
$frontMatter['created_at'] = (Get-Date).ToString('o')
$frontMatter['updated_at'] = (Get-Date).ToString('o')
if (-not [string]::IsNullOrWhiteSpace($TestCommand)) {
  $frontMatter['test_command'] = $TestCommand
}

$objectiveText = if ([string]::IsNullOrWhiteSpace($Objective)) { '' } else { $Objective }
$backgroundText = if ([string]::IsNullOrWhiteSpace($Background)) { '' } else { $Background }
$scopeText = if ([string]::IsNullOrWhiteSpace($Scope)) { '' } else { $Scope }
$filesText = if ([string]::IsNullOrWhiteSpace($FilesLikelyToChange)) { '' } else { $FilesLikelyToChange }
$constraintsText = if ([string]::IsNullOrWhiteSpace($Constraints)) { '' } else { $Constraints }
$acceptanceText = if ([string]::IsNullOrWhiteSpace($AcceptanceCriteria)) { '' } else { $AcceptanceCriteria }
$testsText = if ([string]::IsNullOrWhiteSpace($TestsToRun)) { '' } else { $TestsToRun }
$testCommandText = if ([string]::IsNullOrWhiteSpace($TestCommand)) { '' } else { $TestCommand }
$risksText = if ([string]::IsNullOrWhiteSpace($Risks)) { '' } else { $Risks }
$openQuestionsText = if ([string]::IsNullOrWhiteSpace($OpenQuestions)) { '' } else { $OpenQuestions }

$body = @(
  '# Task',
  '',
  '## Objective',
  $objectiveText,
  '',
  '## Background',
  $backgroundText,
  '',
  '## Scope',
  $scopeText,
  '',
  '## Files likely to change',
  $filesText,
  '',
  '## Constraints',
  $constraintsText,
  '',
  '## Acceptance criteria',
  $acceptanceText,
  '',
  '## Tests to run',
  $testsText,
  '',
  '## Test command',
  $testCommandText,
  '',
  '## Risks / follow-ups',
  $risksText,
  '',
  '## Open questions',
  $openQuestionsText,
  '',
  '## Handoff notes',
  ''
)

Write-AgentTaskFile -Path $taskPath -Metadata $frontMatter -Body $body

Write-Host "Queued task:"
Write-Host "  $taskPath"
Write-Host "Next:"
Write-Host "  start-agent-task.ps1 -TaskPath `"$taskPath`""
