# GrainBids technical execution roadmap after draft PR #3

## Outcome and sequencing

Draft PR #3 (`Add guarded regional source foundation`) is the prerequisite for this roadmap. It adds target-aware US adapters, inactive candidate import, explicit pilot promotion/quarantine, and collection-status polling gates. It should be reviewed and merged before any item below.

The next technical work follows this dependency chain:

`PR #3 -> PR #4 pilot console -> PR #5 geography -> PR #6 publication gate -> PR #7 regional reports -> PR #8 content packs -> PR #9 consulting briefs -> PR #10 public report archive -> PR #11 weekly pipeline`

The work is deliberately split into small PRs. New source collection, email delivery, public publishing, social posting, and paid services remain off unless separately authorized.

## Single best next code PR

**PR #4 — Add a guarded regional-source pilot console** is the best next PR after #3.

PR #3 creates the backend safety model, but an operator still cannot safely inspect a candidate from the web interface before promoting it. PR #4 turns the foundation into a usable workflow: import candidates, run one explicit bounded probe that does not activate or persist market data, inspect schema/row quality, then promote or quarantine intentionally. This is the shortest path to proving that GrainBids can collect a second region without blindly scheduling dozens of sites.

---

## PR #4 — Guarded regional-source pilot console

### Objective

Add an admin-only candidate workflow to `/sources`: import the researched candidate list, run one bounded probe against one candidate, inspect a small sanitized preview and quality summary, then explicitly promote or quarantine it. A probe must not activate the source, schedule future polling, or persist normalized prices.

### Dependencies

- Draft PR #3 merged.
- No live candidate needs to be promoted for the code PR itself.

### Likely files

- `grainbids/apps/api/app/api/routes/sources.py`
- `grainbids/apps/api/app/services/source_probe.py` (new)
- `grainbids/apps/api/app/services/us_source_candidates.py`
- `grainbids/apps/web/app/sources/page.tsx`
- `grainbids/apps/api/tests/test_source_candidate_probe.py` (new)
- `grainbids/apps/api/tests/test_source_collection_controls.py`
- `grainbids/README.md`

### Acceptance criteria

- Admin can import US candidates from the Sources page and see `candidate`, `pilot`, `active`, and `quarantined` states.
- `POST /api/sources/{id}/probe` works only for inactive candidates using a supported target-aware adapter and a URL present in the approved candidate configuration.
- Probe has one attempt, the source timeout ceiling, a small response row cap (for example 20 preview rows), sanitized scalar values, and no arbitrary redirect/URL override from the request.
- Probe returns columns, raw row count, required-field coverage, supported commodities, locations, and a clear pass/fail reason.
- Candidate remains inactive and no `PriceSnapshot`, `NormalizedPrice`, scheduled poll, or promotion mutation is created by probing.
- Promote and quarantine buttons require confirmation and refresh the displayed status.
- No batch-probe button and no automatic promotion.

### Tests

- Mock successful Agricharts and DTN probes; no real network in tests.
- Reject non-admin, active, quarantined, unsupported-adapter, missing-URL, and non-allowlisted candidates.
- Assert probe does not mutate activation/status or persist price records.
- Web production build and TypeScript checks.

### Risks and controls

- Scraper blocking or site changes: show the failure; never retry a candidate in a loop.
- SSRF/arbitrary fetch: require the stored URL to exactly match the repository candidate record and permit HTTPS only.
- Accidental load: one explicit source per request, no batch action, existing timeout.
- Site terms/robots expectations still require business review before sustained polling.

### Autonomy gate

Safe autonomously: implementation, unit tests, build, and draft PR.

Requires explicit approval: running a live probe, promoting a candidate, or enabling scheduled polling.

### Sellable outcome

Provides a credible, demonstrable “we can add another market safely” workflow and begins proving the regional data network that underpins subscriptions, content, and consulting.

---

## PR #5 — Replace source-name region hacks with real market geography

### Objective

Create stable geography fields and filtering so Eastern Ontario, a US state, or another market can be selected by actual location/source metadata rather than matching a region to hard-coded source names. Unknown geography stays explicitly unresolved.

### Dependencies

