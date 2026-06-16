# GrainBids Platform

`grainbids/` is the active GrainBids platform codebase.
BasisBoard is the bids/market module inside GrainBids, not a separate product.

## Stack
- `apps/web`: Next.js + TypeScript + Tailwind
- `apps/api`: FastAPI + SQLAlchemy + Alembic
- `packages/*`: shared package placeholders

## Product modules
- `GrainBids / Market`: canonical bid discovery, radius search, basis/cash movement, top movers, and watchlist/alert creation
- `GrainBids / Sources`: source definitions, source health, ingestion runs, canonical coverage, source priority controls, and manual ingestion triggers
- `GrainBids / Alerts`: threshold rules, open alert triage, delivery status, and notification history
- `GrainBids / Quotes`: delivered-value and quote sheet generation
- `GrainBids / Watchlists`: saved market views, saved searches, CRUD, and previews
- `GrainBids / Signals`: forecast rows and signal health
- `GrainBids / Settings`: admin shell for organization defaults and access controls

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
- `AUTH_CONTEXT_MODE=local_headers` allows local dev role/email headers; production must use `trusted_proxy`.
- `ALLOW_LOCAL_HEADER_AUTH=true` allows local dev users that are not seeded in the `users` table.
- `ALERT_EMAIL_*` + `ALERT_SMTP_*` enable outbound email when alert events are created.
- `API_CORS_ORIGINS` controls allowed frontend origins.
- `API_ENABLE_DOCS=false` can disable Swagger/OpenAPI in production.

Web:
- `cd apps/web`
- `npm install`
- `npm run dev`

## Notes
- This is the single active runtime architecture for GrainBids.
- `/` is a lightweight product entry page. The active market dashboard is `/bids`, with `/dashboard` preserved as the underlying dashboard route.
- `/upload` and `/uploads` are deprecated web compatibility routes that redirect to `/sources`.
- Legacy Flask/SQLite and old orchestration code are archived under `archive/`.
- Alembic migrations live in `apps/api/alembic/versions`.
- Admin-only routes accept `X-User-Role: admin` only in local-header development mode. Production resolves role from the active `users` row identified by `X-Auth-User-Id`.

## Parallel coding workflow
- Guide: `docs/operations/multi-agent-workflow.md`
- Task template: `docs/operations/TASK.template.md`
- Worktree bootstrap: `infra/scripts/new-agent-worktree.ps1`
- Queue tools: `infra/scripts/enqueue-agent-task.ps1`, `infra/scripts/start-next-agent-task.ps1`, `infra/scripts/start-agent-task.ps1`, `infra/scripts/review-agent-task.ps1`, `infra/scripts/prepare-agent-merge.ps1`, `infra/scripts/close-agent-task.ps1`, `infra/scripts/list-agent-tasks.ps1`, `infra/scripts/verify-agent-queue.ps1`, `infra/scripts/watch-agent-queue.ps1`
- Use one worktree per task and keep task scope narrow enough for review in one diff.

DB migrate:
- `infra/scripts/db-migrate.ps1 -DatabaseUrl <url>`

Daily ingestion (manual):
- `infra/scripts/run-daily-ingestion.ps1`
- one-step fetch + ingest (local): `infra/scripts/run-fetch-and-ingest.ps1 -Fetcher dynamic`
- logs are written to `.runlogs/daily-ingestion-*.log`
- one-step fetch + ingest (local): `infra/scripts/run-fetch-and-ingest.ps1 -Fetcher dynamic`
- optional cloud-safe upload + ingest trigger:
  - set env: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GRAINBIDS_API_URL`, `NEXT_PUBLIC_ORG_ID`
  - run:
    - `infra/scripts/run-fetch-and-ingest.ps1 -Fetcher grainbidder -UploadToSupabase -SupabaseBucket ingestion -SupabasePrefix ontario -TriggerCloudIngestion`

Daily ingestion (Windows Scheduled Task):
- Preview task config:
  - `infra/scripts/register-daily-ingestion-task.ps1`
- Register task:
  - `infra/scripts/register-daily-ingestion-task.ps1 -Apply`
- Default schedule is `08:00` and `15:00` local time. Override with `-StartTimes "HH:mm,HH:mm"`.
- For Ontario fetch + ingest in one run (recommended for local file pipelines):
  - Preview task config: `infra/scripts/register-fetch-and-ingest-task.ps1 -Fetcher grainbidder`
  - Register task: `infra/scripts/register-fetch-and-ingest-task.ps1 -Fetcher grainbidder -Apply`

## Production baseline (Vercel + Render + Supabase)
API (`apps/api`) required env:
- `APP_ENV=production`
- `DATABASE_URL=<supabase postgres url>`
- `ALLOW_IMPLICIT_ORG=false`
- `AUTH_CONTEXT_MODE=trusted_proxy`
- `ALLOW_LOCAL_HEADER_AUTH=false`
- `API_CORS_ORIGINS=https://grainbids.com,https://www.grainbids.com,https://<your-vercel-domain>`

Web (`apps/web`) required env:
- `NEXT_PUBLIC_API_URL=https://<your-api-domain>`
- `NEXT_PUBLIC_ORG_ID=<org-uuid>`
- `NEXT_PUBLIC_AUTH_USER_ID=<trusted auth user id>`

Health checks:
- Liveness: `GET /health/live`
- Readiness (DB): `GET /health/ready` (returns `503` when DB unavailable)
- Scripted smoke test: `infra/scripts/smoke-test.ps1 -ApiBaseUrl https://<api-domain> -WebBaseUrl https://<web-domain> -CheckWeb -OrgId <org-uuid> -UserRole admin`

Scheduling:
- Use host scheduler/cron at `08:00` and `15:00` America/Toronto.
- Job command: `python -m app.jobs.daily_source_ingestion`
- For Render-hosted ingestion, set `sources.url` to stable public HTTPS file URLs (not local `P:\...` paths).

