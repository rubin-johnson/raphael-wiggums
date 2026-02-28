# Plan Review Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `wiggums review <plan_file>` that reads a plan.md + optional execution state, calls Claude to evaluate story quality and coverage, prints suggestions, and optionally rewrites the plan.

**Architecture:** New `review/` module with a single `run_review()` function. Reads plan.md (and plan_state.json if present), builds a review prompt, calls Claude, and prints structured feedback. With `--rewrite`, the LLM output replaces plan.md after user confirmation. Thin CLI command in wiggums.py delegates to this module.

**Tech Stack:** Click, anthropic SDK (via `claude --print`), existing `PlanState`, `generate/prd.py`'s `call_claude()`

---

### Task 1: Review prompt template

**Files:**
- Create: `prompts/review_plan.md`

**Step 1: Write the prompt file**

```markdown
You are reviewing an implementation plan for a software project.

## Plan Under Review

{plan}

## Execution State

{state_summary}

## Your Task

Evaluate the plan and return structured feedback covering:

1. **Story completeness** — does each story have acceptance criteria, unit tests, implementation notes, and explicit dependencies?
2. **Dependency correctness** — are dependencies listed in the right direction? Any cycles or missing dependencies?
3. **Story sizing** — are any stories too large to complete in a single Claude Code context window (~10k tokens of work)?
4. **Coverage gaps** — what important functionality is missing from the plan?
5. **Ordering** — given the dependencies, is the execution order sensible?

After the analysis, output:
- A numbered list of **issues found** (severity: HIGH / MEDIUM / LOW)
- A numbered list of **suggested improvements**
- If you were to rewrite this plan to fix the issues, output the full corrected plan.md between these exact markers:
  ```
  ===REWRITTEN_PLAN_START===
  <full corrected plan.md here>
  ===REWRITTEN_PLAN_END===
  ```
  Only include the rewrite block if significant changes are needed.
```

**Step 2: No test needed for a prompt file — commit directly**

```bash
git add prompts/review_plan.md
git commit -m "feat: add plan review prompt template"
```

---

### Task 2: Core review module

**Files:**
- Create: `review/__init__.py`
- Create: `review/reviewer.py`
- Test: `tests/test_reviewer.py`

**Step 1: Write the failing tests**

```python
# tests/test_reviewer.py
import pytest
from pathlib import Path
from review.reviewer import build_review_prompt, extract_rewritten_plan


def test_build_review_prompt_includes_plan_text(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary=None)
    assert "STORY-001" in prompt


def test_build_review_prompt_includes_state_when_provided(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary="1 completed, 0 failed")
    assert "1 completed" in prompt


def test_build_review_prompt_no_state_says_not_started(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary=None)
    assert "not started" in prompt.lower() or "no execution" in prompt.lower()


def test_extract_rewritten_plan_finds_block():
    raw = "Some feedback.\n===REWRITTEN_PLAN_START===\n# New Plan\n===REWRITTEN_PLAN_END==="
    result = extract_rewritten_plan(raw)
    assert result == "# New Plan"


def test_extract_rewritten_plan_returns_none_when_absent():
    raw = "Some feedback without a rewrite block."
    result = extract_rewritten_plan(raw)
    assert result is None


def test_extract_rewritten_plan_strips_whitespace():
    raw = "===REWRITTEN_PLAN_START===\n\n# Plan\n\n===REWRITTEN_PLAN_END==="
    result = extract_rewritten_plan(raw)
    assert result == "# Plan"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_reviewer.py -v
```
Expected: `ModuleNotFoundError: No module named 'review'`

**Step 3: Create the module**

```python
# review/__init__.py
# empty
```

```python
# review/reviewer.py
import re
from pathlib import Path
from typing import Optional

_PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "review_plan.md"
_START_MARKER = "===REWRITTEN_PLAN_START==="
_END_MARKER = "===REWRITTEN_PLAN_END==="


def build_review_prompt(plan_path: Path, state_summary: Optional[str]) -> str:
    template = _PROMPT_TEMPLATE.read_text()
    plan_text = plan_path.read_text()
    state_text = state_summary if state_summary else "No execution state — plan has not been run yet."
    return template.format(plan=plan_text, state_summary=state_text)


def extract_rewritten_plan(raw: str) -> Optional[str]:
    start = raw.find(_START_MARKER)
    end = raw.find(_END_MARKER)
    if start == -1 or end == -1:
        return None
    content = raw[start + len(_START_MARKER):end]
    return content.strip() or None
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_reviewer.py -v
```
Expected: 6 passed

