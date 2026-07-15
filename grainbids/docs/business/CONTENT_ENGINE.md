# GrainBids Content Engine

Status: proposed architecture

Initial operating mode: autonomous draft generation, human-reviewed publishing

Primary launch region: Eastern Ontario
Expansion target: configuration-driven Canadian and US regions

## 1. Outcome

GrainBids should turn verified bid records into a repeatable content system without allowing a language model, scheduler, or weak data feed to invent market conclusions or publish on its own.

The first useful version automatically creates a review queue containing:

- one daily email draft per active region;
- one weekly market-report email draft per active region;
- short social-post variants derived from the same facts;
- a site update derived from the same facts;
- a QA report showing exactly why the draft passed, warned, or failed.

Generation is automatic. Sending and publishing are not. Every artifact begins with `publication_status=draft`, and the initial content engine has no outbound email or social publishing dependency.

## 2. Non-negotiable rules

1. **Facts are computed before prose is written.** SQL and deterministic Python build a versioned fact pack. A language model may rewrite approved facts but may not calculate prices, basis, rankings, changes, freight, or conversions.
2. **Every numeric sentence is traceable.** Each publishable claim points to a fact ID and the normalized-price rows used to calculate it.
3. **Delivery periods remain attached to prices.** A nearby bid and a harvest bid may appear in the same snapshot, but they are not described as directly comparable unless the delivery bucket is the same.
4. **Futures months remain attached to basis.** Basis changes use `basis_change_strict` or an equivalent exact comparison matching commodity, location, delivery period, and futures month. A contract roll is not presented as a basis move.
5. **Currency and units are explicit.** A fact pack has one declared currency and cash/basis unit per value. CAD and USD values are never pooled in an average, range, ranking, or change.
6. **Freight treatment is explicit.** Posted bids are described as posted/FOB values unless a verified delivered lane and freight cost exist. A headline bid is never called the best netback when freight is unknown.
7. **Freshness and coverage are visible.** Every issue states the data-as-of time, source count, location count, and omitted-data warnings.
8. **No manufactured commentary.** Missing data produces an omission or a clearly labelled limitation, not a guessed market explanation.
9. **No initial auto-send.** A successful scheduled run creates drafts only. The existing weekly delivery service remains separate and is not called by the content engine.
10. **No trade recommendations from posted bids alone.** Content may describe observable prices and strict changes. It may not tell a producer to sell, hedge, store, or ship without the required freight, risk, delivery, and market context.

## 3. Existing GrainBids foundation

The repository already provides most of the trustworthy input layer:

- canonical normalized prices with delivery labels/ranges, futures month, futures price, basis, cash price, strict changes, and capture time;
- source, company, location, and region metadata;
- source health and guarded regional-source activation;
- newsletter subscribers, unsubscribe handling, SMTP delivery, and per-subscriber weekly delivery idempotency;
- a deterministic weekly market-report compiler and dry-run job;
- outbound weekly email disabled unless both configuration and an explicit `--send` flag are supplied.

The content engine should extend this foundation rather than introduce a second scraper, subscriber system, or sending path.

## 4. System flow

```text
successful ingestion
        |
        v
regional eligibility check
        |
        v
deterministic fact pack --------> QA: facts, coverage, freshness, units
        |                                      |
        | pass                                 | fail
        v                                      v
channel renderers / constrained copy       blocked issue + diagnostics
        |
        v
email + social + site draft bundle
        |
        v
QA: traceability, prohibited claims, channel rules
        |
        v
human review queue (never auto-send initially)
```

One fact pack is the source of truth for every channel. Repurposing never queries prices again and never asks a model to reconstruct a number from prose.

## 5. Inputs

### 5.1 Required market inputs

Use canonical rows only. A content run loads:

- `normalized_prices.id` and `snapshot_id`;
- commodity;
- company and location IDs and display names;
- source name and source ID where available;
- region, country, currency, and timezone from the source/location configuration;
- capture timestamp;
- delivery label, start, and end;
- futures month and futures price;
- basis;
- cash price per bushel and/or metric tonne;
- `basis_change_strict`;
- cash-price change in the same unit;
- canonical status and reason;
- source confidence, collection status, and last-success time.

### 5.2 Region configuration

Content behavior belongs in data/configuration rather than region-specific code. Each region needs:

