# Content Draft Engine Task

Branch: `agent/content-drafts`
Base: `origin/agent/regional-source-foundation` (PR #3 / migration `0016`)

## Goal

Persist deterministic, QA-gated daily and weekly content draft bundles from existing canonical GrainBids data. The feature ends at a read-only review surface and cannot send or publish anything.

## In scope

- `ContentDraft` model and Alembic migration `0017`.
- Region/cadence selection and deterministic fact-pack construction.
- Exact delivery/futures matching, currency/unit separation, freshness and coverage QA.
- Deterministic email, social and site draft renderers with numeric fact lineage.
- Fingerprinted, idempotent persistence.
- Draft-only CLI job with `--cadence` and optional `--region`.
- Authenticated read-only list/detail API endpoints.
- Focused tests for daily/weekly generation, QA boundaries, lineage, idempotency and absence of outbound calls.

## Guardrails

- No LLM calls.
- No email sending or publisher integration.
- No send/publish flags.
- No subscriber, scraping, source-activation, social-credential or deployment changes.
- Reuse existing canonical data and market-report helpers where safe.

## Done when

- One Eastern Ontario daily or weekly canonical dataset produces a persisted draft bundle.
- Facts, artifacts and QA are readable through authenticated endpoints.
- Identical reruns return the same row.
- All persisted statuses are `draft`, `draft_needs_review` or `blocked`.
- Focused tests pass and the work is committed locally only.
