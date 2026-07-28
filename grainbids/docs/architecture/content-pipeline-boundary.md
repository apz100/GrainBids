# GrainBids Content Pipeline Boundary

## Decision

GrainBids and the content pipeline are separate systems.

- `apz100/GrainBids` owns operational cash-bid ingestion, canonical prices, companies, facilities, users, alerts, subscribers, delivery records, historical bid data and guarded SMTP delivery.
- `apz100/GrainBids-Content` owns government/public-data collectors, market calculations, fact packs, charts, newsletter and article rendering, social drafts, approval workflow and its own execution history.
- GrainBids-Content receives operational bid data only through authenticated, versioned, read-only HTTP contracts.
- GrainBids-Content must never receive GrainBids database credentials and must never write directly to the GrainBids operational database.

Ontario remains the first proprietary cash-bid module. Region and currency fields are explicit in the contracts so Canadian and North American content can be added without moving operational cash-bid ownership out of GrainBids.

## Existing PR disposition

### PR #6: QA-gated content draft engine

Reusable in GrainBids-Content after removing GrainBids database coupling:

- region/cadence configuration concepts
- canonical input normalization
- freshness, coverage, currency, unit and lineage QA rules
- fact-pack schema and deterministic fingerprints
- issue-key generation
- posted-bid range and strict basis-change calculations
- artifact lineage validation
- deterministic HTML/plain-text/site/social rendering patterns
- pure tests for fact generation, blocking and deduplication

Rewrite before reuse:

- replace `load_content_rows()` SQLAlchemy access with a client for the snapshot API below
- persist fact packs, artifacts and run state in the content repository's own database/storage
- replace `ContentDraft`, `generate_content_draft()` and the GrainBids job with content-service models and pipeline orchestration
- move region configuration out of application code and support Ontario, Canada and North American scopes
- replace GrainBids application settings imports with content-service configuration

Do not merge into GrainBids:

- migration `0017_add_content_drafts.py`
- `ContentDraft` operational model
- `/api/content-drafts` routes
- `generate_content_drafts` job
- content-engine persistence or permanent rendering logic

### PRs #3 and #5

These PRs concern operational cash-bid source metadata, candidate registration, source probing, promotion and quarantine. Those responsibilities remain in GrainBids because cash-bid ingestion is core operational data. Government and market-intelligence collectors belong in GrainBids-Content.

### PR #7

PR #7 remains an unsafe mixed recovery branch and must not be used as the content-system base. Relevant Ontario beta work must continue to be recovered under issue #9 in focused branches.

## GrainBids read-only snapshot contract

### Endpoint

`GET /api/content/v1/snapshots/cash-bids`

### Authentication

`Authorization: Bearer <server-held content snapshot key>`

The key is configured only on the GrainBids API and GrainBids-Content service. It must never be exposed through `NEXT_PUBLIC_*`, browser JavaScript or repository files. GrainBids may accept multiple active keys during rotation through `CONTENT_SNAPSHOT_API_KEYS`.

The endpoint is fixed to the organization configured by `CONTENT_SNAPSHOT_ORG_ID`; clients cannot select an arbitrary organization.

### Query parameters

- `region`: optional case-insensitive region filter, maximum 120 characters
- `commodity`: optional repeated value; defaults to `Corn`, `Soybeans`, `Wheat`
- `limit`: 1-5000; defaults to 5000

Example:

`GET /api/content/v1/snapshots/cash-bids?region=Ontario&commodity=Corn&commodity=Soybeans`

### Response

