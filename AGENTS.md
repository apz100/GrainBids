# GrainBids agent operating instructions

## Start here

Before selecting work, read:

1. `docs/business/MASTER_EXECUTION_PLAN.md`
2. `docs/business/MASTER_BACKLOG.md`
3. Relevant task and architecture files under `docs/`

Use the personal skill `build-grainbids-business` for GrainBids planning, commercialization, autonomous continuation, and cross-track execution. Use `analyze-grain-merchandising` for grain pricing, basis, futures, FX, freight, netback, processing-margin, or market-content logic.

## Operating model

- Run at most three active tracks: revenue, product/data, and content/operations.
- Prefer work that supports a sellable result within 14 days.
- Use Eastern Ontario as the proof market, not the geographic ceiling.
- Favor B2B reports, intelligence, consulting, and automation before broad SaaS features.
- Do not build elevator-management modules unless paid demand validates them.
- Update `MASTER_BACKLOG.md` when work starts, completes, or becomes blocked.
- Continue to the next safe backlog item without waiting for another prompt.

## Autonomy boundaries

Codex may autonomously research, draft, code, test, document, create skills, and publish scoped draft pull requests.

Explicit authorization is required before:

- merging unless the current request clearly authorizes it;
- activating new scraping targets or polling load;
- sending email, outreach, proposals, or social posts;
- purchasing services or starting paid usage;
- using private employer/customer data outside its authorized purpose;
- destructive Git or production-data operations.

## Engineering workflow

- One coherent task per branch and draft pull request.
- Use isolated worktrees for parallel code tasks.
- Do not mix unrelated baseline repairs into a product change.
- Record acceptance criteria and tests before broad implementation.
- Verify local tests, remote file diffs, review comments, checks, and deployment previews.
- When a merge is authorized, use the expected head SHA and verify production afterward.
