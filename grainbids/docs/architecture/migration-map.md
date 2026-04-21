# GrainBids Migration Map

This file tracks legacy -> GrainBids migration boundaries.

## Main Runtime
- Keep: `grainbids/apps/web` and `grainbids/apps/api`
- Legacy runtime paths are archived and not extended.

## Logic Migrated in this step
- Legacy parse/symbol helpers -> `apps/api/app/modules/imports/legacy_helpers.py`
- Legacy dataframe normalization pattern -> `apps/api/app/modules/imports/legacy_normalize.py`
- Posted bid validation baseline -> `apps/api/app/modules/quotes/posted_bid.py`
- Source config TOML loading pattern -> `apps/api/app/modules/imports/source_config.py`

## Remaining High-Value Migrations
- Source fetch orchestration (`GrainBidder.py`) into `apps/api` jobs/services
- Selected source adapters from root `*_source.py`
- Legacy test intent from `app/tests/*` into API service tests

- Grain price source pullers promoted into main API module path: `app/modules/market_sources` (copied from legacy archive).
- Grain price platform layer established at `app/platform/market_data`; GrainBids modules consume this shared backend service layer.


