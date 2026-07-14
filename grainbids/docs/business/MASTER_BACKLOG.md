# GrainBids master backlog

This is the portable source of truth for autonomous GrainBids work. Keep no more than three items `ACTIVE`: one per track.

## Active

| ID | Track | Priority | Outcome | Definition of done | Status | Gate / dependency |
|---|---|---:|---|---|---|---|
| R-002 | Revenue | P0 | Three customer-ready proof packs | Snapshot, freight/netback, and paid-pilot scorecard templates are populated from verified data and presentation-ready | ACTIVE | Production snapshot access or authorized data required; do not invent prices |
| P-002 | Product/data | P0 | Source validation harness and pilot console | One candidate can be probed manually, scored, reviewed, promoted, or quarantined without scheduled activation or price persistence | ACTIVE | Stacked on PR #3; no live probes |
| C-002 | Content/operations | P0 | Daily/weekly draft generator | Persisted QA-gated email/site/social drafts are created from verified snapshots and never sent | ACTIVE | Stacked on PR #3; no publishing |

## Next

| ID | Track | Priority | Outcome | Definition of done | Status | Dependency / gate |
|---|---|---:|---|---|---|---|
| R-003 | Revenue | P0 | Initial prospect pipeline | Thirty qualified organizations with reason-to-buy, contact role, and sample angle | QUEUED | Public research; contact requires approval |
| P-003 | Product/data | P1 | Regional source configuration | Country, currency, timezone, region, and source ownership are configurable without invented metadata | QUEUED | P-002 |
| C-003 | Content/operations | P1 | Content approval queue | Drafts expose evidence, warnings, status, reviewer decision, and revision history | QUEUED | C-002 |
| R-004 | Revenue | P1 | Paid pilot package | One-page scope, onboarding checklist, success metrics, terms, and recurring conversion path | QUEUED | R-001 |
| P-004 | Product/data | P1 | Customer-ready market report export | Branded PDF/CSV/email-preview output with provenance, units, currency, delivery, futures, and freight disclosures | QUEUED | Verified data |
| P-005 | Product/data | P1 | Regional comparison model | Compare bids across regions only when units, currency, timing, grade, and freight assumptions are compatible | QUEUED | P-003 |
| C-004 | Content/operations | P2 | Content performance feedback | Track signup, open, click, lead, and conversion metrics by issue and content type | QUEUED | Actual distribution approval |

## Completed

| ID | Track | Outcome | Evidence |
|---|---|---|---|
| O-001 | Operations | Grain-merchandising decision skill | Installed `analyze-grain-merchandising` skill |
| O-002 | Operations | Persistent GrainBids business skill | Created `build-grainbids-business` skill |
| P-000 | Product/data | Signup and guarded weekly report foundation | PRs #1 and #2 merged; production deployment passed |
| R-001 | Revenue | Productized GrainBids service offer | CAD $750 snapshot, $2,500 pilot, and managed monthly desk documented in `SERVICE_OFFER.md` |
| C-001 | Content/operations | Autonomous draft content engine specification | Fact-pack, QA, storage, scheduling, templates, metrics, and implementation scope documented in `CONTENT_ENGINE.md` |

## Blocked or deliberately deferred

| Item | Reason |
|---|---|
| Full elevator-management suite | The user is not buying/running an elevator; no paying demand validates this scope |
| Merge PR #3 | Draft is mergeable and its Vercel preview passed; merge awaits explicit authorization |
| Nationwide bulk scraping | Source rights, reliability, load, normalization, and commercial need must be validated region-by-region |
| Automatic market email/social sending | Requires explicit approval, tested content QA, sender configuration, unsubscribe compliance, and monitoring |
| Broad farmer marketplace | High surface area and low initial revenue per user relative to B2B services |
| Polished multi-tenant SaaS infrastructure | Defer until a paid workflow proves recurring demand |