- PR #3 for source country/currency/timezone fields.
- Can be developed after #3 while #4 is being reviewed, but should rebase after #4 if both touch Sources UI types.

### Likely files

- `grainbids/apps/api/alembic/versions/0017_add_market_geography.py` (new)
- `grainbids/apps/api/app/models/location.py`
- `grainbids/apps/api/app/models/source.py`
- `grainbids/apps/api/app/services/us_source_candidates.py`
- `grainbids/apps/api/app/services/canonical_resolver.py`
- `grainbids/apps/api/app/services/market_canonicalization.py`
- `grainbids/apps/api/app/api/routes/normalized_prices.py`
- `grainbids/apps/web/app/dashboard/page.tsx`
- `grainbids/apps/api/tests/test_normalized_price_filters.py`
- `grainbids/apps/api/tests/test_market_canonicalization.py`

### Acceptance criteria

- Location/source geography supports country code, first-level subdivision (Ontario/state), and a controlled market-region slug/display label.
- Existing known Eastern Ontario locations are backfilled deterministically; unknown rows remain null/unresolved rather than guessed.
- Region facets and filters use geography joins/fields, not `NormalizedPrice.source_name` membership.
- API can filter independently by market region, subdivision, and country without mixing currencies.
- Dashboard defaults to Eastern Ontario through a single region filter instead of twelve parallel location requests.
- US candidate configuration can hold reviewed geography metadata; candidates lacking it are visibly unresolved and cannot enter a regional report.

### Tests

- Migration upgrade/downgrade and existing-data backfill.
- Eastern Ontario filter parity against known locations.
- US subdivision isolation, unresolved geography exclusion, and no source-name false positives.
- Facet serialization and dashboard production build.

### Risks and controls

- Elevator companies span multiple states: assign geography to parsed locations where possible; source-level geography is only fallback metadata.
- Name-based geocoding is error-prone: no automatic city/state inference in this PR.
- Existing filters may change counts: add parity fixtures for the current Eastern Ontario set.

### Autonomy gate

Safe autonomously: schema, deterministic backfill, tests, and draft PR.

Requires explicit review: ambiguous location assignments. They must be reported, not guessed.

### Sellable outcome

Turns GrainBids from an Eastern Ontario-coded site into a genuine regional platform foundation and allows the same product/report to be sold market by market.

---

## PR #6 — Add a publication-readiness gate for reports and content

### Objective

Prevent stale, thin, mixed-currency, or unhealthy data from becoming an email or public report. Preview remains available with visible warnings; delivery/publishing fails closed.

### Dependencies

- PR #5 geography.
- Existing report service and source-health records from PRs #2/#3.

### Likely files

- `grainbids/apps/api/app/services/report_readiness.py` (new)
- `grainbids/apps/api/app/services/market_report.py`
- `grainbids/apps/api/app/api/routes/market_report.py`
- `grainbids/apps/api/app/jobs/weekly_market_report.py`
- `grainbids/apps/api/app/core/config.py`
- `grainbids/apps/api/.env.example`
- `grainbids/apps/api/tests/test_report_readiness.py` (new)
- `grainbids/apps/api/tests/test_market_report.py`

### Acceptance criteria

- Readiness result includes region, currency, data timestamp, fresh-source count, healthy-source count, market count per commodity, rejected/outlier count, and explicit blocking reasons.
- Preview returns report plus readiness warnings even when not publishable.
- `--send` refuses delivery when readiness fails; there is no force flag in this PR.
- A report cannot combine CAD and USD rows or unresolved geography.
- Thresholds are conservative configuration values with documented defaults.
- The report continues to disclose that freight is excluded and remains a posted-bid snapshot, not a delivered recommendation.

### Tests

- Fresh/healthy fixture passes.
- Stale, no-source, low-coverage, unresolved-region, and mixed-currency fixtures fail with deterministic reasons.
- Dry run still renders warnings; delivery sender is never called on failure.
- Existing report idempotency tests remain green.

### Risks and controls

- A strict gate can block a sparse but useful region: surface exact reasons and adjust reviewed thresholds rather than bypassing the gate.
- Quality scores may appear precise without being meaningful: expose component facts, not only one score.

### Autonomy gate

Safe autonomously. It adds a fail-closed safeguard and does not turn on delivery.