```toml
[regions.eastern_ontario]
display_name = "Eastern Ontario"
country_code = "CA"
timezone = "America/Toronto"
currency = "CAD"
cash_units = ["CAD/bu", "CAD/MT"]
basis_unit = "CAD/bu"
commodities = ["Corn", "Soybeans", "Wheat"]
daily_draft_local_time = "16:30"
weekly_draft_day = "Friday"
weekly_draft_local_time = "17:00"
freshness_hours = 24
minimum_healthy_sources = 2
minimum_locations_per_commodity = 2
```

Future regions can declare USD values, their own timezone, supported commodities, freshness thresholds, and preferred display units without changing templates.

### 5.3 Optional context inputs

These inputs may enrich content only when verified and timestamped:

- exchange rates with provider, observation time, and conversion direction;
- futures settlements with exchange, contract code, settlement time, and currency/unit;
- verified freight lanes and cost basis;
- editorial calendar events such as report dates or contract expiries;
- approved GrainBids calls to action and campaign tags.

Optional inputs never silently fill a missing required field. For example, an FX value may convert a basis only when its source and effective timestamp are recorded in the claim lineage.

## 6. Deterministic transformations

### 6.1 Normalize and partition

1. Filter to active region, eligible source status, canonical rows, supported commodities, declared currency, and the run's freshness window.
2. Partition by:
   - region;
   - commodity;
   - currency and unit;
   - delivery bucket;
   - futures month for basis facts.
3. Create a normalized delivery bucket from `delivery_start` and `delivery_end`. If neither can be parsed, retain the original label and set `delivery_bucket_quality=unresolved`; do not use it in direct comparisons.
4. Deduplicate using the canonical record and preserve every source row ID in lineage.

### 6.2 Produce atomic facts

The engine may produce these facts when their prerequisites pass:

- highest and lowest posted cash bid within one commodity/delivery/currency/unit bucket;
- posted-bid range and median within that same bucket;
- location count and healthy-source count;
- day-over-day cash change for an exact comparable record;
- strict basis change for an exact commodity/location/delivery/futures comparison;
- count of bids added, removed, changed, or unchanged;
- regional data freshness and coverage;
- optional delivered netback only when `netback = posted bid - verified freight - declared costs` is fully populated.

Every fact has a neutral description. `highest_posted_bid` does not become `best sale` or `best netback` unless verified freight and all relevant costs are present.

### 6.3 Grain-merchandising calculation rules

- Governing identity: `basis = cash - futures` only after cash and futures use the same currency and unit.
- Validate the stored basis against that identity when all three values exist. A variance outside a configured rounding tolerance blocks that claim.
- Never combine basis values referencing different futures contracts in an average or change statistic.
- Never describe a contract-roll difference as local basis movement.
- Never compare delivered destinations by headline bid when freight is absent.
- When freight is omitted, append `before freight` or `freight not included` to the relevant table or sentence.
- Use `CAD` for Eastern Ontario output and print the unit on every material number.
- Do not infer a cause for a price move from the bid data. Phrases such as “because of farmer selling,” “export demand,” or “tight supplies” require a separate cited source and are outside the initial engine.

## 7. Fact-pack contract

The fact pack is immutable JSON stored with the issue. A simplified shape is:

```json
{
  "schema_version": "1",
  "issue_key": "eastern_ontario:daily:2026-07-14",
  "region_key": "eastern_ontario",
  "region_name": "Eastern Ontario",
  "content_cadence": "daily",
  "generated_at": "2026-07-14T20:35:00Z",
  "data_as_of": "2026-07-14T20:10:00Z",
  "currency": "CAD",
  "coverage": {
    "healthy_sources": 5,
    "locations": 18,
    "commodities": ["Corn", "Soybeans"]
  },
  "facts": [
    {
      "fact_id": "corn:2026-10:highest_cash_bu",
      "fact_type": "highest_posted_bid",
      "commodity": "Corn",
      "delivery_start": "2026-10-01",
      "delivery_end": "2026-10-31",
      "futures_month": "Dec 2026",
      "value": 5.42,
      "currency": "CAD",
      "unit": "CAD/bu",
      "freight_included": false,
      "source_row_ids": ["normalized-price-uuid"],
      "claim_text": "The highest listed October corn bid was $5.42 CAD/bu before freight."
    }
  ],
  "warnings": [],
  "input_fingerprint": "sha256:..."
}
```

The example values illustrate the contract only and are not market data.

## 8. Content templates

Templates consume fact IDs, not raw database rows. Every rendered numeric span records the fact ID that supplied it.

### 8.1 Daily email draft

Subject:

```text
GrainBids {{ region_name }} daily snapshot — {{ local_date }}
```

Body:

