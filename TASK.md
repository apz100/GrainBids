# Regional Source Pilot Console

## Objective

Add a guarded admin workflow for inspecting one inactive regional source candidate before deciding whether to promote or quarantine it.

## Scope

- Add an admin-only `POST /api/sources/{id}/probe` endpoint.
- Probe only inactive candidates using target-aware adapters and approved US candidate URLs.
- Return a capped, sanitized preview and quality summary without persisting market data.
- Add Sources UI actions for importing candidates, probing one candidate, and confirming promotion or quarantine.
- Add mocked API coverage and verify focused backend tests plus the web production build.

## Constraints

- One source and one fetch attempt per probe.
- Use the adapter's existing timeout.
- Require the stored HTTPS URL to match the approved US candidate configuration.
- Never activate a source, change collection status, schedule polling, or persist `PriceSnapshot`/`NormalizedPrice` during probe.
- No batch probing and no live network probe runs during development or tests.
- Do not publish or merge this branch.

## Acceptance Criteria

- Unsupported, active, non-candidate, non-HTTPS, or unapproved sources are rejected clearly.
- Successful probes report columns, raw row count, required-field coverage, commodities, locations, pass/fail reasons, and a capped sanitized preview.
- Probe execution leaves the source and persisted market-data counts unchanged.
- Sources UI exposes import, geography/status, probe results, and confirmation-gated promote/quarantine controls.
- Existing candidate import and guarded lifecycle behavior remain intact.

## Tests

- Mock adapter fetches; never contact source websites.
- Cover probe eligibility, URL approval, successful summary, failed quality checks, and no-persistence behavior.
- Run focused API tests for source registry/orchestration/routes.
- Run the web production build.
