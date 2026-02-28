import asyncio
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch
from execute.state import PlanState, StoryStatus, StoryCost
from execute.supervisor import Supervisor
from execute.runner import AgentResult
from execute.cost import parse_escalation


def make_plan(tmp_path: Path, plan_text: str) -> tuple[PlanState, Path]:
    plan = tmp_path / "plan.md"
    plan.write_text(plan_text)
    return PlanState.from_plan(plan), plan


SIMPLE_PLAN = """
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
"""

PARALLEL_PLAN = "\n\n".join([
    f"## STORY-00{i} — Story {i}\n\n### Dependencies\n- None."
    for i in range(1, 4)
])


def make_result(story_id: str, outcome: str = "complete", attempt: int = 1, cost_usd: float = 0.0) -> AgentResult:
    if outcome == "complete":
        stdout = f"STORY_COMPLETE: {story_id}"
    elif outcome == "retry":
        stdout = f"STORY_RETRY_NEEDED: {story_id}\nPartial work done."
    else:
        stdout = "no signal"
    return AgentResult(
        story_id=story_id, stdout=stdout, stderr="", exit_code=0,
        worktree_path="", branch=f"{story_id}-attempt-{attempt}",
        cost=StoryCost(cost_usd=cost_usd, model="sonnet", input_tokens=100, output_tokens=50),
    )


async def _run_with_mock(state, plan, repo, mock_launch_fn, max_concurrent=3, escalation=None):
    sup = Supervisor(
        state, plan, repo, max_concurrent=max_concurrent,
        escalation=escalation or parse_escalation("sonnet:3"),
    )
    with patch.object(sup, "_launch_agent", side_effect=mock_launch_fn):
        with patch("execute.supervisor.git_ops.merge_worktree_branch", return_value="success"):
            with patch("execute.supervisor.git_ops.delete_branch"):
                await sup.run()
    return sup


