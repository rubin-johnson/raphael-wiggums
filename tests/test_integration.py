"""
Integration test: runs the executor against a minimal fake plan with mocked
agent launches. Verifies the full loop: parse → launch → merge → complete.
"""
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch
from execute.state import PlanState, StoryStatus
from execute.supervisor import Supervisor
from execute.runner import AgentResult

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


def make_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "README.md").write_text("# Repo\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


async def test_full_loop_two_dependent_stories(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()
    make_git_repo(repo)

    state = PlanState.from_plan(plan)
    execution_order = []

    async def mock_launch(story_id, story, attempt):
        execution_order.append(story_id)
        branch = f"{story_id.lower()}-attempt-{attempt}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
        (repo / f"{story_id}.txt").write_text("done")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", f"feat: {story_id}"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
        return AgentResult(
            story_id=story_id,
            stdout=f"STORY_COMPLETE: {story_id}",
            stderr="", exit_code=0,
            worktree_path=str(repo), branch=branch,
        )

    sup = Supervisor(state, plan, repo, max_concurrent=3, max_retries=3)
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        await sup.run()

    assert state.stories["STORY-001"].status == StoryStatus.COMPLETED
    assert state.stories["STORY-002"].status == StoryStatus.COMPLETED
    # STORY-001 must run before STORY-002 (dependency constraint)
    assert execution_order.index("STORY-001") < execution_order.index("STORY-002")


async def test_state_file_written_after_run(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()
    make_git_repo(repo)

    state = PlanState.from_plan(plan)

    async def mock_launch(story_id, story, attempt):
        branch = f"{story_id.lower()}-attempt-{attempt}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
        (repo / f"{story_id}.txt").write_text("done")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", f"feat: {story_id}"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
        return AgentResult(
            story_id=story_id, stdout=f"STORY_COMPLETE: {story_id}",
            stderr="", exit_code=0, worktree_path=str(repo), branch=branch,
        )

    sup = Supervisor(state, plan, repo, max_concurrent=3, max_retries=3)
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        await sup.run()

    state_file = plan.parent / "plan_state.json"
    assert state_file.exists()

    # Reload and verify
    state2 = PlanState.load(state_file, plan)
    assert state2.stories["STORY-001"].status == StoryStatus.COMPLETED
    assert state2.stories["STORY-002"].status == StoryStatus.COMPLETED


async def test_resumed_run_skips_completed_stories(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(MINIMAL_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()
    make_git_repo(repo)

    # Pre-mark STORY-001 as completed
    state = PlanState.from_plan(plan)
    state.mark_complete("STORY-001")
    state_file = plan.parent / "plan_state.json"
    state.save(state_file)

    launched = []

    # Reload state as the executor would
    state2 = PlanState.load(state_file, plan)

    async def mock_launch(story_id, story, attempt):
        launched.append(story_id)
        branch = f"{story_id.lower()}-attempt-{attempt}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
        (repo / f"{story_id}.txt").write_text("done")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", f"feat: {story_id}"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
        return AgentResult(
            story_id=story_id, stdout=f"STORY_COMPLETE: {story_id}",
            stderr="", exit_code=0, worktree_path=str(repo), branch=branch,
        )

    sup = Supervisor(state2, plan, repo, max_concurrent=3, max_retries=3)
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        await sup.run()

    # Only STORY-002 should have launched (STORY-001 already done)
    assert "STORY-001" not in launched
    assert "STORY-002" in launched
