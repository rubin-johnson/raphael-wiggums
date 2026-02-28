from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from raphael import cli
import sys
import subprocess

REPO_ROOT = Path(__file__).parent.parent
RAPHAEL = [sys.executable, str(REPO_ROOT / "raphael.py")]


def run(args, **kwargs):
    return subprocess.run(RAPHAEL + args, capture_output=True, text=True, cwd=REPO_ROOT, **kwargs)


def test_critique_help_has_correct_options():
    result = run(["critique", "--help"])
    assert result.returncode == 0
    assert "--plan-output" in result.stdout
    assert "--run-understand" in result.stdout


def test_critique_errors_without_understanding(tmp_path):
    # No .raphael/understanding.md → should fail with helpful error
    runner = CliRunner()
    result = runner.invoke(cli, ["critique", str(tmp_path)])
    assert result.exit_code != 0
    assert "understanding" in result.output.lower()


def test_critique_writes_critique_and_plan(tmp_path):
    raphael_dir = tmp_path / ".raphael"
    raphael_dir.mkdir()
    (raphael_dir / "understanding.md").write_text("### Architecture Overview\nSimple.\n")
    plan_out = tmp_path / "features" / "plan.md"

    fake_critique = "### Current State Assessment\nClean.\n\n### Prioritized Improvements\n1. Simplify X"
    fake_plan = "## STORY-001 — Simplify X\n\n### Dependencies\n- None.\n"

    runner = CliRunner()
    with patch("understand.critic.call_claude", side_effect=[fake_critique, fake_plan]):
        result = runner.invoke(cli, ["critique", str(tmp_path), "--plan-output", str(plan_out)])

    assert result.exit_code == 0, result.output
    assert (raphael_dir / "critique.md").exists()
    assert plan_out.exists()
    assert "STORY-001" in plan_out.read_text()


def test_critique_prints_paths(tmp_path):
    raphael_dir = tmp_path / ".raphael"
    raphael_dir.mkdir()
    (raphael_dir / "understanding.md").write_text("### Architecture Overview\nSimple.\n")
    plan_out = tmp_path / "features" / "plan.md"

    fake_critique = "### Current State Assessment\nClean.\n"
    fake_plan = "## STORY-001 — X\n\n### Dependencies\n- None.\n"

    runner = CliRunner()
    with patch("understand.critic.call_claude", side_effect=[fake_critique, fake_plan]):
        result = runner.invoke(cli, ["critique", str(tmp_path), "--plan-output", str(plan_out)])

    assert "critique.md" in result.output
    assert str(plan_out) in result.output
