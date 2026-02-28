from unittest.mock import patch
from understand.critic import run_critique, run_critique_pipeline

FAKE_UNDERSTANDING = "### Architecture Overview\nSimple codebase with one module."
FAKE_CRITIQUE = "### Current State Assessment\nClean but has duplication.\n\n### Prioritized Improvements\n1. Remove X"
FAKE_PLAN = "## STORY-001 — Remove X\n\n### Dependencies\n- None.\n"


def test_run_critique_calls_claude_with_understanding():
    with patch("understand.critic.call_claude", return_value=FAKE_CRITIQUE) as mock:
        result = run_critique(FAKE_UNDERSTANDING)
    assert result == FAKE_CRITIQUE
    assert "Architecture Overview" in mock.call_args[0][0]


def test_run_critique_pipeline_returns_critique_and_plan():
    with patch("understand.critic.call_claude", side_effect=[FAKE_CRITIQUE, FAKE_PLAN]):
        critique, plan = run_critique_pipeline(FAKE_UNDERSTANDING)
    assert "duplication" in critique
    assert "STORY-001" in plan


def test_run_critique_pipeline_plan_is_executable(tmp_path):
    """Plan output must parse as valid PlanState."""
    from execute.state import PlanState
    plan_file = tmp_path / "plan.md"
    with patch("understand.critic.call_claude", side_effect=[FAKE_CRITIQUE, FAKE_PLAN]):
        _, plan = run_critique_pipeline(FAKE_UNDERSTANDING)
    plan_file.write_text(plan)
    state = PlanState.from_plan(plan_file)
    assert "STORY-001" in state.stories
