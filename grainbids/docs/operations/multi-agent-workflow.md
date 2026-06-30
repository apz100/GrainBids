# GrainBids Multi-Agent Workflow

Use this when multiple coding agents, reviews, or autonomous passes are working on the same repo. The goal is to keep parallel work isolated, reviewable, and easy to merge.

## Operating Rules

1. One task = one branch = one worktree.
2. Never let two agents edit the same files at the same time.
3. Every task starts with a short task file, not with memory.
4. The reviewer reads the diff and test results, not the whole repo.
5. The builder does not merge their own code without review.
6. Keep changes small enough to reason about in one pass.
7. Use the queue scripts for state changes; use chat threads for implementation and review only.

## Recommended Roles

### Planner
- Defines the objective.
- Lists the exact files or modules likely to change.
- Writes acceptance criteria and test expectations.
- Flags any risky assumptions up front.

### Builder
- Works in an isolated git worktree.
- Makes the smallest coherent change set.
- Runs the relevant tests locally.
- Updates the task file with what changed and what still needs review.

### Reviewer
- Checks the diff against the task file.
- Verifies tests and edge cases.
- Looks for regressions, stale assumptions, and hidden coupling.
- Sends back a precise fix list if anything is off.

## Hybrid Operating Model

This is the recommended default for GrainBids when you want as much automation as possible without losing review discipline.

### Coordinator thread
- Owns `ROADMAP.md`, task-file creation, task ordering, and final merge decisions.
- Picks the next ready task from the roadmap or queue.
- Renames or archives worker and reviewer threads so the sidebar stays readable.
- Never edits implementation files while a worker task is active.

### Queue scripts
- `enqueue-agent-task.ps1` creates the task record.
- `start-next-agent-task.ps1` advances the next queued task into a worktree.
- `start-agent-task.ps1` starts one specific task.
- `review-agent-task.ps1` moves a completed implementation into review.
- `prepare-agent-merge.ps1` handles the approved merge path.
- `close-agent-task.ps1` finalizes the task once merged.

### Chat threads
- Use one worker thread per task implementation.
- Use one reviewer thread per completed worker branch.
- Keep only the active pair visible when working from mobile.
- Archive or rename completed threads instead of leaving many similarly named chats open.

### Recommended cycle
1. Update the task file and ensure the roadmap still orders it correctly.
2. Queue the task with `enqueue-agent-task.ps1`.
3. Start the worker from the queue or with `start-agent-task.ps1`.
4. Read the worker report, commit hash, and changed files.
5. Create or update the reviewer thread with the actual worker commit hash.
6. Approve or reject based on the committed diff only.
7. Run `prepare-agent-merge.ps1` and then `close-agent-task.ps1` after approval.

### Mobile-friendly rule
- If a task is done, archive it.
- If a task is active, keep its worker and reviewer threads named consistently.
- Avoid maintaining multiple active threads for the same task unless one is blocked and the duplicate is explicitly intentional.

## Task File Format

Store the task in a file named `TASK.md` at the worktree root.

Minimum contents:
- Objective
- Background
- Scope
- Files likely to change
- Constraints
- Acceptance criteria
- Tests to run
- Test command
- Open questions

Use the template in `TASK.template.md`.

If you want the workflow to be machine-readable, use the queue scripts and folder structure under `.agent/queue/`.

## Suggested Branch Naming

- `agent/<short-slug>`
- `fix/<short-slug>`
- `feature/<short-slug>`

Keep the branch name short and obvious.

## Suggested Worktree Layout

Create worktrees under:

`<repo-root>/.worktrees/<short-slug>`

That keeps parallel work out of the main checkout and makes cleanup easy.

Queue files live under:

`<repo-root>/.agent/queue/<state>/`

Recommended scripts:
- `infra/scripts/enqueue-agent-task.ps1`
- `infra/scripts/start-next-agent-task.ps1`
- `infra/scripts/start-agent-task.ps1`
- `infra/scripts/review-agent-task.ps1`
- `infra/scripts/prepare-agent-merge.ps1`
- `infra/scripts/close-agent-task.ps1`
- `infra/scripts/list-agent-tasks.ps1`
- `infra/scripts/verify-agent-queue.ps1`
- `infra/scripts/watch-agent-queue.ps1`

## Suggested Process

1. Planner writes `TASK.md`.
2. Builder creates a fresh worktree and branch.
3. Builder implements the change and runs targeted tests.
4. Reviewer checks the diff and test output.
5. If needed, Builder makes one follow-up pass.
6. When approved, run merge prep and then merge into the main branch.

## What To Avoid

- Editing the main checkout while a parallel task is in flight.
- Mixing unrelated fixes into the same branch.
- Letting an agent continue from memory without a task file.
- Broad refactors when the task is a small bug fix.
- Running review and implementation from the same branch without a clean diff boundary.

## Practical Use With GrainBids

Good split examples:
- API endpoint work in one worktree
- frontend table changes in another worktree
- ingestion/data fixes in a third worktree

Bad split examples:
- two agents both editing `apps/api/app/services/upload_csv.py`
- one agent changing frontend filters while another changes the same filter contract in the API