```json
{
  "schema_version": "grainbids.content-snapshot.v1",
  "snapshot_id": "sha256:...",
  "generated_at": "2026-07-28T14:00:00+00:00",
  "data_as_of": "2026-07-28T13:45:00+00:00",
  "filters": {
    "region": "Ontario",
    "commodities": ["Corn", "Soybeans"],
    "canonical_only": true,
    "latest_source_snapshot_only": true
  },
  "freshness": {
    "status": "fresh",
    "max_age_minutes": 1440,
    "age_minutes": 15.0
  },
  "row_count": 1,
  "truncated": false,
  "rows": [
    {
      "id": "normalized-price-uuid",
      "snapshot_id": "price-snapshot-uuid",
      "source_id": "source-uuid",
      "source_name": "GLG",
      "source_url": "https://example.com/bids",
      "source_type": "automated",
      "source_region": "Ontario",
      "source_confidence": 0.975,
      "source_last_success_at": "2026-07-28T13:45:00+00:00",
      "source_consecutive_failures": 0,
      "company_id": "company-uuid",
      "company_name": "Great Lakes Grain",
      "facility_id": "facility-uuid",
      "facility_name": "Chesterville",
      "facility_region": "Eastern Ontario",
      "facility_postal_code": "K0C 1H0",
      "facility_latitude": 45.1,
      "facility_longitude": -75.2,
      "buyer_name": "Great Lakes Grain",
      "captured_at": "2026-07-28T13:45:00+00:00",
      "commodity": "Corn",
      "location": "Chesterville",
      "delivery_label": "September 2026",
      "delivery_start": "2026-09-01",
      "delivery_end": "2026-09-30",
      "futures_month": "December 2026",
      "futures_price": 4.25,
      "futures_change": 0.05,
      "basis": 1.25,
      "basis_change": 0.05,
      "basis_change_strict": 0.04,
      "cash_price_bu": 5.5,
      "cash_price_mt": 216.52,
      "cash_price_bu_change": 0.09,
      "cash_price_mt_change": 3.54,
      "currency_code": "CAD",
      "cash_price_bu_unit": "CAD/bu",
      "cash_price_mt_unit": "CAD/MT",
      "basis_unit": "CAD/bu",
      "is_canonical": true,
      "canonical_rank": 1,
      "canonical_reason": "preferred source"
    }
  ]
}
```

### Consumer rules

GrainBids-Content must reject a snapshot for publication when:

- `schema_version` is unsupported
- `freshness.status` is not `fresh`
- `truncated` is `true`
- required commodities or coverage are absent
- currency or units do not match the calculation
- row lineage identifiers are absent

An empty or stale snapshot returns HTTP 200 with explicit status so the content service can persist diagnostics without mistaking transport failure for valid market content.

### Failure responses

- `401`: missing or invalid bearer key
- `422`: invalid query parameters
- `503`: interface, organization or database is not configured/available

GET requests are safe to retry. `snapshot_id` is deterministic for the returned data and filters.

## Approved-content submission contract

This is the next core-repository contract and is not implemented in the first snapshot PR.

### Endpoint

`POST /api/content/v1/issues`

### Authentication

Use a separate write-scoped bearer secret, not the snapshot-read secret.

`Authorization: Bearer <approved-content submission key>`

`Idempotency-Key: <issue-key>:<content-sha256>`

### Request

```json
{
  "schema_version": "grainbids.approved-content.v1",
  "issue_key": "north-america:daily:2026-07-28",
  "content_type": "newsletter",
  "cadence": "daily",
  "region_keys": ["ontario", "canada", "north_america"],
  "subject": "GrainBids Daily Market Brief — July 28, 2026",
  "preheader": "Cash bids, futures, crop and trade updates.",
  "html_body": "<!doctype html>...",
  "text_body": "GrainBids Daily Market Brief...",
  "content_sha256": "sha256:...",
  "source_snapshot_ids": ["sha256:..."],
  "data_as_of": "2026-07-28T13:45:00+00:00",
  "generated_at": "2026-07-28T13:50:00+00:00",
  "approved_at": "2026-07-28T13:58:00+00:00",
  "approval": {
    "method": "manual",
    "approved_by": "operator identifier",
    "notes": null
  },
  "canonical_url": null
}
```

### GrainBids behavior

- validate the schema version, content hash, sizes, required plain text and safe HTML policy
- validate that `data_as_of` satisfies the configured delivery freshness policy
- store the issue and approval metadata in GrainBids for delivery auditing
- return the existing record for an identical idempotent resubmission
- return `409` when the same `issue_key` is submitted with a different hash
- never expose subscriber records to GrainBids-Content
- never send email merely because the issue was submitted
- deliver only through the existing guarded job/admin workflow with email enabled, explicit send intent, unsubscribe insertion and per-subscriber deduplication

