import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from raphael import cli

REPO_ROOT = Path(__file__).parent.parent
RAPHAEL = [sys.executable, str(REPO_ROOT / "raphael.py")]


def run(args, cwd=None, env=None, input=None):
    return subprocess.run(
        RAPHAEL + args,
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env,
        input=input,
    )


def test_understand_help_has_correct_options():
    result = run(["understand", "--help"])
    assert result.returncode == 0
    assert "--map-model" in result.stdout
    assert "--reduce-escalation" in result.stdout


def test_understand_creates_output_files(tmp_path):
    (tmp_path / "foo.py").write_text("def greet(name): return f'hi {name}'\n")
    out_dir = tmp_path / ".raphael"

    module_json = '{"file": "foo.py", "purpose": "Greets.", "public_api": ["greet"], "data_flow": "in->out", "internal_dependencies": [], "external_dependencies": [], "complexity_signals": [], "smells": [], "simplification_opportunities": [], "test_coverage_estimate": "none", "lines_of_code": 1}'
    understanding = "### Architecture Overview\nSimple greeter.\n"
    coherence_score = '{"accuracy": 8, "specificity": 8, "actionability": 7, "overall": 8, "pass": true, "issues": [], "missing": []}'

    runner = CliRunner()
    with patch("understand.mapper.call_claude", return_value=module_json):
        with patch("understand.coherence.call_claude", side_effect=[understanding, coherence_score]):
            result = runner.invoke(cli, ["understand", str(tmp_path), "--output-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert (out_dir / "repo_map.md").exists()
    assert (out_dir / "understanding.md").exists()


def test_understand_prints_path(tmp_path):
    (tmp_path / "bar.py").write_text("x = 1\n")
    out_dir = tmp_path / ".raphael"

    module_json = '{"file": "bar.py", "purpose": "Sets x.", "public_api": [], "data_flow": "none", "internal_dependencies": [], "external_dependencies": [], "complexity_signals": [], "smells": [], "simplification_opportunities": [], "test_coverage_estimate": "none", "lines_of_code": 1}'
    understanding = "### Architecture Overview\nJust a variable.\n"
    coherence_score = '{"accuracy": 9, "specificity": 8, "actionability": 8, "overall": 9, "pass": true, "issues": [], "missing": []}'

    runner = CliRunner()
    with patch("understand.mapper.call_claude", return_value=module_json):
        with patch("understand.coherence.call_claude", side_effect=[understanding, coherence_score]):
            result = runner.invoke(cli, ["understand", str(tmp_path), "--output-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert "understanding.md" in result.output
