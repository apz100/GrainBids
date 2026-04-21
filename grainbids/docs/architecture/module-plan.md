# GrainBids Module Plan

GrainBids is the umbrella product. Product modules consume shared platform services instead of owning duplicated ingestion or pricing logic.

## Frontend Routes
- `app/bids`: normalized bid dashboard and market comparison
- `app/sources`: source management and source refresh entrypoints
- `app/sources`: configured source-file ingestion, manual admin trigger, and run status
- `app/alerts`: alert-rule workflow scaffold
- `app/quotes`: quote-builder workflow scaffold
- `app/watchlists`: saved market views scaffold
- `app/settings`: organization, source mapping, billing, and access scaffold

## Backend Routes
- `api/routes/bids.py`: bids module metadata; current bid data lives in normalized-price routes
- `api/routes/sources.py`: sources module metadata; source records and market-data routes are active
- `api/routes/ingestion.py`: source-file ingestion trigger and run history
- `api/routes/alerts.py`: alerts module scaffold
- `api/routes/quotes.py`: quotes module scaffold
- `api/routes/watchlists.py`: watchlists module scaffold
- `api/routes/settings.py`: settings module scaffold

## Shared Platform Services
- `app/platform/market_data`: shared grain-price fetching layer
- `app/services/market_data.py`: source refresh orchestration
- `app/services/source_file_ingestion.py`: CSV/XLSX file ingestion and run metadata
- `app/services/upload_csv.py`: reusable normalization and persistence helpers

## Current Product Focus
The first working path remains:

`configured source file -> ingestion run -> normalization -> normalized_prices -> bids dashboard`
