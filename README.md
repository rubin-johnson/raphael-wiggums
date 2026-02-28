# Sir Wiggums

PRD-to-stories pipeline and autonomous story executor.

Three commands:
- `wiggums generate` — converts raw notes into an implementation plan
- `wiggums execute` — runs the plan autonomously using Claude Code agents
- `wiggums review` — evaluates a plan and suggests improvements

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

## Review a plan

```bash
# Get feedback on story quality, sizing, dependencies, coverage gaps
wiggums review features/plan.md

# Review + apply suggested rewrites (asks for confirmation before writing)
wiggums review features/plan.md --rewrite

# Review a partially-executed plan (loads plan_state.json automatically)
wiggums review features/plan.md

# Use Opus for deeper analysis
wiggums review features/plan.md --model opus
```

The review command reads `plan_state.json` alongside the plan if it exists,
so it knows which stories have already run and can factor in execution history.

## Execute a plan

```bash
# Default: run overnight, parallel where possible
wiggums execute features/plan.md /path/to/target/repo

# Limit concurrency (default 3)
wiggums execute features/plan.md /path/to/target/repo --max-concurrent 2

# Pause for approval before each story (interactive mode)
wiggums execute features/plan.md /path/to/target/repo --pause-between

# Model escalation: try sonnet 3 times, then opus 2 times per story
wiggums execute features/plan.md /path/to/target/repo --model-escalation "sonnet:3,opus:2"

# Cap spend per story
wiggums execute features/plan.md /path/to/target/repo --budget-per-story 2.00

# Write per-story logs and live status.json to a directory
wiggums execute features/plan.md /path/to/target/repo --log-dir /tmp/wiggums-logs
```

If interrupted (Ctrl-C), the executor finishes in-progress stories then stops cleanly.
Re-run the same command to resume — state is tracked in `features/plan_state.json`.
Completed stories are skipped automatically.

## Observability (headless runs)

With `--log-dir`:

```bash
# Watch live status
watch -n2 cat /tmp/wiggums-logs/status.json

# Tail a specific story's log
tail -f /tmp/wiggums-logs/STORY-001_attempt_1.log

# Follow the overall run log
tail -f /tmp/wiggums-logs/run.log
```

## Model escalation

`--model-escalation` controls retry behavior when a story needs multiple attempts:

```
sonnet:3        # Try up to 3 times on sonnet, then fail
sonnet:3,opus:2 # Try 3 times on sonnet, escalate to opus for 2 more attempts
opus:1          # Single attempt on opus only
```

Cheaper models run first. More capable models are reserved for stories that fail
initial attempts. Cost per story is tracked and shown in the final summary.

## How execution works

1. Stories with no unmet dependencies form the "ready set."
2. Up to `--max-concurrent` agents launch simultaneously, each in an isolated git
   worktree (so concurrent file writes never collide).
3. When a story finishes successfully, its branch merges back to main and dependent
   stories unlock immediately (no waiting for the whole batch).
4. If an agent exhausts its context window before finishing, it commits partial
   work and emits `STORY_RETRY_NEEDED`. A fresh agent starts with a carry-forward
   summary, using the next model in the escalation schedule.
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