### Sellable outcome

Creates the trust layer needed to charge for market intelligence: every report can state how current and complete its underlying market sample is.

---

## PR #7 — Regional report profiles and subscriber preferences

### Objective

Generate separate market reports by controlled region/currency and send each subscriber only the report they requested. Keep all delivery switches off.

### Dependencies

- PR #5 geography.
- PR #6 readiness gate.

### Likely files

- `grainbids/apps/api/alembic/versions/0018_add_report_profiles.py` (new)
- `grainbids/apps/api/app/models/report_profile.py` (new)
- `grainbids/apps/api/app/models/newsletter_subscriber.py`
- `grainbids/apps/api/app/models/market_report_delivery.py`
- `grainbids/apps/api/app/models/__init__.py`
- `grainbids/apps/api/app/api/routes/newsletter.py`
- `grainbids/apps/api/app/api/routes/market_report.py`
- `grainbids/apps/api/app/services/market_report.py`
- `grainbids/apps/api/app/jobs/weekly_market_report.py`
- `grainbids/apps/web/app/_components/market-report-signup.tsx`
- `grainbids/apps/api/tests/test_newsletter.py`
- `grainbids/apps/api/tests/test_market_report.py`

### Acceptance criteria

- A report profile specifies region slug, display name, country, currency, timezone, enabled commodities, and active/draft status.
- Eastern Ontario is migrated as the default profile without unsubscribing or duplicating existing subscribers.
- Signup accepts only active profile identifiers supplied by the API; no arbitrary region strings.
- Issue and delivery uniqueness includes report profile so two regional issues in one ISO week do not collide.
- Job can preview one profile or all active profiles, but `--send` still requires existing email configuration plus readiness pass.
- Subscribers receive only their chosen profile; audience and consent fields are preserved.

### Tests

- Migration of existing subscribers to Eastern Ontario.
- Invalid/inactive profile rejection and idempotent resubscription.
- Recipient segmentation and per-profile issue keys.
- Mixed-region leakage test and web build.

### Risks and controls

- Free-form regions create duplicate segments: use profile IDs and controlled slugs.
- Consent scope: keep the existing consent copy/version and record profile changes.
- A profile without sufficient data must remain draft/not ready.

### Autonomy gate

Safe autonomously: code, migration, tests, and draft profiles.

Requires explicit approval: creating a live public region promise or enabling delivery.

### Sellable outcome

Enables regional newsletter products instead of a single Eastern Ontario list, with the same software serving farmers, grain businesses, and agricultural professionals.

---

## PR #8 — Generate an approval-ready content pack from each report

### Objective

Turn one readiness-approved data snapshot into reusable, deterministic content: email text/HTML, website summary, LinkedIn draft, short social draft, and a machine-readable JSON payload. Generate drafts only; do not post externally.

### Dependencies

- PR #6 readiness gate.
- PR #7 report profiles.

### Likely files

- `grainbids/apps/api/app/services/content_pack.py` (new)
- `grainbids/apps/api/app/api/routes/market_report.py`
- `grainbids/apps/api/app/services/market_report.py`
- `grainbids/apps/web/app/market-report/page.tsx` (new admin preview page)
- `grainbids/apps/web/app/_components/top-nav.tsx`
- `grainbids/apps/api/tests/test_content_pack.py` (new)

### Acceptance criteria

- One endpoint/CLI input produces all formats from the exact same `MarketReport` object and data-as-of timestamp.
- Every format includes region, currency/unit labels, source/data timestamp, freight disclaimer, and a link back to GrainBids.
- Claims are limited to computed facts (top posted bids, medians/ranges, weekly changes when comparable); no invented causes or trade recommendations.
- Draft content is copyable/downloadable and clearly marked `draft` until approved.
- JSON schema is versioned for later n8n/Node-RED/CRM integrations.
- No LLM dependency, social credentials, or auto-posting in this PR.

### Tests

- Golden fixtures for email, web, LinkedIn, short post, and JSON.
- Missing data degrades to explicit “not enough verified data,” not fabricated prose.
- Currency/unit/freight language is present in every format.
- Deterministic output for identical report input and web build.

### Risks and controls

