# BasisBoard

Monorepo for BasisBoard: a grain bid monitoring SaaS.

## Stack
- `apps/web`: Next.js + TypeScript + Tailwind
- `apps/api`: FastAPI + SQLAlchemy + Alembic
- `packages/*`: shared packages placeholders

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
- Docker is intentionally omitted for now to keep the MVP moving fast.
- Alembic migrations live in `apps/api/alembic/versions`.

DB migrate:
- infra/scripts/db-migrate.ps1 -DatabaseUrl <url>

