# GrainBids API

## Local ingestion loop

The fastest local validation path is now:

1. Reprocess the latest file-backed source.
2. Print the latest snapshot diagnostics immediately after.

From `C:\Users\Scaleuser\Documents\Code\GrainBids\grainbids\apps\api`:

```powershell
.\scripts\reprocess-latest-file-source.ps1
```

If the last remembered snapshot path is wrong, force the local file path explicitly:

```powershell
.\scripts\reprocess-latest-file-source.ps1 -SourceFilePath "C:\path\to\Ontario_CashBids_latest.xlsx"
```

Optional source filter:

```powershell
.\scripts\reprocess-latest-file-source.ps1 -SourceId "<source-uuid>"
```

Skip duplicate diagnostics and only print the ingestion result:

```powershell
.\scripts\reprocess-latest-file-source.ps1 -SkipDiagnostics
```

The underlying Python job is:

```powershell
.\.venv\Scripts\python.exe -m app.jobs.reprocess_latest_file_source
```

## Related commands

Diagnostics only:

```powershell
.\.venv\Scripts\python.exe -m app.jobs.ingestion_diagnostics
```

Recompute canonical rows for the latest snapshot only:

```powershell
.\.venv\Scripts\python.exe -m app.jobs.ingestion_diagnostics --recompute-latest
```

Environment override for a stable local file path:

```env
REPROCESS_SOURCE_FILE_PATH_OVERRIDE=C:\path\to\Ontario_CashBids_latest.xlsx
```

Admin API endpoints:

```powershell
irm "$api/api/ingestion/diagnostics" -Headers $h
irm "$api/api/ingestion/source-file/reprocess-latest" -Method Post -Headers $h
```