```text
Data as of {{ data_as_of_local }}. Coverage: {{ healthy_sources }} sources and
{{ locations }} locations.

TODAY'S POSTED BIDS
{{ for each commodity and comparable delivery bucket }}
{{ commodity }} — {{ delivery_label }}
Highest listed: {{ highest_posted_bid }} at {{ buyer_location }}, before freight.
Listed range: {{ low }} to {{ high }} {{ currency }}/{{ unit }} across {{ count }} bids.
{{ end }}

STRICT CHANGES
{{ only exact delivery/futures matches with verified prior values }}
{{ buyer_location }} {{ commodity }} {{ delivery_label }} basis changed
{{ signed_change }} {{ basis_unit }} versus the previous comparable observation.

WHAT TO VERIFY
Posted-bid snapshot only. Freight is not included unless specifically stated.
Verify grade, delivery window, futures contract, currency, and current buyer terms.

View current bids: {{ public_url }}
```

If there are no valid strict changes, use “No comparable strict basis changes met today’s publication rules.” Do not substitute a looser comparison.

### 8.2 Weekly email draft

Retain the current report's top-bid tables and add only auditable sections:

1. data-as-of and weekly coverage;
2. posted bids grouped by commodity and delivery bucket;
3. largest strict basis changes observed during the week;
4. locations with newly available or removed bids;
5. limitations and missing coverage;
6. site call to action.

Avoid a single “top three” ranking across unrelated delivery periods. If a compact summary is needed, label every row with its delivery window and futures month.

### 8.3 Social draft

Generate up to three variants from the same fact pack:

- **Snapshot:** one commodity, one delivery bucket, highest/low/range, data-as-of time.
- **Change:** one strict basis or cash change with buyer/location, delivery, futures month, and unit.
- **Coverage:** number of sources/locations updated plus a link to current bids.

Example structure:

```text
Eastern Ontario corn snapshot — October delivery

Listed range: {{ low }}–{{ high }} CAD/bu across {{ count }} posted bids.
Highest listed: {{ buyer_location }} at {{ high }} CAD/bu.

As of {{ timestamp }}. Before freight; verify current buyer terms.
{{ tracked_url }}
```

The social renderer enforces channel length but does not remove delivery, currency/unit, freshness, or freight disclosure to make the post fit. It shortens optional prose first.

### 8.4 Site update

The site artifact is a structured content block, not free-form HTML:

- title and slug;
- region and local publication date;
- data-as-of time;
- short neutral summary;
- fact-backed tables;
- methodology/limitation block;
- canonical URL and campaign parameters;
- JSON-LD fields only when supportable.

The site can render the same block as a daily market note or a weekly archive page. The initial engine stores it as a draft and does not deploy it.

## 9. Language-model boundary

An LLM is optional, not foundational. The smallest version should use deterministic templates. A later copy-polish step may be added under these restrictions:

- input contains only the approved fact pack, house style, and channel contract;
- output is validated JSON, never arbitrary HTML;
- each sentence containing a number must list one or more `fact_id` values;
- the model cannot add market causes, trading advice, unseen prices, or new calculations;
- unsupported claims, altered numbers, lost qualifiers, or missing disclosures block the artifact;
- invalid output falls back to the deterministic template instead of retrying indefinitely.

## 10. QA gates

### 10.1 Data gate

Block the affected section when any of the following applies:

- no canonical records;
- data older than the regional freshness threshold;
- source is candidate, quarantined, inactive, or below the chosen confidence threshold;
- currency or unit is unknown;
- delivery period is unresolved for a comparison;
- futures month is missing for a basis-change claim;
- prior record is not an exact comparable match;
- source/location coverage is below the regional minimum;
- numeric value is non-finite, outside a configured commodity sanity range, or materially inconsistent with source data.

### 10.2 Calculation gate

For each calculated claim:

- recompute from source rows;
- confirm all inputs share commodity, delivery bucket, currency, unit, and—when basis is involved—futures month;
- test `cash - futures = basis` within tolerance when the fields are available;
- confirm signed changes use current minus prior;
- confirm rankings use comparable records only;
- record the formula and input IDs.

### 10.3 Editorial gate

Block an artifact that:

- uses an untraceable number;
- says “best” without qualifying it as highest posted bid or calculating a freight-adjusted netback;
- omits delivery, currency/unit, data-as-of, or freight treatment;
- presents an estimate as verified;
- contains a buy/sell/hedge recommendation;
- attributes market causation without a cited context source;
- claims regional completeness when the coverage threshold was not met.

### 10.4 Publication gate

Initial allowed transition:

