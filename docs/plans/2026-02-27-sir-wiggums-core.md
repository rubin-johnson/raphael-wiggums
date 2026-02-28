# Sir Wiggums — Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-command CLI (`wiggums generate` and `wiggums execute`) that converts raw text notes into dependency-ordered implementation stories and then executes them autonomously using Claude Code, with parallel execution for independent stories and retry logic for context exhaustion.

**Architecture:** `generate` is a two-stage LLM pipeline (notes → PRD → stories); `execute` is a supervisor loop that topologically sorts stories, launches one Claude Code subprocess per ready story (each in its own git worktree), merges on success, and carries forward context on retry. State is tracked in `plan_state.json` alongside the human-readable `plan.md`.

**Tech Stack:** Python 3.13, uv/pyenv, Click (CLI), subprocess + asyncio (parallel agents), pytest, no external LLM SDK needed (uses `claude --print` CLI directly for generate; target repo uses its own SDK).

---

## Overview: Concurrency Model

Stories with no unmet dependencies form the "ready set." The executor launches one `claude --print --worktree --dangerously-skip-permissions` subprocess per ready story (capped at `--max-concurrent`, default 3). Each agent works in an isolated git worktree so file writes never collide.

When an agent exits:
1. Runner checks exit code and test output from the agent's log.
2. On success: merge the worktree branch back to main, mark story `completed` in `plan_state.json`, compute newly-unblocked stories, launch them.
3. On context exhaustion (agent exits with partial work): run retry logic — collect what was done, start a new agent with a carry-forward context file, increment retry counter.
4. On hard failure (tests failing, retry limit hit): mark story `failed`, log details, continue with other ready stories, report at end.

Merge conflicts are detected and quarantined — the story is marked `merge_conflict` and skipped. Human review required.

---

## Task 1: Project scaffold and CLI entry point

**Files:**
- Create: `wiggums.py`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/test_cli.py`

**Step 1: Initialize project with uv**

```bash
cd /home/rujohnson/code/personal/sir_wiggums
uv init --python 3.13
uv add click
uv add --dev pytest pytest-mock
```

**Step 2: Write failing test**

`tests/test_cli.py`:
```python
from click.testing import CliRunner
from wiggums import cli

def test_cli_has_generate_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "--help"])
    assert result.exit_code == 0

def test_cli_has_execute_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["execute", "--help"])
    assert result.exit_code == 0
```

**Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: ImportError or ModuleNotFoundError.

**Step 4: Write minimal implementation**

`wiggums.py`:
```python
import click

@click.group()
def cli():
    """Sir Wiggums — PRD-to-stories pipeline and executor."""
    pass

@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="features/plan.md", help="Output plan file")
@click.option("--codebase", "-c", type=click.Path(exists=True), help="Path to target codebase (optional)")
def generate(input_file, output, codebase):
    """Convert raw notes into an implementation plan."""
    click.echo(f"Generating plan from {input_file}...")

@cli.command()
@click.argument("plan_file", type=click.Path(exists=True), default="features/plan.md")
@click.option("--max-concurrent", default=3, help="Max parallel agents")
@click.option("--max-retries", default=3, help="Max retries per story on context exhaustion")
@click.option("--pause-between", is_flag=True, help="Pause for approval between stories")
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Claude model to use")
@click.option("--budget", default=None, type=float, help="Max spend in USD (passed to claude --max-budget-usd)")
def execute(plan_file, max_concurrent, max_retries, pause_between, model, budget):
    """Execute stories from a plan file using Claude Code agents."""
    click.echo(f"Executing plan: {plan_file}")

if __name__ == "__main__":
    cli()
```

**Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: 2 passed.

**Step 6: Commit**

```bash
git init
git add pyproject.toml wiggums.py tests/
git commit -m "feat: scaffold CLI with generate and execute commands"
```

---

## Task 2: Plan state model

Stories need to track status across retries and concurrent execution. `plan_state.json` is the source of truth; `plan.md` is human-readable and never modified by the executor.

**Files:**
- Create: `execute/state.py`
- Create: `tests/test_state.py`

**Step 1: Write failing tests**

`tests/test_state.py`:
```python
import json
from pathlib import Path
from execute.state import PlanState, StoryState, StoryStatus

