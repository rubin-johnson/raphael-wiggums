# Sir Wiggums

PRD-to-stories pipeline and autonomous story executor.

Two commands:
- `wiggums generate` — converts raw notes into an implementation plan
- `wiggums execute` — runs the plan autonomously using Claude Code agents

## Setup

```bash
uv sync
```

Requires `claude` CLI installed and authenticated (`claude --version`).

## Generate a plan

```bash
# From raw notes
wiggums generate notes.md -o features/plan.md

# With existing codebase for context (better story quality)
wiggums generate notes.md -o features/plan.md --codebase /path/to/repo

# Use Opus for more careful PRD decomposition
wiggums generate notes.md -o features/plan.md --model opus
```

Review `features/plan.md` before executing. Edit it freely — the executor parses
the markdown structure, not the content.

## Execute a plan

```bash
# Default: run overnight, parallel where possible, 3 retries per story
wiggums execute features/plan.md /path/to/target/repo

# Limit concurrency (default 3)
wiggums execute features/plan.md /path/to/target/repo --max-concurrent 2

# Pause for approval before each story (interactive mode)
wiggums execute features/plan.md /path/to/target/repo --pause-between

# More retries for harder stories
wiggums execute features/plan.md /path/to/target/repo --max-retries 5

# Use Opus (better for complex implementation)
wiggums execute features/plan.md /path/to/target/repo --model opus

# Cap spend per story
wiggums execute features/plan.md /path/to/target/repo --budget-per-story 2.00
```

If interrupted, re-run the same command to resume — state is tracked in
`features/plan_state.json`. Completed stories are skipped automatically.

## How execution works

1. Stories with no unmet dependencies form the "ready set."
2. Up to `--max-concurrent` agents launch simultaneously, each in an isolated git
   worktree (so concurrent file writes never collide).
3. When an agent finishes with all tests passing, its branch merges back to main
   and dependent stories unlock.
4. If an agent exhausts its context window before finishing, it commits partial
   work and emits `STORY_RETRY_NEEDED`. The supervisor starts a fresh agent with
   a carry-forward summary of what was done, up to `--max-retries` times.
5. Merge conflicts are quarantined and flagged — the run continues with other stories.

## Story format

Key constraints:

- `## BT-xxx — Title` for behavioral tests (upfront, stub bodies)
- `## STORY-xxx — Title` for implementation stories
- `### Dependencies` section with exact syntax: `STORY-001 must be complete.` or `None.`
- Each story completable in one Claude Code context window (~20k tokens of work)
- Unit tests inline with each story

## Concurrency and repos

Each story gets its own git worktree inside the target repo (`.claude/worktrees/`).
No separate repo copies needed — git worktrees share the object store but have
isolated working directories.

Stories that edit the same files should have explicit dependencies to prevent
merge conflicts. The executor detects conflicts and quarantines them rather than
aborting the whole run.