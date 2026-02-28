import json
from pathlib import Path
from unittest.mock import patch
from understand.mapper import map_module, EXPECTED_FIELDS


def _make_result(**overrides):
    base = {
        "file": "foo.py",
        "purpose": "Does stuff",
        "public_api": ["fn"],
        "data_flow": "in -> out",
        "internal_dependencies": [],
        "external_dependencies": [],
        "complexity_signals": [],
        "smells": [],
        "simplification_opportunities": [],
        "test_coverage_estimate": "low",
        "lines_of_code": 10,
    }
    base.update(overrides)
    return json.dumps(base)


def test_map_module_returns_parsed_json(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def fn(): pass\n")
    with patch("understand.mapper.call_claude", return_value=_make_result()):
        result = map_module(f, tmp_path, repo_map="foo.py:\n  def fn()")
    assert result["purpose"] == "Does stuff"
    assert result["file"] == "foo.py"


def test_map_module_has_all_expected_fields(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def fn(): pass\n")
    with patch("understand.mapper.call_claude", return_value=_make_result()):
        result = map_module(f, tmp_path, repo_map="")
    for field in EXPECTED_FIELDS:
        assert field in result, f"Missing field: {field}"


def test_map_module_handles_invalid_json(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def fn(): pass\n")
    with patch("understand.mapper.call_claude", return_value="not json at all"):
        result = map_module(f, tmp_path, repo_map="")
    assert result["file"] == "foo.py"
    assert "error" in result


def test_map_module_uses_relative_path(tmp_path):
    sub = tmp_path / "execute"
    sub.mkdir()
    f = sub / "state.py"
    f.write_text("class PlanState: pass\n")
    with patch("understand.mapper.call_claude", return_value=_make_result(file="execute/state.py")):
        result = map_module(f, tmp_path, repo_map="")
    assert result["file"] == "execute/state.py"