```text
generating -> qa_passed -> draft
generating -> warning -> draft_needs_review
generating -> qa_failed -> blocked
```

There is no automatic transition from `draft` to `approved`, `scheduled`, `sent`, or `published`. Any future approval endpoint must require an authenticated admin, log the approver and content hash, and reject an artifact if its facts have changed since review.

## 11. Storage schema and metadata

### 11.1 Initial table: `content_drafts`

Use one table in the first PR to keep the implementation small:

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `org_id` | UUID FK | Tenant ownership |
| `issue_key` | string | Idempotent key such as `eastern_ontario:daily:2026-07-14` |
| `region_key` | string | Stable configuration key |
| `region_name` | string | Display name at generation time |
| `cadence` | string | `daily` or `weekly` |
| `status` | string | `draft`, `draft_needs_review`, or `blocked` |
| `data_as_of` | timestamptz | Freshest included market row |
| `generated_at` | timestamptz | Draft generation time |
| `input_fingerprint` | string | Hash of sorted input row IDs, values, and template version |
| `fact_schema_version` | string | Fact-pack compatibility version |
| `template_version` | string | Renderer version |
| `facts_json` | JSONB | Immutable fact pack and lineage |
| `artifacts_json` | JSONB | Email text/HTML, social variants, and site block |
| `qa_json` | JSONB | Check results, warnings, failures, and coverage |
| `error_message` | text nullable | Generation failure summary |
| `created_at` | timestamptz | Audit timestamp |
| `updated_at` | timestamptz | Audit timestamp |

Add a unique constraint on `(org_id, issue_key, input_fingerprint)`. Rerunning unchanged inputs returns the existing draft. Changed inputs create a new version or replace only a still-unreviewed draft according to an explicit service rule; never silently mutate an approved artifact.

### 11.2 Later split, only when necessary

When approval and publishing are implemented, split channel artifacts into `content_artifacts` and publication attempts into `content_publications`. Record channel, rendered content, approval identity/time, content hash, destination ID, provider response, campaign parameters, and publish status. Reuse `market_report_deliveries` for subscriber email delivery rather than duplicating it.

## 12. Scheduling

Scheduling is region-local and ingestion-aware:

1. Scheduled ingestion completes.
2. Source-health and freshness checks settle.
3. A draft job runs once per eligible region, for example 16:30 local on weekdays and 17:00 local on Friday for the weekly issue.
4. The job acquires an idempotency lock for `region + cadence + local issue date`.
5. It generates the fact pack, runs QA, and saves the draft bundle.
6. It logs the outcome for the review queue and exits. It does not call SMTP or a publishing API.

If ingestion did not succeed, the scheduler may retry draft generation after 15, 30, and 60 minutes. It does not generate a seemingly current issue from stale data. Daylight-saving behavior uses the region's IANA timezone, not a fixed UTC offset.

Suggested commands:

```bash
# Generate today's drafts for all eligible regions; never sends.
python -m app.jobs.generate_content_drafts --cadence daily

# Generate one regional weekly draft for review; never sends.
python -m app.jobs.generate_content_drafts --cadence weekly --region eastern_ontario
```

Do not add `--send` or `--publish` to this job.

## 13. Repurposing workflow

1. Build one regional fact pack.
2. Select a weekly lead fact by deterministic editorial priority: adequate coverage, comparable delivery period, meaningful verified change, and no warnings.
3. Render the full email and site draft from all approved facts.
4. Render social variants from a subset of those same fact IDs.
5. Attach tracked URLs with channel-specific UTM values.
6. Show all artifacts together in the review queue so one correction can be applied to the shared fact/template layer.
7. When human approval exists in a later phase, approve each channel separately. Rejecting social copy must not discard the valid fact pack or email draft.

The system should not generate ten near-duplicate posts merely because it can. A practical starting cadence is one daily market snapshot draft and one weekly report package per active region, with two or three social variants available for selection.

## 14. Failure handling

| Failure | Engine response |
|---|---|
| No successful regional ingestion | Create a blocked issue with diagnostics; publish nothing |
| One commodity lacks coverage | Omit or block that section and mark the bundle `draft_needs_review` |
| Candidate/quarantined source appears | Exclude it and record the exclusion |
| Stale rows | Exclude them; block the issue if remaining coverage is insufficient |
| Currency/unit mismatch | Partition values; block any cross-partition comparison |
| Delivery/futures mismatch | Suppress the comparison and record failed QA |
| Basis identity fails tolerance | Suppress the basis claim and flag the source rows |
| Renderer exception | Preserve the fact pack, mark generation failed, retry at most twice |
| LLM invalid or unsupported output | Use deterministic fallback or block that artifact |
| Duplicate scheduler invocation | Return the existing draft using the issue key/fingerprint |
| Database unavailable | Fail without side effects; retry with bounded backoff |
| Draft becomes stale before review | Mark it stale; regenerate and require review of the new hash |