Recommended initial limits:

- subject: 250 characters
- preheader: 250 characters
- HTML: 500 KB
- plain text: 200 KB
- source snapshot IDs: 1-20

### Submission failures

- `401`: missing/invalid submission credential
- `409`: issue-key/hash conflict
- `413`: content exceeds size limits
- `422`: contract, hash, freshness, approval or HTML validation failure
- `503`: submission or delivery storage is disabled/unavailable

POST retries must use the same `Idempotency-Key` and payload hash.

## Versioning and reliability

- Version the HTTP path and the payload schema independently.
- Add fields compatibly within v1; never change the meaning or units of an existing field.
- Introduce `/v2` for removals, renamed semantics or incompatible calculation inputs.
- Preserve `snapshot_id`, content hash, issue key, generator version and template version in content-service run records.
- Use UTC in contracts; localize only during rendering.
- GrainBids-Content should stop the pipeline on stale, truncated, incomplete or unsupported snapshots and emit diagnostics rather than publish partial content.
- No pipeline stage may send email, publish an article or post social content without an explicit approval and enabled destination.

## Proposed `GrainBids-Content` structure

```text
GrainBids-Content/
├── .github/workflows/
│   ├── ci.yml
│   └── scheduled-dry-run.yml
├── docs/
│   ├── architecture.md
│   ├── contracts.md
│   ├── source-register.md
│   └── runbooks/
├── src/grainbids_content/
│   ├── cli.py
│   ├── config.py
│   ├── clients/
│   │   ├── grainbids.py
│   │   └── government/
│   │       ├── bank_of_canada.py
│   │       ├── statistics_canada.py
│   │       ├── usda_ams.py
│   │       ├── usda_nass.py
│   │       └── cftc.py
│   ├── collectors/
│   ├── calculations/
│   │   ├── basis.py
│   │   ├── crop_progress.py
│   │   ├── exports.py
│   │   ├── futures.py
│   │   └── fx.py
│   ├── domain/
│   │   ├── contracts.py
│   │   ├── facts.py
│   │   ├── issues.py
│   │   └── qa.py
│   ├── factpacks/
│   │   ├── builder.py
│   │   └── schemas/v1.py
│   ├── rendering/
│   │   ├── articles.py
│   │   ├── charts.py
│   │   ├── newsletter.py
│   │   ├── social.py
│   │   └── templates/
│   ├── approval/workflow.py
│   ├── delivery/grainbids_submission.py
│   ├── pipelines/
│   │   ├── daily.py
│   │   └── weekly.py
│   ├── storage/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── migrations/
│   └── observability/
│       ├── health.py
│       └── logging.py
├── tests/
│   ├── contract/
│   ├── fixtures/
│   ├── integration/
│   └── unit/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

Generated artifacts and raw downloaded data must be ignored or stored in external object storage; they should not be committed to Git.

## Implementation sequence

1. **Core PR A — read-only snapshot interface**
   - versioned GET route, server-held bearer auth, exact export service, tests and this document
   - no migration and no write path
2. **Content PR A — repository scaffold and contracts**
   - configuration, CI, snapshot client, contract fixtures and no collectors
3. **Content PR B — portable PR #6 domain logic**
   - fact schema, QA, fingerprints, calculations and pure tests; no rendering or scheduling
4. **Core PR B — approved issue persistence/submission**
   - new approved-issue model/migration and idempotent POST; store only, never send
5. **Core PR C — guarded approved-issue delivery**
   - adapt existing subscriber/delivery/SMTP code to approved HTML and plain text; explicit send remains required
6. **Content PR C onward — one collector/calculation family per PR**
   - government collectors, futures/FX, crop/trade facts and charts in non-overlapping modules
7. **Content PR D — rendering and approval workflow**
   - newsletter/article/social templates and manual approval state
8. **Content PR E — GrainBids submission client and dry-run scheduling**
   - submit approved issues only; no direct SMTP or publishing
9. **Core cleanup PR**
   - remove/deprecate the internal report generator only after external generation and guarded delivery are proven

PR #6 should remain draft/parked and should not receive additional permanent content-engine work.
