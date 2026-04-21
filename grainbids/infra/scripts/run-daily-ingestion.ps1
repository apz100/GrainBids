param(
  [string]$ApiDir = "$PSScriptRoot\..\..\apps\api"
)

Set-Location $ApiDir
python -m app.jobs.daily_source_ingestion