async def test_supervisor_runs_dependency_free_story_first(tmp_path):
    state, plan = make_plan(tmp_path, SIMPLE_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()
    launched = []

    async def mock_launch(story_id, story, attempt, model):
        launched.append(story_id)
        return make_result(story_id)

    await _run_with_mock(state, plan, repo, mock_launch)
    assert launched[0] == "STORY-001"
    assert "STORY-002" in launched


async def test_supervisor_completes_all_stories(tmp_path):
    state, plan = make_plan(tmp_path, SIMPLE_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id)

    await _run_with_mock(state, plan, repo, mock_launch)
    assert state.stories["STORY-001"].status == StoryStatus.COMPLETED
    assert state.stories["STORY-002"].status == StoryStatus.COMPLETED


async def test_supervisor_respects_max_concurrent(tmp_path):
    state, plan = make_plan(tmp_path, PARALLEL_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()

    running_counts = []
    current: list[str] = []

    async def mock_launch(story_id, story, attempt, model):
        current.append(story_id)
        running_counts.append(len(current))
        await asyncio.sleep(0.05)
        current.remove(story_id)
        return make_result(story_id)

    await _run_with_mock(state, plan, repo, mock_launch, max_concurrent=2)
    assert max(running_counts) <= 2


async def test_parallel_execution_does_not_wait_for_all_before_launching_new(tmp_path):
    """
    STORY-001 and STORY-003 launch in parallel. STORY-002 depends only on STORY-001.
    When STORY-001 finishes, STORY-002 should start while STORY-003 is still running.
    """
    plan_text = """
## STORY-001 — Fast

### Dependencies
- None.

---

## STORY-002 — Depends on 001

### Dependencies
- STORY-001 must be complete.

---

## STORY-003 — Slow independent

### Dependencies
- None.
"""
    state, plan = make_plan(tmp_path, plan_text)
    repo = tmp_path / "repo"
    repo.mkdir()

    launch_times: dict[str, float] = {}
    complete_times: dict[str, float] = {}

    async def mock_launch(story_id, story, attempt, model):
        launch_times[story_id] = asyncio.get_event_loop().time()
        if story_id == "STORY-003":
            await asyncio.sleep(0.2)
        else:
            await asyncio.sleep(0.02)
        complete_times[story_id] = asyncio.get_event_loop().time()
        return make_result(story_id)

    await _run_with_mock(state, plan, repo, mock_launch, max_concurrent=3)

    assert launch_times["STORY-002"] >= complete_times["STORY-001"]
    assert launch_times["STORY-002"] < complete_times["STORY-003"]


async def test_supervisor_retries_on_retry_needed(tmp_path):
    state, plan = make_plan(tmp_path, """
## STORY-001 — Foo

### Dependencies
- None.
""")
    repo = tmp_path / "repo"
    repo.mkdir()
    call_count = [0]

    async def mock_launch(story_id, story, attempt, model):
        call_count[0] += 1
        if call_count[0] == 1:
            return make_result(story_id, outcome="retry", attempt=1)
        return make_result(story_id, attempt=2)

    await _run_with_mock(state, plan, repo, mock_launch)
    assert call_count[0] == 2
    assert state.stories["STORY-001"].status == StoryStatus.COMPLETED
    assert state.stories["STORY-001"].retry_count == 1


async def test_model_escalation_switches_after_sonnet_exhausted(tmp_path):
    state, plan = make_plan(tmp_path, """
## STORY-001 — Foo

### Dependencies
- None.
""")
    repo = tmp_path / "repo"
    repo.mkdir()
    call_count = [0]

    async def mock_launch(story_id, story, attempt, model):
        call_count[0] += 1
        if call_count[0] < 3:
            return make_result(story_id, outcome="retry", attempt=call_count[0])
        return make_result(story_id, attempt=call_count[0])

    escalation = parse_escalation("sonnet:2,opus:2")
    await _run_with_mock(state, plan, repo, mock_launch, escalation=escalation)
    assert state.stories["STORY-001"].status == StoryStatus.COMPLETED


async def test_supervisor_marks_failed_after_all_tiers_exhausted(tmp_path):
    state, plan = make_plan(tmp_path, """
## STORY-001 — Foo

### Dependencies
- None.
""")
    repo = tmp_path / "repo"
    repo.mkdir()

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id, outcome="retry", attempt=attempt)

    escalation = parse_escalation("sonnet:2,opus:1")
    await _run_with_mock(state, plan, repo, mock_launch, escalation=escalation)
    assert state.stories["STORY-001"].status == StoryStatus.FAILED


async def test_supervisor_marks_merge_conflict(tmp_path):
    state, plan = make_plan(tmp_path, """
## STORY-001 — Foo

### Dependencies
- None.
""")
    repo = tmp_path / "repo"
    repo.mkdir()

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id)

    sup = Supervisor(state, plan, repo, escalation=parse_escalation("sonnet:3"))
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        with patch("execute.supervisor.git_ops.merge_worktree_branch", return_value="conflict"):
            with patch("execute.supervisor.git_ops.delete_branch"):
                await sup.run()

    assert state.stories["STORY-001"].status == StoryStatus.MERGE_CONFLICT


async def test_supervisor_saves_state_file(tmp_path):
    state, plan = make_plan(tmp_path, SIMPLE_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id)

    await _run_with_mock(state, plan, repo, mock_launch)
    state_file = plan.parent / "plan_state.json"
    assert state_file.exists()


async def test_supervisor_tracks_cost_per_story(tmp_path):
    state, plan = make_plan(tmp_path, SIMPLE_PLAN)
    repo = tmp_path / "repo"
    repo.mkdir()

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id, cost_usd=0.05)

    await _run_with_mock(state, plan, repo, mock_launch)
    assert state.stories["STORY-001"].cost.cost_usd == 0.05
    assert state.stories["STORY-002"].cost.cost_usd == 0.05
    assert abs(state.total_cost_usd() - 0.10) < 0.001


async def test_supervisor_writes_status_file_with_wiggum_log(tmp_path):
    import json
    from execute.wiggum_log import WiggumLog
    state, plan = make_plan(tmp_path, """
## STORY-001 — Foo

### Dependencies
- None.
""")
    repo = tmp_path / "repo"
    repo.mkdir()
    log_dir = tmp_path / "logs"
    wlog = WiggumLog(log_dir)

    async def mock_launch(story_id, story, attempt, model):
        return make_result(story_id)

    sup = Supervisor(state, plan, repo, escalation=parse_escalation("sonnet:3"), wiggum_log=wlog)
    with patch.object(sup, "_launch_agent", side_effect=mock_launch):
        with patch("execute.supervisor.git_ops.merge_worktree_branch", return_value="success"):
            with patch("execute.supervisor.git_ops.delete_branch"):
                await sup.run()

    assert wlog.status_file.exists()
    status = json.loads(wlog.status_file.read_text())
    assert "STORY-001" in status["stories"]
