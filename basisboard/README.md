# GrainBids Platform

`basisboard/` is the active GrainBids platform codebase.
BasisBoard is the bids/market module inside GrainBids, not a separate product.

## Stack
- `apps/web`: Next.js + TypeScript + Tailwind
- `apps/api`: FastAPI + SQLAlchemy + Alembic
- `packages/*`: shared package placeholders

## Product modules
- `GrainBids / Bids`: upload, normalization, basis tracking, and market comparison
- `GrainBids / Alerts`: threshold rules and triggered alerts
- `GrainBids / Quotes`: delivered-value and quote sheet generation
- `GrainBids / Sources`: source definitions, mappings, and ingest
- `GrainBids / Watchlists`: tracked markets and priority rows
- `GrainBids / Admin`: org settings and access controls

## Local dev
1. Copy `.env.example` to `.env` in repo root.
2. Copy `apps/api/.env.example` to `apps/api/.env` and set `DATABASE_URL`.
3. Copy `apps/web/.env.example` to `apps/web/.env.local`.

API:
- `cd apps/api`
- `python -m venv .venv`
- `./.venv/Scripts/activate`
- `pip install -r requirements.txt`
- `uvicorn app.main:app --reload`

Web:
- `cd apps/web`
- `npm install`
- `npm run dev`

## Notes
- This is the single active runtime architecture for GrainBids.
- Legacy Flask/SQLite and old orchestration code are archived under `archive/`.
- Alembic migrations live in `apps/api/alembic/versions`.

DB migrate:
- `infra/scripts/db-migrate.ps1 -DatabaseUrl <url>`
