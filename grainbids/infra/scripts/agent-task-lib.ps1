function Get-AgentRepoRoot {
  return (git rev-parse --show-toplevel).Trim()
}

function Convert-ToAgentSlug {
  param([Parameter(Mandatory = $true)][string]$Value)
  $slug = $Value.ToLowerInvariant()
  $slug = $slug -replace '[^a-z0-9]+', '-'
  $slug = $slug.Trim('-')
  if ([string]::IsNullOrWhiteSpace($slug)) {
    throw "Value produced an empty slug."
  }
  return $slug
}

function Get-AgentQueueRoot {
  param([string]$RepoRoot)
  if (-not $RepoRoot) {
    $RepoRoot = Get-AgentRepoRoot
  }
  return Join-Path $RepoRoot ".agent\queue"
}

function Get-AgentStateFolder {
  param(
    [Parameter(Mandatory = $true)]
    [string]$State,

    [string]$RepoRoot
  )
  $queueRoot = Get-AgentQueueRoot -RepoRoot $RepoRoot
  return Join-Path $queueRoot $State
}

function Read-AgentTaskFile {
  param([Parameter(Mandatory = $true)][string]$Path)

  $lines = Get-Content -LiteralPath $Path
  if ($lines.Count -eq 0) {
    return [pscustomobject]@{
      Metadata = @{}
      Body     = @()
    }
  }

  if ($lines[0] -ne '---') {
    return [pscustomobject]@{
      Metadata = @{}
      Body     = $lines
    }
  }

  $metadata = @{}
  $end = -1
  for ($i = 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -eq '---') {
      $end = $i
      break
    }
    if ($lines[$i] -match '^(?<key>[^:]+):\s*(?<value>.*)$') {
      $key = $Matches.key.Trim().ToLowerInvariant()
      $metadata[$key] = $Matches.value
    }
  }

  if ($end -lt 0) {
    throw "Task file '$Path' is missing the closing frontmatter delimiter."
  }

  $body = @()
  if ($end + 1 -lt $lines.Count) {
    $body = $lines[($end + 1)..($lines.Count - 1)]
  }

  return [pscustomobject]@{
    Metadata = $metadata
    Body     = $body
  }
}

function Write-AgentTaskFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][hashtable]$Metadata,
    [string[]]$Body
  )

  $orderedKeys = @('task_title', 'slug', 'branch', 'worktree', 'state', 'created_at', 'updated_at')
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add('---')

  foreach ($key in $orderedKeys) {
    if ($Metadata.ContainsKey($key)) {
      $lines.Add("${key}: $($Metadata[$key])")
    }
  }

  foreach ($key in ($Metadata.Keys | Sort-Object)) {
    if ($orderedKeys -contains $key) {
      continue
    }
    $lines.Add("${key}: $($Metadata[$key])")
  }

  $lines.Add('---')

  if ($Body) {
    foreach ($line in $Body) {
      $lines.Add($line)
    }
  }

  $parent = Split-Path -Parent $Path
  if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent | Out-Null
  }

  Set-Content -LiteralPath $Path -Value $lines
}

function Move-AgentTaskFile {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$TargetFolder,
    [Parameter(Mandatory = $true)][string]$NewState
  )

  $task = Read-AgentTaskFile -Path $SourcePath
  $metadata = @{}
  foreach ($key in $task.Metadata.Keys) {
    $metadata[$key] = $task.Metadata[$key]
  }
  $metadata['state'] = $NewState
  $metadata['updated_at'] = (Get-Date).ToString('o')

  if ($metadata.ContainsKey('task_title') -and -not $metadata.ContainsKey('slug')) {
    $metadata['slug'] = Convert-ToAgentSlug -Value $metadata['task_title']
  }

  if (-not (Test-Path $TargetFolder)) {
    New-Item -ItemType Directory -Path $TargetFolder -Force | Out-Null
  }

  $targetPath = Join-Path $TargetFolder (Split-Path -Leaf $SourcePath)
  Write-AgentTaskFile -Path $targetPath -Metadata $metadata -Body $task.Body
  Remove-Item -LiteralPath $SourcePath -Force
  return $targetPath
}
