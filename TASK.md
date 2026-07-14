# Task

## Objective

Create a durable GrainBids business operating system that lets Codex continue coordinated revenue, product/data, and content/operations work without relying on one conversation.

## Background

GrainBids already has a working site, bid-ingestion foundation, signup flow, guarded weekly report, and a draft regional-source foundation. The business needs revenue-first sequencing, reusable offers and proof assets, and explicit autonomy gates.

## Scope

- Repository-level agent instructions
- Master execution plan and backlog
- Services-first commercial offer
- Product roadmap after PR #3
- Content-engine specification
- Customer-facing proof templates
- Public-information prospect pipeline

## Constraints

- No source activation or live scraping
- No email, social, proposal, or outreach sending
- No paid-service activation
- No merge of PR #3
- No employer-confidential or customer-private data
- No broad elevator-management product scope

## Acceptance criteria

- A fresh agent can select the correct next work from repository files.
- Exactly three active tracks are visible with gates and next actions.
- Commercial packages, first-sale path, proof templates, and do-not-build rules are explicit.
- Product work is decomposed into small testable PRs.
- Content generation is fact-first, QA-gated, auditable, and draft-only.
- All Markdown passes `git diff --check`.

## Tests to run

- `git diff --check`
- Manual cross-check of active backlog items against branches and PRs
- Independent forward test of the `build-grainbids-business` skill

## Risks / follow-ups

- Proof templates require a verified production snapshot before they become customer-ready samples.
- Prospect hypotheses must be validated in discovery before customer-specific development.
- PR #3 merge and every live operational action remain separately gated.

## Handoff notes

Update `grainbids/docs/business/MASTER_BACKLOG.md` whenever an active task completes, blocks, or is replaced.