Operational alerts should identify region, cadence, issue key, failed gate, source IDs, and retry count. They should never include subscriber addresses or credentials.

## 15. Metrics

### 15.1 Data and reliability

- eligible/healthy sources by region;
- fresh canonical rows by commodity;
- locations and comparable delivery buckets covered;
- age of newest and oldest included rows;
- QA pass, warning, and block rate by reason;
- successful draft-generation rate and latency;
- duplicate runs safely suppressed;
- source facts excluded because of currency, delivery, futures, or freshness problems.

### 15.2 Editorial efficiency

- drafts generated by region and channel;
- time from ingestion success to draft ready;
- human review time;
- approval, revision, and rejection rates;
- percentage of sentences or facts manually changed;
- deterministic fallback rate if an LLM is later added;
- content reused across email, site, and social without numeric divergence.

### 15.3 Business outcomes

After publishing is intentionally enabled, track:

- newsletter signup conversion by region and acquisition channel;
- open, click, bounce, unsubscribe, and spam-complaint rates;
- visits from each content artifact to current bids;
- returning visitors and regional watchlist/alert creation;
- consulting or software leads attributed to content;
- qualified lead and paid-customer conversion, not just impressions;
- revenue or pipeline value by regional content cohort.

Metrics must not influence market facts. Low engagement can change format or cadence, but it cannot justify more sensational claims.

## 16. Smallest next implementation PR

Title: **Persist QA-gated multi-channel content drafts**

This PR should create reviewable draft bundles from existing data and stop there.

### Scope

1. Add `ContentDraft` and one Alembic migration for the `content_drafts` table above.
2. Add `app/services/content_engine.py` containing:
   - region/cadence input selection;
   - deterministic fact-pack construction;
   - exact-comparison and freshness QA;
   - deterministic email, social, and site renderers;
   - input fingerprinting and idempotent persistence.
3. Reuse or extract safe helpers from `market_report.py`; do not create a second newsletter delivery path.
4. Add `app/jobs/generate_content_drafts.py` with `--cadence` and optional `--region`. The command has no send or publish mode.
5. Add an authenticated read-only endpoint:
   - `GET /api/content-drafts`
   - `GET /api/content-drafts/{id}`
6. Add tests proving:
   - daily and weekly draft bundles are produced from canonical rows;
   - unrelated delivery periods are not ranked as directly comparable;
   - strict basis changes require matching delivery and futures month;
   - currency/unit mismatch blocks comparisons;
   - freshness and minimum coverage gates work;
   - every numeric rendered claim has fact lineage;
   - rerunning identical inputs is idempotent;
   - all saved artifacts are drafts or blocked;
   - no SMTP or external publisher is called.

### Explicitly out of scope

- LLM-generated commentary;
- email sending;
- social API credentials or publishing;
- automatic site deployment;
- subscriber segmentation;
- new scraping or candidate-source activation;
- live futures, FX, freight, or news integrations;
- autonomous trading recommendations.

### Acceptance criteria

The PR is complete when a successful ingestion dataset can produce one persisted Eastern Ontario daily or weekly draft bundle, the bundle shows its facts and QA report through the read-only API, repeated runs do not duplicate unchanged content, and no execution path can send or publish it.

## 17. Following tracks

After the draft-engine PR is proven, the business build can progress in parallel without weakening data controls:

- **Regional data track:** promote a tiny set of candidate US sources, measure quality, and map region/currency/timezone metadata.
- **Review product track:** add an internal draft queue with approve, revise, reject, and stale-content handling.
- **Audience track:** add regional preferences to newsletter signup and content archive landing pages.
- **Distribution track:** connect email first, still requiring issue approval; add social/site adapters only after audit logs and per-channel approval exist.
- **Commercial track:** use the regional reports as proof for paid custom market reports, branded data feeds, and consulting deliverables.
- **Intelligence track:** add verified futures, FX, and freight inputs so GrainBids can move from posted-bid snapshots toward defensible basis and delivered-netback analysis.

The order within each track can vary, but the trust boundary does not: autonomous collection and drafting may expand quickly; autonomous external publication waits until approval, audit, and rollback controls are proven.
