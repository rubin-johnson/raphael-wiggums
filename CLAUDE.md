# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project: Sir Wiggums

CLI tool that converts raw notes into dependency-ordered implementation stories (`wiggums generate`) and executes them autonomously using Claude Code agents (`wiggums execute`). Plan quality can be evaluated with `wiggums review`.

---

## Documentation Rule

**Always update README.md when you change the CLI interface, add a command, change an option name, or add a feature users interact with.**

Specifically, before committing any change to `wiggums.py`, `execute/supervisor.py`, or any module that changes observable behavior: read `README.md`, identify what is now stale, and update it in the same commit.

---

## Architecture

```
[Raw notes / text]
       ↓
  wiggums generate   →  features/plan.md  (two-stage LLM: notes → PRD → stories)
       ↓
  wiggums review     →  feedback + optional rewrite (LLM evaluates story quality)
       ↓
  wiggums execute    →  runs stories as parallel Claude Code agents
       ↓
  [Target repo with all stories merged to main]
```

### Key modules

| Module | Purpose |
|--------|---------|
| `wiggums.py` | Click CLI entry point |
| `generate/prd.py` | Two-stage LLM pipeline (notes → PRD → stories) |
| `execute/state.py` | PlanState, StoryState, StoryCost — serialized to plan_state.json |
| `execute/supervisor.py` | Async orchestrator — parallel scheduling, retry, merge |
| `execute/runner.py` | Invokes `claude --print` subprocess per story, parses cost |
| `execute/cost.py` | Model escalation schedule (parse_escalation, model_for_attempt) |
| `execute/git.py` | Worktree creation, branch merge, conflict detection |
| `execute/wiggum_log.py` | Per-story log files, status.json, run.log |
| `review/reviewer.py` | Build review prompt, extract rewrite block, summarize state |

### Story format

- `## STORY-xxx — Title` headers (parsed by `execute/parser.py`)
- `### Dependencies` section: `- STORY-001 must be complete.` or `- None.`
- Each story completable in one Claude Code context window

### Model escalation

`--model-escalation "sonnet:3,opus:2"` means: try up to 3 times on sonnet, then escalate to opus for up to 2 more attempts. Parsed by `execute/cost.py`.

### Parallelism

Uses `asyncio.wait(FIRST_COMPLETED)` + a `tasked_ids` set. Stories unlock as soon as their dependencies complete — does not wait for the full batch. Git worktrees provide file isolation between concurrent agents.

---

## Core Concepts

### Story Constraints
- Each story must be completeable in a **single Claude Code context window**
- Dependencies must be resolved before the story that requires them
- Every story needs explicit **acceptance criteria**

### Key Terms
- **PRD**: Product Requirements Document — structured spec that precedes story generation
- **plan_state.json**: Persisted execution state alongside plan.md — enables resume after interruption
- **escalation**: Model retry schedule — cheap models first, escalate on failure

---

## Testing

```bash
uv run pytest          # full suite
uv run pytest -x -q    # fail-fast
```

100% coverage required. Never weaken or delete a failing test.

### Smoke tests

`tests/test_smoke.py` invokes the CLI via real subprocess calls with a fake `claude` binary in PATH. These tests catch wiring failures, stale option names, and import errors that unit tests miss.

**Always add a smoke test when you add a CLI command or option.** If a human couldn't run the command successfully, the smoke test should catch it.