- Repetitive content: first prove reliable factual generation; optional style variation can come later.
- Platform character limits: enforce format-specific limits in tests.
- Misleading rankings: label posted bid and delivery period; never imply delivered netback.

### Autonomy gate

Safe autonomously: generation and drafts.

Requires explicit approval: external posting or email sending.

### Sellable outcome

Creates the content engine for a grain newsletter/content business and drastically reduces the manual work needed to publish from GrainBids data.

---

## PR #9 — Add a consulting-grade delivered-netback opportunity brief

### Objective

Extend the existing quote export into a client-ready comparison that keeps cash bid, futures contract, basis, delivery window, currency, freight assumption, and netback separate. It should compare scenarios, not tell a client to trade.

### Dependencies

- PR #5 geography/currency.
- PR #6 data readiness concepts.
- Existing `quotes` export functionality.

### Likely files

- `grainbids/apps/api/app/services/netback_brief.py` (new)
- `grainbids/apps/api/app/api/routes/quotes.py`
- `grainbids/apps/api/app/models/quote_run.py`
- `grainbids/apps/web/app/quotes/page.tsx`
- `grainbids/apps/api/tests/test_netback_brief.py` (new)
- `grainbids/apps/api/tests/test_price_comparison.py`

### Acceptance criteria

- User selects commodity, origin/market region, delivery period, and candidate bids, then enters freight explicitly in $/MT and/or $/bu with currency.
- Output shows posted cash, freight, delivered/FOB interpretation, netback, basis/futures month, bid timestamp, and ranking by netback.
- Missing freight is labeled `not included`; it is never silently treated as zero in a client-facing brief.
- Different currencies cannot be ranked without an explicit FX rate and timestamp; FX is an assumption, not fetched implicitly.
- Brief stores all assumptions with the quote run and exports CSV/XLSX initially.
- Includes “scenario comparison, verify quote/grade/freight; not a recommendation” language.

### Tests

- Per-MT and per-bushel freight math for corn and soybeans.
- FOB versus delivered scenarios, missing freight, FX-required, mismatched futures/delivery labels, and stable ranking.
- Assumptions round-trip through `QuoteRun` and export columns.
- Web build.

### Risks and controls

- Freight direction/unit mistakes can reverse the result: explicit signs, units, currency, and test fixtures.
- Stale buyer quotes: show captured-at and block rows that fail readiness thresholds.
- Avoid presenting gross spread as profit; costs and assumptions remain separate.

### Autonomy gate

Safe autonomously: calculation code, exports, and tests.

Requires explicit approval: sending a generated brief to a client or filling unknown freight/FX assumptions.

### Sellable outcome

Provides the first concrete consulting deliverable GrainBids can generate for farmers or grain businesses: a transparent bid/freight/netback comparison.

---

## PR #10 — Draft market-report issue archive with explicit publishing

### Objective

Store immutable generated issues and support an SEO-friendly public report page only after explicit admin publication. Subscriber data stays private, and draft issues are never public.

### Dependencies

- PR #7 report profiles.
- PR #8 content pack.

### Likely files

- `grainbids/apps/api/alembic/versions/0019_add_market_report_issues.py` (new)
- `grainbids/apps/api/app/models/market_report_issue.py` (new)
- `grainbids/apps/api/app/models/__init__.py`
- `grainbids/apps/api/app/services/market_report.py`
- `grainbids/apps/api/app/api/routes/market_report.py`
- `grainbids/apps/web/app/reports/[region]/[issue]/page.tsx` (new)
- `grainbids/apps/web/app/reports/[region]/page.tsx` (new)
- `grainbids/apps/api/tests/test_market_report_issues.py` (new)

### Acceptance criteria

- Generated issue stores profile, issue key, data-as-of, readiness snapshot, subject, sanitized HTML/text/JSON content, and content hash.
- Default status is `draft`; only admin can publish/unpublish.
- Public API/page returns only `published` issues and no organization, subscriber, delivery, or internal error data.
- Published issue is immutable; changes create a revision/new issue record rather than silently rewriting history.
- Page includes region/currency/data timestamp, methodology/disclaimer, signup CTA, canonical metadata, and current-bids link.
- A failed-readiness issue cannot be published.