**Step 5: Commit**

```bash
git add review/__init__.py review/reviewer.py tests/test_reviewer.py
git commit -m "feat: add review module with prompt builder and rewrite extractor"
```

---

### Task 3: State summary helper

**Files:**
- Modify: `review/reviewer.py`
- Modify: `tests/test_reviewer.py`

The review command needs to summarize `plan_state.json` into a short human-readable string. Add this to the reviewer module.

**Step 1: Write the failing tests** (add to `tests/test_reviewer.py`)

```python
from execute.state import PlanState, StoryStatus

def test_summarize_state_counts_statuses(tmp_path):
    from review.reviewer import summarize_state
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## STORY-001 — Foo\n\n### Dependencies\n- None.\n\n---\n\n"
        "## STORY-002 — Bar\n\n### Dependencies\n- None.\n"
    )
    state = PlanState.from_plan(plan)
    state.mark_complete("STORY-001")
    summary = summarize_state(state)
    assert "completed" in summary
    assert "pending" in summary


def test_summarize_state_includes_cost_when_nonzero(tmp_path):
    from review.reviewer import summarize_state
    from execute.state import StoryCost
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    state = PlanState.from_plan(plan)
    state.record_cost("STORY-001", StoryCost(cost_usd=0.05, model="sonnet", input_tokens=100, output_tokens=50))
    summary = summarize_state(state)
    assert "$0.05" in summary or "0.05" in summary
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_reviewer.py::test_summarize_state_counts_statuses tests/test_reviewer.py::test_summarize_state_includes_cost_when_nonzero -v
```
Expected: `ImportError: cannot import name 'summarize_state'`

**Step 3: Add `summarize_state` to `review/reviewer.py`**

```python
from execute.state import PlanState


def summarize_state(state: PlanState) -> str:
    from execute.state import StoryStatus
    counts: dict[str, int] = {}
    for s in state.stories.values():
        counts[s.status.value] = counts.get(s.status.value, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items()]
    summary = ", ".join(parts)
    total_cost = state.total_cost_usd()
    if total_cost:
        summary += f" | total cost so far: ${total_cost:.3f}"
    return summary
```

**Step 4: Run all reviewer tests**

```bash
uv run pytest tests/test_reviewer.py -v
```
Expected: 8 passed

**Step 5: Commit**

```bash
git add review/reviewer.py tests/test_reviewer.py
git commit -m "feat: add summarize_state helper for review command"
```

---

### Task 4: `wiggums review` CLI command

**Files:**
- Modify: `wiggums.py` (add `review` command)
- Test: `tests/test_review_cli.py`

**Step 1: Write the failing tests**

```python
# tests/test_review_cli.py
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from wiggums import cli

SIMPLE_PLAN = """## STORY-001 — Foo

### Dependencies
- None.
"""


def test_review_command_calls_claude_and_prints_output(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(SIMPLE_PLAN)

    runner = CliRunner()
    with patch("review.reviewer.call_claude", return_value="HIGH: Missing acceptance criteria.\nNo rewrite needed."):
        result = runner.invoke(cli, ["review", str(plan)])

    assert result.exit_code == 0
    assert "HIGH" in result.output


def test_review_command_loads_state_when_state_file_exists(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(SIMPLE_PLAN)
    from execute.state import PlanState
    state = PlanState.from_plan(plan)
    state.mark_complete("STORY-001")
    state.save(tmp_path / "plan_state.json")

    runner = CliRunner()
    with patch("review.reviewer.call_claude", return_value="MEDIUM: Plan looks mostly good.") as mock_call:
        result = runner.invoke(cli, ["review", str(plan)])

    assert result.exit_code == 0
    # State summary should appear in what was passed to claude
    prompt_arg = mock_call.call_args[0][0]
    assert "completed" in prompt_arg


def test_review_rewrite_flag_writes_new_plan(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(SIMPLE_PLAN)
    new_plan = "## STORY-001 — Foo (improved)\n\n### Dependencies\n- None.\n"
    llm_response = f"Feedback.\n===REWRITTEN_PLAN_START===\n{new_plan}\n===REWRITTEN_PLAN_END==="

    runner = CliRunner()
    with patch("review.reviewer.call_claude", return_value=llm_response):
        result = runner.invoke(cli, ["review", str(plan), "--rewrite"], input="y\n")

    assert result.exit_code == 0
    assert plan.read_text().strip() == new_plan.strip()


def test_review_rewrite_flag_does_not_write_when_user_declines(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(SIMPLE_PLAN)
    original = plan.read_text()
    new_plan = "## STORY-001 — Improved\n\n### Dependencies\n- None.\n"
    llm_response = f"Feedback.\n===REWRITTEN_PLAN_START===\n{new_plan}\n===REWRITTEN_PLAN_END==="

    runner = CliRunner()
    with patch("review.reviewer.call_claude", return_value=llm_response):
        result = runner.invoke(cli, ["review", str(plan), "--rewrite"], input="n\n")

    assert result.exit_code == 0
    assert plan.read_text() == original


def test_review_rewrite_flag_no_rewrite_block_says_so(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(SIMPLE_PLAN)

    runner = CliRunner()
    with patch("review.reviewer.call_claude", return_value="Looks great, no changes needed."):
        result = runner.invoke(cli, ["review", str(plan), "--rewrite"])

    assert result.exit_code == 0
    assert "no rewrite" in result.output.lower() or "not suggest" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_review_cli.py -v
```
Expected: `Error: No such command 'review'`

