from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from raphael import cli

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
