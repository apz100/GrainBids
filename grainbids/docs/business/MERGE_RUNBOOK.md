# GrainBids pull-request merge runbook

Use this runbook whenever Codex prepares or merges GrainBids pull requests. A green preview is necessary, not sufficient.

## Standing authority

Codex may create branches, commits, tests, and draft pull requests autonomously. It must not merge a pull request, deploy production, activate a source, run a live source probe, or distribute content unless the user explicitly authorizes that action.

An instruction to merge one pull request authorizes only that pull request. Never infer approval for dependent or adjacent pull requests.

## Current dependency order

1. **PR #4 — business operating system:** documentation-only and independent of the product stack.
2. **PR #3 — regional source foundation:** required base for both product branches.
3. After #3 is merged, keep its branch until both children are retargeted:
   - retarget **PR #5 — pilot console** from `agent/regional-source-foundation` to `main`;
   - retarget **PR #6 — content draft engine** from `agent/regional-source-foundation` to `main`.
4. Recalculate each child diff and checks after retargeting. They are independent siblings; neither should be based on the other.
5. Merge #5 and #6 only with separate explicit authorization for each.
6. Delete a base branch only after every open child PR has been retargeted and verified.

## Pre-merge checklist

For the exact pull request being considered:

- Confirm title, base, head, draft state, head SHA, author, and dependency order.
- Confirm it is mergeable and not behind the intended base.
- Compare the base and head through GitHub; inspect the exact changed-file list, additions, and deletions.
- Check for accidental worktree files, secrets, generated files, unrelated changes, migration collisions, and overlapping files with sibling PRs.
- Read every unresolved review thread and requested change.
- Require all relevant CI and preview checks to pass on the current head SHA.
- Re-run focused local tests when code changed after the last recorded test run.
- For migrations, confirm there is one expected Alembic head and no revision-number collision.
- State known risks and what was not tested.
- Obtain explicit merge authorization naming the pull request.

If the head SHA changes after authorization, stop and obtain authorization again after reporting the new diff and checks.

## Merge execution

- Prefer GitHub's normal merge strategy unless the repository establishes another policy.
- Do not force-push, rewrite history, bypass protections, auto-merge additional PRs, or silently resolve conflicts.
- Merge one pull request at a time.
- Record the resulting merge commit SHA.
- Confirm the pull request is reported as merged.
- Pull or fetch the new `main` state before evaluating the next pull request.

## Post-merge verification

- Confirm the expected files exist on `main`.
- Confirm production checks/deployment complete successfully when the merge affects deployable code.
- Run a read-only smoke check appropriate to the change.
- Do not trigger migrations, jobs, probes, polling, publishing, or email delivery unless separately authorized.
- If a dependent PR remains open, retarget it, re-check its exact diff, and wait for new checks before proposing the next merge.

## Current special gates

- **PR #3:** source candidates remain inactive; merging does not authorize candidate import, probing, promotion, polling, or activation.
- **PR #5:** the UI requires a passing probe, but the server does not yet persist a probe receipt; do not describe it as a complete approval audit trail.
- **PR #6:** merging does not authorize running migration `0017` in production, executing the generation job, or publishing any draft.
- **Any outreach:** account research and draft messages are safe; resolving named recipients and sending require separate approval.

## Stop conditions

Do not merge when any of these is true:

- authorization is ambiguous or names a different pull request;
- the head SHA changed after approval;
- checks are pending, missing, or failing;
- GitHub reports a conflict or an unexpected base;
- the diff contains unrelated or unexplained files;
- a migration collides with another open change;
- the action would activate external collection, contact a person, publish content, spend money, or deploy beyond the authorized scope.