def test_load_from_plan_md(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    assert len(state.stories) == 2
    assert "STORY-001" in state.stories
    assert "STORY-002" in state.stories

def test_dependency_parsing(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    assert state.stories["STORY-002"].depends_on == ["STORY-001"]
    assert state.stories["STORY-001"].depends_on == []

def test_ready_stories_are_dependency_free(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    ready = state.ready_stories()
    assert [s.id for s in ready] == ["STORY-001"]

def test_completing_story_unblocks_dependents(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    state.mark_complete("STORY-001")
    ready = state.ready_stories()
    assert [s.id for s in ready] == ["STORY-002"]

def test_state_persists_to_json(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state_file = tmp_path / "plan_state.json"
    state.save(state_file)
    loaded = json.loads(state_file.read_text())
    assert "STORY-001" in loaded["stories"]

def test_state_loads_from_json(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state_file = tmp_path / "plan_state.json"
    state.save(state_file)
    state2 = PlanState.load(state_file, plan)
    assert state2.stories["STORY-001"].status == StoryStatus.PENDING

def test_retry_count_increments(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state.record_retry("STORY-001", "Context exhausted after writing foo()")
    assert state.stories["STORY-001"].retry_count == 1
    assert len(state.stories["STORY-001"].retry_notes) == 1
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_state.py -v
```
Expected: ModuleNotFoundError for `execute.state`.

**Step 3: Implement**

```bash
mkdir execute && touch execute/__init__.py
```

`execute/state.py`:
```python
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class StoryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGE_CONFLICT = "merge_conflict"


@dataclass
class StoryState:
    id: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    status: StoryStatus = StoryStatus.PENDING
    retry_count: int = 0
    retry_notes: list[str] = field(default_factory=list)
    worktree_branch: Optional[str] = None

    def is_ready(self, completed_ids: set[str]) -> bool:
        return (
            self.status == StoryStatus.PENDING
            and all(dep in completed_ids for dep in self.depends_on)
        )


class PlanState:
    def __init__(self, stories: dict[str, StoryState]):
        self.stories = stories

    @classmethod
    def from_plan(cls, plan_path: Path) -> "PlanState":
        text = plan_path.read_text()
        stories: dict[str, StoryState] = {}

        # Find all story/BT headers: ## STORY-001 — Title or ## BT-001 — Title
        header_pattern = re.compile(r"^## ((?:STORY|BT)-\d+) — (.+)$", re.MULTILINE)
        dep_pattern = re.compile(r"- ((?:STORY|BT)-\d+) must be complete")

        # Split into sections per story
        sections = re.split(r"(?=^## (?:STORY|BT)-\d+)", text, flags=re.MULTILINE)

        for section in sections:
            m = header_pattern.match(section.strip())
            if not m:
                continue
            story_id = m.group(1)
            title = m.group(2).strip()

            # Extract dependencies section
            dep_section_match = re.search(
                r"### Dependencies\n(.*?)(?=\n###|\n---|\Z)", section, re.DOTALL
            )
            depends_on = []
            if dep_section_match:
                dep_text = dep_section_match.group(1)
                if "None" not in dep_text:
                    depends_on = dep_pattern.findall(dep_text)

            stories[story_id] = StoryState(
                id=story_id, title=title, depends_on=depends_on
            )

        return cls(stories)

    @classmethod
    def load(cls, state_file: Path, plan_path: Path) -> "PlanState":
        """Load persisted state, merging with current plan for any new stories."""
        base = cls.from_plan(plan_path)
        data = json.loads(state_file.read_text())
        for story_id, saved in data["stories"].items():
            if story_id in base.stories:
                s = base.stories[story_id]
                s.status = StoryStatus(saved["status"])
                s.retry_count = saved.get("retry_count", 0)
                s.retry_notes = saved.get("retry_notes", [])
                s.worktree_branch = saved.get("worktree_branch")
        return base

    def save(self, state_file: Path) -> None:
        data = {
            "stories": {
                sid: {
                    "title": s.title,
                    "status": s.status.value,
                    "depends_on": s.depends_on,
                    "retry_count": s.retry_count,
                    "retry_notes": s.retry_notes,
                    "worktree_branch": s.worktree_branch,
                }
                for sid, s in self.stories.items()
            }
        }
        state_file.write_text(json.dumps(data, indent=2))

    def completed_ids(self) -> set[str]:
        return {sid for sid, s in self.stories.items() if s.status == StoryStatus.COMPLETED}

    def ready_stories(self) -> list[StoryState]:
        done = self.completed_ids()
        running = {sid for sid, s in self.stories.items() if s.status == StoryStatus.RUNNING}
        return [
            s for s in self.stories.values()
            if s.is_ready(done) and s.id not in running
        ]

    def mark_complete(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.COMPLETED

    def mark_running(self, story_id: str, branch: str) -> None:
        s = self.stories[story_id]
        s.status = StoryStatus.RUNNING
        s.worktree_branch = branch

    def mark_failed(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.FAILED

    def mark_merge_conflict(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.MERGE_CONFLICT

    def record_retry(self, story_id: str, note: str) -> None:
        s = self.stories[story_id]
        s.status = StoryStatus.PENDING
        s.retry_count += 1
        s.retry_notes.append(note)

    def is_done(self) -> bool:
        return all(
            s.status in (StoryStatus.COMPLETED, StoryStatus.FAILED, StoryStatus.MERGE_CONFLICT)
            for s in self.stories.values()
        )

    def summary(self) -> str:
        counts = {}
        for s in self.stories.values():
            counts[s.status] = counts.get(s.status, 0) + 1
        parts = [f"{v} {k.value}" for k, v in counts.items()]
        return " | ".join(parts)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_state.py -v
```
Expected: all pass.

**Step 5: Commit**

```bash
git add execute/ tests/test_state.py
git commit -m "feat: plan state model with dependency resolution and retry tracking"
```

---

## Task 3: Story prompt builder

Each agent needs a focused prompt: the story text, the retry context (if any), and instructions to run tests and commit on success. This is a pure function — easy to test.

**Files:**
- Create: `execute/prompt.py`
- Create: `prompts/story_executor.md`
- Create: `tests/test_prompt.py`

**Step 1: Write failing tests**

`tests/test_prompt.py`:
```python
from execute.prompt import build_story_prompt
from execute.state import StoryState

def test_prompt_contains_story_text():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    story_text = "## STORY-001 — Foo\n\nDo the thing."
    prompt = build_story_prompt(story, story_text, retry_notes=[])
    assert "STORY-001" in prompt
    assert "Do the thing." in prompt

def test_prompt_contains_retry_context_when_present():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[], retry_count=1,
                       retry_notes=["Wrote foo() but tests still failing at line 42"])
    story_text = "## STORY-001 — Foo\n\nDo the thing."
    prompt = build_story_prompt(story, story_text, retry_notes=story.retry_notes)
    assert "PREVIOUS ATTEMPT" in prompt
    assert "line 42" in prompt

def test_prompt_no_retry_context_when_first_attempt():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    story_text = "## STORY-001 — Foo\n\nDo the thing."
    prompt = build_story_prompt(story, story_text, retry_notes=[])
    assert "PREVIOUS ATTEMPT" not in prompt

def test_prompt_contains_success_instructions():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo it.", retry_notes=[])
    assert "git commit" in prompt.lower() or "commit" in prompt.lower()
    assert "pytest" in prompt.lower() or "test" in prompt.lower()
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_prompt.py -v
```

**Step 3: Create prompt template**

`prompts/story_executor.md`:
```markdown
You are implementing a single story from an implementation plan. Your job is to complete
the story, make all tests pass, and commit the result. Do not move on to other stories.

## Your Story

{story_text}

## Success Criteria

1. All tests referenced in the acceptance criteria pass: `pytest tests/ -v`
2. No existing tests are broken.
3. You commit your changes with a message: `feat({story_id}): <brief description>`
4. You output the line `STORY_COMPLETE: {story_id}` as your final output.

## Failure Protocol

If you reach the end of your context before all tests pass:
1. Commit whatever working code you have: `git add -A && git commit -m "wip({story_id}): partial - context exhausted"`
2. Write a brief summary of what you completed and what remains.
3. Output the line `STORY_RETRY_NEEDED: {story_id}` followed by your summary.
4. Stop.

Do not fabricate test results. Do not mark anything complete unless `pytest` output shows it passing.
{retry_section}
```

**Step 4: Implement**

`execute/prompt.py`:
```python
from pathlib import Path
from execute.state import StoryState

TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "story_executor.md"


def build_story_prompt(story: StoryState, story_text: str, retry_notes: list[str]) -> str:
    template = TEMPLATE_PATH.read_text()

    retry_section = ""
    if retry_notes:
        notes_formatted = "\n".join(f"- {n}" for n in retry_notes)
        retry_section = f"""
## Previous Attempt Context

PREVIOUS ATTEMPT(S) left the following notes. Start from where they left off:

{notes_formatted}

The working tree may already have partial implementation from a previous attempt.
Check what exists before rewriting from scratch.
"""

    return template.format(
        story_id=story.id,
        story_text=story_text,
        retry_section=retry_section,
    )
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_prompt.py -v
```
Expected: all pass.

**Step 6: Commit**

```bash
git add execute/prompt.py prompts/ tests/test_prompt.py
git commit -m "feat: story prompt builder with retry context injection"
```

---

## Task 4: Story text extractor

Given a `plan.md`, extract the full markdown block for a specific story ID. Used by the prompt builder and the retry summarizer.

**Files:**
- Create: `execute/parser.py`
- Create: `tests/test_parser.py`

**Step 1: Write failing tests**

`tests/test_parser.py`:
```python
from execute.parser import extract_story_text, extract_all_story_ids

SAMPLE_PLAN = """
## Overview

Some intro text.

---

## BT-001 — Behavioral Tests: Foo

Content for BT-001.

### Dependencies
- None.

---

## STORY-001 — Bar

Content for STORY-001.

### Dependencies
- None.

---

## STORY-002 — Baz

Content for STORY-002.

### Dependencies
- STORY-001 must be complete.

---
"""

def test_extract_story_text_returns_correct_block():
    text = extract_story_text(SAMPLE_PLAN, "STORY-001")
    assert "## STORY-001 — Bar" in text
    assert "Content for STORY-001." in text

def test_extract_story_text_does_not_include_next_story():
    text = extract_story_text(SAMPLE_PLAN, "STORY-001")
    assert "STORY-002" not in text

def test_extract_bt_story():
    text = extract_story_text(SAMPLE_PLAN, "BT-001")
    assert "BT-001" in text
    assert "Content for BT-001." in text

def test_extract_nonexistent_story_raises():
    import pytest
    with pytest.raises(KeyError):
        extract_story_text(SAMPLE_PLAN, "STORY-999")

def test_extract_all_story_ids():
    ids = extract_all_story_ids(SAMPLE_PLAN)
    assert ids == ["BT-001", "STORY-001", "STORY-002"]
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_parser.py -v
```

**Step 3: Implement**

`execute/parser.py`:
```python
import re
from pathlib import Path


STORY_HEADER = re.compile(r"^## ((?:STORY|BT)-\d+) —", re.MULTILINE)


def extract_all_story_ids(plan_text: str) -> list[str]:
    return STORY_HEADER.findall(plan_text)


def extract_story_text(plan_text: str, story_id: str) -> str:
    """Extract the full markdown block for a story. Raises KeyError if not found."""
    # Find start position
    pattern = re.compile(rf"^## {re.escape(story_id)} —", re.MULTILINE)
    m = pattern.search(plan_text)
    if not m:
        raise KeyError(f"Story {story_id} not found in plan")

    start = m.start()

    # Find next story header or end of file
    remaining = plan_text[start:]
    next_story = STORY_HEADER.search(remaining, 1)  # start at 1 to skip current
    if next_story:
        return remaining[: next_story.start()].strip()
    return remaining.strip()
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_parser.py -v
```
Expected: all pass.

**Step 5: Commit**

```bash
git add execute/parser.py tests/test_parser.py
git commit -m "feat: story text extractor from plan.md"
```

---

## Task 5: Agent runner (single story)

Launches one `claude --print` subprocess for a story in a git worktree, captures output, detects success/retry-needed/failure signals.

**Files:**
- Create: `execute/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write failing tests**

`tests/test_runner.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from execute.runner import AgentResult, AgentOutcome, run_story_agent

def test_agent_result_detects_success():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Some output\nSTORY_COMPLETE: STORY-001\n",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.SUCCESS

def test_agent_result_detects_retry_needed():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Partial work done.\nSTORY_RETRY_NEEDED: STORY-001\nWrote foo() but bar() unfinished.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.RETRY_NEEDED

def test_agent_result_extracts_retry_summary():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Stuff.\nSTORY_RETRY_NEEDED: STORY-001\nfoo() done, bar() needs tests.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert "foo() done" in result.retry_summary

def test_agent_result_detects_hard_failure_on_nonzero_exit():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Something went wrong.",
        stderr="Error: API error",
        exit_code=1,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.HARD_FAILURE
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_runner.py -v
```

**Step 3: Implement**

`execute/runner.py`:
```python
import asyncio
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class AgentOutcome(str, Enum):
    SUCCESS = "success"
    RETRY_NEEDED = "retry_needed"
    HARD_FAILURE = "hard_failure"


@dataclass
class AgentResult:
    story_id: str
    stdout: str
    stderr: str
    exit_code: int
    worktree_path: str
    branch: str

    @property
    def outcome(self) -> AgentOutcome:
        if self.exit_code != 0:
            return AgentOutcome.HARD_FAILURE
        if f"STORY_COMPLETE: {self.story_id}" in self.stdout:
            return AgentOutcome.SUCCESS
        if f"STORY_RETRY_NEEDED: {self.story_id}" in self.stdout:
            return AgentOutcome.RETRY_NEEDED
        # No signal — treat as failure
        return AgentOutcome.HARD_FAILURE

    @property
    def retry_summary(self) -> str:
        marker = f"STORY_RETRY_NEEDED: {self.story_id}"
        idx = self.stdout.find(marker)
        if idx == -1:
            return ""
        return self.stdout[idx + len(marker):].strip()


def run_story_agent(
    story_id: str,
    prompt: str,
    target_repo: Path,
    attempt: int,
    model: str = "sonnet",
    budget: Optional[float] = None,
) -> AgentResult:
    """Launch a Claude Code agent for a story in a git worktree. Blocking."""
    branch = f"{story_id.lower().replace('-', '-')}-attempt-{attempt}"

    # Write prompt to a temp file so we can pipe it
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model", model,
        "--worktree", branch,
    ]
    if budget is not None:
        cmd += ["--max-budget-usd", str(budget)]

    # Pass the prompt via stdin
    with open(prompt_file) as stdin_f:
        proc = subprocess.run(
            cmd,
            stdin=stdin_f,
            capture_output=True,
            text=True,
            cwd=str(target_repo),
        )

    # Worktree will be created by claude inside target_repo/.claude/worktrees/
    worktree_path = str(target_repo / ".claude" / "worktrees" / branch)

    return AgentResult(
        story_id=story_id,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        worktree_path=worktree_path,
        branch=branch,
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_runner.py -v
```
Expected: all pass (no subprocess calls in these tests — they test the result object).

**Step 5: Commit**

```bash
git add execute/runner.py tests/test_runner.py
git commit -m "feat: agent runner with success/retry/failure signal detection"
```

---

## Task 6: Git merge helper

After an agent succeeds, its worktree branch must be merged back to main. This is the only place where concurrent agents could conflict.

**Files:**
- Create: `execute/git.py`
- Create: `tests/test_git.py`

**Step 1: Write failing tests**

`tests/test_git.py`:
```python
import subprocess
import pytest
from pathlib import Path
from execute.git import merge_worktree_branch, MergeResult

def make_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path

def test_merge_clean_branch_succeeds(tmp_path):
    repo = make_repo(tmp_path)
    # Create a branch with a new file
    subprocess.run(["git", "checkout", "-b", "story-001-attempt-1"], cwd=repo, check=True, capture_output=True)
    (repo / "new_file.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add file"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)

    result = merge_worktree_branch(repo, "story-001-attempt-1")
    assert result == MergeResult.SUCCESS
    assert (repo / "new_file.py").exists()

def test_merge_conflict_detected(tmp_path):
    repo = make_repo(tmp_path)
    # Create conflict: same file edited differently on branch vs main
    subprocess.run(["git", "checkout", "-b", "story-001-attempt-1"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Branch version\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "branch change"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Main version\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "main change"], cwd=repo, check=True, capture_output=True)

    result = merge_worktree_branch(repo, "story-001-attempt-1")
    assert result == MergeResult.CONFLICT
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_git.py -v
```

**Step 3: Implement**

`execute/git.py`:
```python
import subprocess
from enum import Enum
from pathlib import Path


class MergeResult(str, Enum):
    SUCCESS = "success"
    CONFLICT = "conflict"
    ERROR = "error"


def merge_worktree_branch(repo: Path, branch: str) -> MergeResult:
    """Merge branch into current branch (main). Returns result enum."""
    result = subprocess.run(
        ["git", "merge", "--no-ff", branch, "-m", f"merge: {branch}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return MergeResult.SUCCESS

    # Check if it's a conflict
    if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
        # Abort the merge to leave repo clean
        subprocess.run(["git", "merge", "--abort"], cwd=str(repo), capture_output=True)
        return MergeResult.CONFLICT

    return MergeResult.ERROR


def delete_branch(repo: Path, branch: str) -> None:
    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=str(repo),
        capture_output=True,
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_git.py -v
```
Expected: all pass.

**Step 5: Commit**

```bash
git add execute/git.py tests/test_git.py
git commit -m "feat: git merge helper with conflict detection"
```

---

## Task 7: Parallel execution supervisor

The main loop: topological sort → launch ready stories concurrently → handle results → repeat. Uses `asyncio` to manage concurrent subprocesses without blocking.

**Files:**
- Create: `execute/supervisor.py`
- Modify: `wiggums.py` (wire `execute` command to supervisor)
- Create: `tests/test_supervisor.py`

**Step 1: Write failing tests**

`tests/test_supervisor.py`:
```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from execute.state import PlanState, StoryStatus
from execute.supervisor import Supervisor

SIMPLE_PLAN = """
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
"""

def make_state(plan_text: str, tmp_path: Path) -> tuple[PlanState, Path]:
    plan = tmp_path / "plan.md"
    plan.write_text(plan_text)
    return PlanState.from_plan(plan), plan

@pytest.mark.asyncio
async def test_supervisor_runs_independent_stories_first(tmp_path):
    state, plan = make_state(SIMPLE_PLAN, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    launched = []

    async def mock_launch(story_id, *args, **kwargs):
        launched.append(story_id)
        # Simulate success
        from execute.runner import AgentResult, AgentOutcome
        return AgentResult(
            story_id=story_id,
            stdout=f"STORY_COMPLETE: {story_id}",
            stderr="",
            exit_code=0,
            worktree_path=str(tmp_path),
            branch=f"{story_id}-attempt-1",
        )

    sup = Supervisor(state, plan, repo, max_concurrent=3, max_retries=3, model="sonnet")
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        with patch("execute.git.merge_worktree_branch", return_value="success"):
            await sup.run()

    assert launched[0] == "STORY-001"
    assert "STORY-002" in launched

@pytest.mark.asyncio
async def test_supervisor_respects_max_concurrent(tmp_path):
    # 3 independent stories, max_concurrent=2 → only 2 launch initially
    plan_text = "\n\n".join([
        f"## STORY-00{i} — Story {i}\n\n### Dependencies\n- None."
        for i in range(1, 4)
    ])
    state, plan = make_state(plan_text, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    running_at_once = []
    current = []

    async def mock_launch(story_id, *args, **kwargs):
        current.append(story_id)
        running_at_once.append(len(current))
        await asyncio.sleep(0.01)  # simulate work
        current.remove(story_id)
        from execute.runner import AgentResult
        return AgentResult(
            story_id=story_id, stdout=f"STORY_COMPLETE: {story_id}",
            stderr="", exit_code=0, worktree_path="", branch="",
        )

    import asyncio
    sup = Supervisor(state, plan, repo, max_concurrent=2, max_retries=3, model="sonnet")
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        with patch("execute.git.merge_worktree_branch", return_value="success"):
            await sup.run()

    assert max(running_at_once) <= 2
```

**Step 2: Run to verify failure**

```bash
uv add --dev pytest-asyncio
uv run pytest tests/test_supervisor.py -v
```

**Step 3: Implement**

`execute/supervisor.py`:
```python
import asyncio
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from execute.state import PlanState, StoryState, StoryStatus
from execute.parser import extract_story_text
from execute.prompt import build_story_prompt
from execute.runner import run_story_agent, AgentResult, AgentOutcome
from execute import git as git_ops

console = Console()
log = logging.getLogger(__name__)


class Supervisor:
    def __init__(
        self,
        state: PlanState,
        plan_path: Path,
        target_repo: Path,
        max_concurrent: int = 3,
        max_retries: int = 3,
        pause_between: bool = False,
        model: str = "sonnet",
        budget_per_story: Optional[float] = None,
    ):
        self.state = state
        self.plan_path = plan_path
        self.plan_text = plan_path.read_text()
        self.target_repo = target_repo
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.pause_between = pause_between
        self.model = model
        self.budget_per_story = budget_per_story
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._state_file = plan_path.parent / "plan_state.json"

    async def run(self) -> None:
        console.rule("[bold blue]Sir Wiggums — Executor[/bold blue]")
        self._print_status()

        while not self.state.is_done():
            ready = self.state.ready_stories()
            if not ready:
                if any(s.status == StoryStatus.RUNNING for s in self.state.stories.values()):
                    await asyncio.sleep(2)
                    continue
                # Deadlock — no ready, no running
                console.print("[red]No stories ready and none running. Possible unresolvable dependency.[/red]")
                break

            tasks = [asyncio.create_task(self._run_story(s)) for s in ready]
            await asyncio.gather(*tasks)

        self._print_final_summary()

    async def _run_story(self, story: StoryState) -> None:
        async with self._semaphore:
            if self.pause_between:
                console.print(f"\n[yellow]Ready to run {story.id}: {story.title}[/yellow]")
                answer = console.input("  Start this story? [Y/n]: ").strip().lower()
                if answer == "n":
                    console.print(f"  [dim]Skipping {story.id}[/dim]")
                    return

            attempt = story.retry_count + 1
            branch = f"{story.id.lower()}-attempt-{attempt}"
            self.state.mark_running(story.id, branch)
            self.state.save(self._state_file)

            console.print(f"[green]→ Launching {story.id}[/green] (attempt {attempt})")

            result = await self._launch_agent(story.id, story, attempt)
            await self._handle_result(story, result)

    async def _launch_agent(self, story_id: str, story: StoryState, attempt: int) -> AgentResult:
        loop = asyncio.get_event_loop()
        story_text = extract_story_text(self.plan_text, story_id)
        prompt = build_story_prompt(story, story_text, story.retry_notes)
        # run_story_agent is blocking — run in thread pool
        return await loop.run_in_executor(
            None,
            run_story_agent,
            story_id, prompt, self.target_repo, attempt, self.model, self.budget_per_story,
        )

    async def _handle_result(self, story: StoryState, result: AgentResult) -> None:
        if result.outcome == AgentOutcome.SUCCESS:
            merge_result = git_ops.merge_worktree_branch(self.target_repo, result.branch)
            if merge_result == git_ops.MergeResult.SUCCESS:
                self.state.mark_complete(story.id)
                console.print(f"[bold green]✓ {story.id} complete[/bold green]")
                git_ops.delete_branch(self.target_repo, result.branch)
            else:
                self.state.mark_merge_conflict(story.id)
                console.print(f"[red]✗ {story.id} merge conflict — manual review needed[/red]")

        elif result.outcome == AgentOutcome.RETRY_NEEDED:
            if story.retry_count < self.max_retries:
                note = result.retry_summary or "No summary provided by agent."
                self.state.record_retry(story.id, note)
                console.print(f"[yellow]↻ {story.id} retry {story.retry_count}/{self.max_retries}[/yellow]")
            else:
                self.state.mark_failed(story.id)
                console.print(f"[red]✗ {story.id} failed — retry limit reached[/red]")

        else:
            self.state.mark_failed(story.id)
            console.print(f"[red]✗ {story.id} hard failure[/red]")
            if result.stderr:
                console.print(f"[dim]{result.stderr[:500]}[/dim]")

        self.state.save(self._state_file)
        self._print_status()

    def _print_status(self) -> None:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Story")
        table.add_column("Status")
        table.add_column("Retries")
        for sid, s in self.state.stories.items():
            color = {
                StoryStatus.PENDING: "white",
                StoryStatus.RUNNING: "yellow",
                StoryStatus.COMPLETED: "green",
                StoryStatus.FAILED: "red",
                StoryStatus.MERGE_CONFLICT: "magenta",
            }.get(s.status, "white")
            table.add_row(sid, f"[{color}]{s.status.value}[/{color}]", str(s.retry_count))
        console.print(table)

    def _print_final_summary(self) -> None:
        console.rule("[bold]Run Complete[/bold]")
        console.print(self.state.summary())
```

**Step 4: Add rich dependency**

```bash
uv add rich
```

**Step 5: Wire into CLI**

In `wiggums.py`, replace the `execute` command body:
```python
@cli.command()
@click.argument("plan_file", type=click.Path(exists=True), default="features/plan.md")
@click.argument("target_repo", type=click.Path(exists=True))
@click.option("--max-concurrent", default=3)
@click.option("--max-retries", default=3)
@click.option("--pause-between", is_flag=True)
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]))
@click.option("--budget-per-story", default=None, type=float)
def execute(plan_file, target_repo, max_concurrent, max_retries, pause_between, model, budget_per_story):
    """Execute stories from a plan file using Claude Code agents."""
    import asyncio
    from pathlib import Path
    from execute.state import PlanState
    from execute.supervisor import Supervisor

    plan_path = Path(plan_file)
    repo_path = Path(target_repo)
    state_file = plan_path.parent / "plan_state.json"

    if state_file.exists():
        state = PlanState.load(state_file, plan_path)
        click.echo("Resuming from existing state.")
    else:
        state = PlanState.from_plan(plan_path)

    sup = Supervisor(
        state=state,
        plan_path=plan_path,
        target_repo=repo_path,
        max_concurrent=max_concurrent,
        max_retries=max_retries,
        pause_between=pause_between,
        model=model,
        budget_per_story=budget_per_story,
    )
    asyncio.run(sup.run())
```

**Step 6: Run tests**

```bash
uv run pytest tests/test_supervisor.py -v
```
Expected: all pass.

**Step 7: Commit**

```bash
git add execute/supervisor.py wiggums.py tests/test_supervisor.py
git commit -m "feat: parallel execution supervisor with asyncio semaphore"
```

---

## Task 8: Generate command — PRD builder

Two-stage LLM pipeline: notes → PRD (structured spec), then PRD → stories (plan.md format). Uses `claude --print` so no SDK needed.

**Files:**
- Create: `generate/prd.py`
- Create: `generate/__init__.py`
- Create: `prompts/notes_to_prd.md`
- Create: `prompts/prd_to_stories.md`
- Create: `tests/test_generate.py`

**Step 1: Write failing tests**

`tests/test_generate.py`:
```python
from unittest.mock import patch
from pathlib import Path
from generate.prd import run_prd_pipeline

def test_prd_pipeline_calls_claude_twice(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("Build a thing that does stuff.")

    call_args = []

    def mock_claude(prompt: str, model: str) -> str:
        call_args.append(prompt)
        if len(call_args) == 1:
            return "# PRD\n\n## Goal\nBuild a thing.\n\n## Requirements\n- Do stuff."
        return "## STORY-001 — Do stuff\n\n### Dependencies\n- None.\n"

    with patch("generate.prd.call_claude", side_effect=mock_claude):
        result = run_prd_pipeline(notes, codebase=None, model="sonnet")

    assert len(call_args) == 2
    assert "STORY-001" in result

def test_prd_pipeline_injects_codebase_context(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("Add a feature.")
    codebase = tmp_path / "src"
    codebase.mkdir()
    (codebase / "main.py").write_text("def foo(): pass")

    injected_prompts = []

    def mock_claude(prompt: str, model: str) -> str:
        injected_prompts.append(prompt)
        return "# PRD\n\n## Goal\nThing.\n" if len(injected_prompts) == 1 else "## STORY-001\n\n### Dependencies\n- None.\n"

    with patch("generate.prd.call_claude", side_effect=mock_claude):
        run_prd_pipeline(notes, codebase=codebase, model="sonnet")

    # Codebase context should be in the second call (story generation)
    assert "main.py" in injected_prompts[1] or "foo" in injected_prompts[1]
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_generate.py -v
```

**Step 3: Create prompt templates**

`prompts/notes_to_prd.md`:
```markdown
You are a senior product engineer. Convert the following raw notes into a structured
Product Requirements Document (PRD).

The PRD must include:
1. **Goal** — One sentence describing what this builds and why.
2. **Background** — Why this is needed. What problem does it solve?
3. **Requirements** — Specific, testable requirements. Not vague goals.
4. **Out of scope** — What this explicitly does NOT do.
5. **Open questions** — Things that need decisions before implementation.
6. **Success criteria** — How will we know this is done?

Be specific. Remove ambiguity. If the notes mention something vague, flag it as an
open question rather than making an assumption.

## Raw Notes

{notes}
```

`prompts/prd_to_stories.md`:
```markdown
You are a senior engineer decomposing a PRD into implementation stories for an AI
coding agent. Each story will be executed by a Claude Code instance in a single
context window (~200k tokens, ~20k tokens of actual work budget per story).

## Output Format Rules

**CRITICAL: Match this format exactly.** The executor parses it programmatically.

```
## STORY-001 — Short title

### User story
As a [role], I want [feature] so that [benefit].

### Context
[Why this exists, what problem it solves, relevant existing code to be aware of.]

### Acceptance criteria
1. [Specific, testable criterion]
2. [Another criterion]

### Unit tests (in this story)
```python
def test_specific_behavior():
    # concrete test
    pass
```

### Implementation notes
- [Specific guidance, not vague suggestions]
- [Reference real function names, file paths, patterns from the codebase]

### Dependencies
- None.   ← or: "STORY-001 must be complete."
```

**Behavioral tests:** Write BT-xxx stories first for cross-cutting acceptance criteria.
They contain stub tests that pass only when dependent STORY-xxx stories are complete.

**Dependency ordering:** List stories in execution order. Put the dependency graph
and recommended execution order at the top of the output.

**Story sizing:** Each story should be doable in <100 lines of code + tests. If
larger, split it.

## PRD

{prd}

{codebase_context}
```

**Step 4: Implement**

```bash
mkdir generate && touch generate/__init__.py
```

`generate/prd.py`:
```python
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


NOTES_TO_PRD_PROMPT = Path(__file__).parent.parent / "prompts" / "notes_to_prd.md"
PRD_TO_STORIES_PROMPT = Path(__file__).parent.parent / "prompts" / "prd_to_stories.md"


def call_claude(prompt: str, model: str = "sonnet") -> str:
    """Call claude --print with a prompt string. Returns stdout."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    with open(prompt_file) as stdin_f:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "--dangerously-skip-permissions"],
            stdin=stdin_f,
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

    return result.stdout.strip()


def _build_codebase_context(codebase: Optional[Path]) -> str:
    if codebase is None:
        return ""

    context_parts = ["## Existing Codebase\n"]
    # Gather Python files, skip venv and __pycache__
    py_files = [
        f for f in codebase.rglob("*.py")
        if ".venv" not in str(f) and "__pycache__" not in str(f)
    ]
    for py_file in sorted(py_files)[:20]:  # cap at 20 files
        rel = py_file.relative_to(codebase)
        content = py_file.read_text()[:3000]  # cap per file
        context_parts.append(f"### `{rel}`\n```python\n{content}\n```\n")

    return "\n".join(context_parts)


def run_prd_pipeline(
    notes_path: Path,
    codebase: Optional[Path],
    model: str = "sonnet",
) -> str:
    """Two-stage pipeline: notes → PRD → stories. Returns plan.md content."""
    notes = notes_path.read_text()

    # Stage 1: notes → PRD
    notes_prompt_template = NOTES_TO_PRD_PROMPT.read_text()
    notes_prompt = notes_prompt_template.format(notes=notes)
    prd = call_claude(notes_prompt, model=model)

    # Stage 2: PRD → stories
    stories_prompt_template = PRD_TO_STORIES_PROMPT.read_text()
    codebase_context = _build_codebase_context(codebase)
    stories_prompt = stories_prompt_template.format(
        prd=prd,
        codebase_context=codebase_context,
    )
    stories = call_claude(stories_prompt, model=model)

    # Prepend standard header
    header = (
        "# Implementation Plan\n\n"
        "Generated by Sir Wiggums. Edit freely — the executor reads this file.\n\n"
        "---\n\n"
    )
    return header + stories
```

**Step 5: Wire into CLI**

In `wiggums.py`, replace the `generate` command body:
```python
@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="features/plan.md", show_default=True)
@click.option("--codebase", "-c", type=click.Path(exists=True), default=None)
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]))
def generate(input_file, output, codebase, model):
    """Convert raw notes into an implementation plan."""
    from pathlib import Path
    from generate.prd import run_prd_pipeline

    notes_path = Path(input_file)
    codebase_path = Path(codebase) if codebase else None
    output_path = Path(output)

    click.echo(f"Stage 1: Converting notes to PRD...")
    click.echo(f"Stage 2: Generating stories...")

    plan_md = run_prd_pipeline(notes_path, codebase=codebase_path, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(plan_md)
    click.echo(f"Plan written to {output_path}")
    click.echo(f"Review it, then run: wiggums execute {output_path} <target-repo>")
```

**Step 6: Run tests**

```bash
uv run pytest tests/test_generate.py -v
```
Expected: all pass.

**Step 7: Commit**

```bash
git add generate/ prompts/ tests/test_generate.py wiggums.py
git commit -m "feat: two-stage generate pipeline (notes → PRD → stories)"
```

---

## Task 9: Full integration test + README

Wire everything together with a smoke test against a tiny fake plan, and write a minimal README covering the two commands.

**Files:**
- Create: `tests/test_integration.py`
- Create: `README.md`

**Step 1: Write integration test**

`tests/test_integration.py`:
```python
"""
Integration test: runs the executor against a minimal fake plan
with a mock claude subprocess. Verifies the full loop: parse →
launch → merge → complete.
"""
import asyncio
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch
from execute.state import PlanState, StoryStatus
from execute.supervisor import Supervisor
from execute.runner import AgentResult, AgentOutcome

MINIMAL_PLAN = """# Test Plan

---

## STORY-001 — Write a file

### User story
As a dev, I want a file written.

### Acceptance criteria
1. `output.txt` exists.

### Unit tests (in this story)
```python
def test_output_exists(tmp_path):
    assert (tmp_path / "output.txt").exists()
```

### Implementation notes
- Write output.txt with content "hello".

### Dependencies
- None.

---

## STORY-002 — Read the file

### User story
As a dev, I want to read the file written in STORY-001.

### Acceptance criteria
1. Reading `output.txt` returns "hello".

### Unit tests (in this story)
```python
def test_read_output(tmp_path):
    assert (tmp_path / "output.txt").read_text() == "hello"
```

### Implementation notes
- Read output.txt.

### Dependencies
- STORY-001 must be complete.
"""

@pytest.mark.asyncio
async def test_full_loop_two_stories(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()
    # Initialize a real git repo so merge works
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    state = PlanState.from_plan(plan)
    execution_order = []

    async def mock_launch(story_id, story, attempt):
        execution_order.append(story_id)
        # Create and commit a file on a branch so merge has something to do
        branch = f"{story_id.lower()}-attempt-{attempt}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
        (repo / f"{story_id}.txt").write_text("done")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", f"feat: {story_id}"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
        return AgentResult(
            story_id=story_id,
            stdout=f"STORY_COMPLETE: {story_id}",
            stderr="",
            exit_code=0,
            worktree_path=str(repo),
            branch=branch,
        )

    sup = Supervisor(state, plan, repo, max_concurrent=3, max_retries=3)
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        await sup.run()

    assert state.stories["STORY-001"].status == StoryStatus.COMPLETED
    assert state.stories["STORY-002"].status == StoryStatus.COMPLETED
    assert execution_order[0] == "STORY-001"
    assert execution_order[1] == "STORY-002"
```

**Step 2: Run all tests**

```bash
uv run pytest tests/ -v
```
Expected: all pass.

**Step 3: Create README**

`README.md`:
```markdown
# Sir Wiggums

PRD-to-stories pipeline and autonomous story executor.

## Commands

### Generate a plan

```bash
wiggums generate notes.md -o features/plan.md
wiggums generate notes.md -o features/plan.md --codebase /path/to/repo  # with codebase context
```

Runs a two-stage LLM pipeline: raw notes → PRD → implementation stories.
Review `features/plan.md` before executing.

### Execute a plan

```bash
wiggums execute features/plan.md /path/to/target/repo
wiggums execute features/plan.md /path/to/target/repo --max-concurrent 2
wiggums execute features/plan.md /path/to/target/repo --pause-between    # manual approval per story
wiggums execute features/plan.md /path/to/target/repo --max-retries 5
wiggums execute features/plan.md /path/to/target/repo --model opus       # use Opus for hard stories
```

Runs stories in dependency order, parallel where possible. State is tracked in
`features/plan_state.json` — re-run the same command to resume after interruption.

## Setup

```bash
uv sync
```

Requires `claude` CLI installed and authenticated.

## Story format

See `4th_step/features/plan.md` for the canonical story format this tool produces.
Key constraints:
- Each story completable in one Claude Code context window
- BT-xxx behavioral tests written upfront
- STORY-xxx implementation stories with inline unit tests
- `### Dependencies` section uses exact format: `STORY-001 must be complete.`
```

**Step 4: Final test run**

```bash
uv run pytest tests/ -v --tb=short
```
Expected: all pass.

**Step 5: Commit**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: integration test and README"
```

---

## Implementation order

Tasks 1–6 have no blocking dependencies on each other after Task 1 (scaffold). Recommended order:

```
Task 1 (scaffold) → Tasks 2, 3, 4, 5, 6 in parallel → Task 7 (supervisor) → Task 8 (generate) → Task 9 (integration)
```

Tasks 2–6 can each be done independently since they're pure modules with no cross-imports until Task 7 assembles them.