### Tests

- Draft privacy, admin authorization, readiness enforcement, idempotent generation/content hash, immutable published issue, and public serialization.
- XSS/sanitization fixture and Next.js production build.

### Risks and controls

- Publishing incorrect data: explicit action plus readiness gate; no automatic publish.
- Stale SEO pages: date/data-as-of are prominent and current report is linked.
- Duplicate content: canonical region/issue URLs and immutable issues.

### Autonomy gate

Safe autonomously: draft generation, tests, and PR.

Requires explicit approval: publishing an issue publicly.

### Sellable outcome

Builds a searchable proof-of-work library that attracts newsletter leads and demonstrates historical market intelligence to consulting/software prospects.

---

## PR #11 — Idempotent weekly business pipeline, dry-run by default

### Objective

Coordinate the existing pieces into one observable weekly run: check source health, evaluate report readiness, generate regional report/content drafts, create a draft issue, and summarize what is ready. Delivery and publishing require separate explicit flags and existing feature switches.

### Dependencies

- PRs #6, #7, #8, and #10.
- PR #9 can remain an on-demand consulting workflow and is not required by the weekly content pipeline.

### Likely files

- `grainbids/apps/api/alembic/versions/0020_add_pipeline_runs.py` (new)
- `grainbids/apps/api/app/models/pipeline_run.py` (new)
- `grainbids/apps/api/app/models/__init__.py`
- `grainbids/apps/api/app/services/weekly_pipeline.py` (new)
- `grainbids/apps/api/app/jobs/weekly_business_pipeline.py` (new)
- `grainbids/apps/api/app/api/routes/market_report.py`
- `grainbids/apps/web/app/market-report/page.tsx`
- `grainbids/apps/api/tests/test_weekly_pipeline.py` (new)
- `grainbids/README.md`

### Acceptance criteria

- Default command performs no polling, sending, publishing, posting, or paid API calls.
- Pipeline records stage status, timestamps, input issue/profile, readiness facts, output IDs, and concise errors.
- Rerunning the same profile/issue is idempotent and reuses the same drafts unless inputs changed.
- Failure in one profile does not corrupt another; final summary identifies blocked and ready profiles.
- `--send` and `--publish` are separate, explicit, mutually observable actions, still constrained by readiness and configuration switches.
- No social auto-post flag in this PR.
- Admin can view the latest pipeline result and copy/download ready content.

### Tests

- Full dry-run happy path with mocked repositories/sender.
- Readiness failure, partial profile failure, rerun/idempotency, changed-input revision, send-disabled, and publish-disabled cases.
- Assert no sender/publisher/source fetch is called by default.
- CLI exit codes and web build.

### Risks and controls

- Hidden side effects in an “autonomous” job: default is a pure draft workflow and side-effect calls are separately injected/tested.
- Partial runs and duplicate sends: stage records plus existing per-subscriber issue idempotency.
- Scheduler drift: store UTC timestamps and profile timezone; scheduling configuration remains outside this PR.

### Autonomy gate

Safe autonomously: code, tests, dry runs, and draft generation.

Requires explicit approval: installing a production cron schedule, sending, or publishing.

### Sellable outcome

This is the autonomous operating loop: GrainBids can prepare regional market intelligence and content without requiring a new prompt at each stage while retaining human control over external publication.

---

## Deliberately deferred

The following should not interrupt the eight-PR path unless a real customer requires them:

- Scraping all 24 candidates or expanding the candidate list before two or three sources prove reliable.
- Automatic AI market commentary or causal explanations; deterministic verified facts come first.
- Automatic social posting, outbound sales email, or subscriber delivery.
- Paid market-data, FX, geocoding, CRM, billing, or social APIs.
- Multi-tenant billing/permissions overhaul, mobile app, elaborate forecasting, or a generalized workflow builder.
- PDF design work before CSV/XLSX consulting briefs are being used with real prospects.

## Merge and execution rule for every PR

For each item: branch from current `main`; keep one objective; run targeted tests plus the web build when touched; inspect the exact diff, unresolved comments, and deployment check; merge with an expected-head SHA; verify production; then rebase/retarget the next stacked branch and re-check its diff. Operational activation is a separate decision from merging code.
