# GrainBids Platform

`grainbids/` is the active GrainBids platform codebase.
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

Optional API env values:
- `ALLOW_IMPLICIT_ORG=true` allows local dev requests without `X-Org-Id`.
- `ALERT_EMAIL_*` + `ALERT_SMTP_*` enable outbound email when alert events are created.

Web:
- `cd apps/web`
- `npm install`
- `npm run dev`

## Notes
- This is the single active runtime architecture for GrainBids.
- Legacy Flask/SQLite and old orchestration code are archived under `archive/`.
- Alembic migrations live in `apps/api/alembic/versions`.
- Admin-only routes (source refresh/seed, quote export, ingestion run trigger) accept `X-User-Role: admin`.

DB migrate:
- `infra/scripts/db-migrate.ps1 -DatabaseUrl <url>`

Daily ingestion (manual):
- `infra/scripts/run-daily-ingestion.ps1`
- logs are written to `.runlogs/daily-ingestion-*.log`

Daily ingestion (Windows Scheduled Task):
- Preview task config:
  - `infra/scripts/register-daily-ingestion-task.ps1`
- Register task:
  - `infra/scripts/register-daily-ingestion-task.ps1 -Apply`