**Step 3: Add `review` command to `wiggums.py`**

Add after the `execute` command:

```python
@cli.command()
@click.argument("plan_file", type=click.Path(exists=True))
@click.option("--rewrite", is_flag=True, help="Apply LLM-suggested rewrite to plan file after confirmation")
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Claude model to use")
def review(plan_file, rewrite, model):
    """Evaluate a plan and suggest improvements."""
    from pathlib import Path
    from execute.state import PlanState
    from review.reviewer import build_review_prompt, extract_rewritten_plan, summarize_state
    from generate.prd import call_claude

    plan_path = Path(plan_file)
    state_file = plan_path.parent / "plan_state.json"

    state_summary = None
    if state_file.exists():
        state = PlanState.load(state_file, plan_path)
        state_summary = summarize_state(state)
        click.echo(f"Loaded execution state: {state_summary}")

    click.echo("Reviewing plan...")
    prompt = build_review_prompt(plan_path, state_summary)
    raw = call_claude(prompt, model=model)

    click.echo("\n" + raw)

    if rewrite:
        new_plan = extract_rewritten_plan(raw)
        if new_plan is None:
            click.echo("\nLLM did not suggest a rewrite.")
        else:
            click.echo("\n--- Proposed rewrite (first 500 chars) ---")
            click.echo(new_plan[:500] + ("..." if len(new_plan) > 500 else ""))
            if click.confirm("\nApply rewrite to plan file?"):
                plan_path.write_text(new_plan)
                click.echo(f"Plan updated: {plan_path}")
            else:
                click.echo("Rewrite discarded.")
```

Also add `import review.reviewer` is handled via inline imports — no top-level change needed.

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_review_cli.py -v
```
Expected: 5 passed

**Step 5: Run full suite**

```bash
uv run pytest --tb=short -q
```
Expected: all passing

**Step 6: Commit**

```bash
git add wiggums.py tests/test_review_cli.py
git commit -m "feat: add wiggums review command with optional --rewrite"
```

---

### Task 5: Fix `call_claude` import in reviewer tests

The tests in `test_review_cli.py` patch `review.reviewer.call_claude` but the actual import is from `generate.prd`. The review module needs to import `call_claude` directly so it can be patched cleanly.

**Files:**
- Modify: `review/reviewer.py`

**Step 1: Update reviewer to own its `call_claude` import**

Add to `review/reviewer.py` top-level:

```python
from generate.prd import call_claude

__all__ = ["build_review_prompt", "extract_rewritten_plan", "summarize_state", "call_claude"]
```

This makes `patch("review.reviewer.call_claude", ...)` work correctly in tests.

**Step 2: Run all tests**

```bash
uv run pytest --tb=short -q
```
Expected: all passing

**Step 3: Commit**

```bash
git add review/reviewer.py
git commit -m "fix: expose call_claude in review module for clean patching in tests"
```

---

## Notes

- `call_claude` lives in `generate/prd.py` — re-used here, not duplicated
- `--rewrite` requires explicit user confirmation (`click.confirm`) — no silent file modification
- State file is optional — review works on a fresh plan with no execution history
- The prompt template uses `{plan}` and `{state_summary}` placeholders — matches Python `.format()` call
