# Grain Price Ingestion (Main App Module)

This folder contains the source pulling stack now promoted into the main GrainBids API.

- Source adapters (`*_source.py`)
- Shared processing (`processing.py`)
- Source config (`config.toml`, `us_elevators_urls.toml`, `grain_bids/config.py`)
- Runner utilities (`orchestrator/` and `scripts/`)

Use this as the migration base for service-level jobs under `app/services`.
