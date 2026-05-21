param(
    [string]$ApiDir = "",
    [string]$OrgId = "",
    [string]$SourceId = "",
    [string]$SourceFilePath = "",
    [int]$DuplicateLimit = 10,
    [switch]$SkipDiagnostics
)

$ErrorActionPreference = "Stop"

if (-not $ApiDir) {
    $ApiDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$PythonExe = Join-Path $ApiDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Python virtualenv not found at $PythonExe"
}

$ArgsList = @(
    "-m",
    "app.jobs.reprocess_latest_file_source"
)

if ($OrgId) {
    $ArgsList += @("--org-id", $OrgId)
}
if ($SourceId) {
    $ArgsList += @("--source-id", $SourceId)
}
if ($SourceFilePath) {
    $ArgsList += @("--source-file-path", $SourceFilePath)
}
if ($DuplicateLimit -gt 0) {
    $ArgsList += @("--duplicate-limit", "$DuplicateLimit")
}
if ($SkipDiagnostics) {
    $ArgsList += "--skip-diagnostics"
}

Write-Host "Running latest file-source reprocess from $ApiDir"
if ($SourceFilePath) {
    Write-Host "Using explicit file override: $SourceFilePath"
}

Push-Location $ApiDir
try {
    & $PythonExe @ArgsList
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
