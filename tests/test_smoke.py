"""
Smoke tests: invoke wiggums via subprocess as a human would.

These tests exercise the full CLI wiring — entry point, option parsing, file I/O,
and observable output. They use a fake `claude` binary to avoid real API calls
while still running the actual code path from the command line.

If these fail, a real user cannot use the tool.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
RAPHAEL = [sys.executable, str(REPO_ROOT / "raphael.py")]

MINIMAL_PLAN = """\
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
"""


def run(args, cwd=None, env=None, input=None):
    return subprocess.run(
        RAPHAEL + args,
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env,
        input=input,
    )


def fake_claude_env(tmp_path, stdout: str) -> dict:
    """Return env with a fake 'claude' script that prints stdout and exits 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(f'#!/bin/sh\ncat << \'EOF\'\n{stdout}\nEOF\n')
    script.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return env


# ---------------------------------------------------------------------------
# Help text — catches wiring errors and stale option names before runtime
# ---------------------------------------------------------------------------

def test_help_lists_all_three_commands():
    result = run(["--help"])
    assert result.returncode == 0
    assert "generate" in result.stdout
    assert "execute" in result.stdout
    assert "review" in result.stdout


def test_generate_help_has_correct_options():
    result = run(["generate", "--help"])
    assert result.returncode == 0
    assert "--output" in result.stdout
    assert "--codebase" in result.stdout
    assert "--model" in result.stdout


def test_execute_help_has_correct_options():
    result = run(["execute", "--help"])
    assert result.returncode == 0
    assert "--model-escalation" in result.stdout
    assert "--max-concurrent" in result.stdout
    assert "--log-dir" in result.stdout
    assert "--budget-per-story" in result.stdout
    # old options that were removed — if these appear, the CLI is stale
    assert "--max-retries" not in result.stdout


def test_review_help_has_correct_options():
    result = run(["review", "--help"])
    assert result.returncode == 0
    assert "--rewrite" in result.stdout
    assert "--model" in result.stdout


def test_understand_help_has_correct_options():
    result = run(["understand", "--help"])
    assert result.returncode == 0
    assert "--map-model" in result.stdout
    assert "--reduce-escalation" in result.stdout


# ---------------------------------------------------------------------------
# generate: notes → plan file
# ---------------------------------------------------------------------------

def test_generate_creates_plan_file(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("Build a web scraper that saves pages to disk.")
    out = tmp_path / "plan.md"

    # Fake claude returns a minimal but parseable plan for both pipeline stages
    env = fake_claude_env(tmp_path, MINIMAL_PLAN)

    result = run(["generate", str(notes), "--output", str(out)], env=env)

    assert result.returncode == 0, result.stderr
    assert out.exists(), "plan.md was not created"
    content = out.read_text()
    assert "STORY-" in content or "BT-" in content


def test_generate_prints_path_to_plan(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("notes")
    out = tmp_path / "plan.md"
    env = fake_claude_env(tmp_path, MINIMAL_PLAN)

    result = run(["generate", str(notes), "--output", str(out)], env=env)

    assert result.returncode == 0, result.stderr
    assert str(out) in result.stdout


# ---------------------------------------------------------------------------
# review: reads plan, prints feedback
# ---------------------------------------------------------------------------

def test_review_prints_llm_output(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    env = fake_claude_env(tmp_path, "HIGH: Story lacks acceptance criteria.\nLooks fixable.")

    result = run(["review", str(plan)], env=env)

    assert result.returncode == 0, result.stderr
    assert "HIGH" in result.stdout


def test_review_loads_state_and_mentions_it(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    # Write a fake state file with STORY-001 completed
    state = {
        "stories": {
            "STORY-001": {
                "title": "Write a file",
                "status": "completed",
                "depends_on": [],
                "retry_count": 0,
                "retry_notes": [],
                "worktree_branch": None,
                "cost": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "model": ""},
            }
        }
    }
    (tmp_path / "plan_state.json").write_text(json.dumps(state))
    env = fake_claude_env(tmp_path, "MEDIUM: Consider adding more stories.")

    result = run(["review", str(plan)], env=env)

    assert result.returncode == 0, result.stderr
    assert "completed" in result.stdout.lower()


def test_review_rewrite_writes_plan_on_confirm(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    new_plan = "## STORY-001 — Improved\n\n### Dependencies\n- None.\n"
    response = f"Feedback.\n===REWRITTEN_PLAN_START===\n{new_plan}\n===REWRITTEN_PLAN_END==="
    env = fake_claude_env(tmp_path, response)

    result = run(["review", str(plan), "--rewrite"], env=env, input="y\n")

    assert result.returncode == 0, result.stderr
    assert plan.read_text().strip() == new_plan.strip()


def test_review_rewrite_does_not_write_on_decline(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    original = plan.read_text()
    new_plan = "## STORY-001 — Improved\n\n### Dependencies\n- None.\n"
    response = f"Feedback.\n===REWRITTEN_PLAN_START===\n{new_plan}\n===REWRITTEN_PLAN_END==="
    env = fake_claude_env(tmp_path, response)

    result = run(["review", str(plan), "--rewrite"], env=env, input="n\n")

    assert result.returncode == 0, result.stderr
    assert plan.read_text() == original
