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
        if len(injected_prompts) == 1:
            return "# PRD\n\n## Goal\nThing.\n"
        return "## STORY-001\n\n### Dependencies\n- None.\n"

    with patch("generate.prd.call_claude", side_effect=mock_claude):
        run_prd_pipeline(notes, codebase=codebase, model="sonnet")

    # Codebase context injected into stage 2 prompt
    assert "main.py" in injected_prompts[1] or "foo" in injected_prompts[1]


def test_prd_pipeline_output_has_header(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("Do stuff.")

    def mock_claude(prompt: str, model: str) -> str:
        return "## STORY-001 — Do stuff\n\n### Dependencies\n- None.\n"

    with patch("generate.prd.call_claude", side_effect=mock_claude):
        result = run_prd_pipeline(notes, codebase=None, model="sonnet")

    assert "# Implementation Plan" in result
    assert "Raphael" in result


def test_prd_pipeline_no_codebase_skips_context(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("Do stuff.")

    injected_prompts = []

    def mock_claude(prompt: str, model: str) -> str:
        injected_prompts.append(prompt)
        return "## STORY-001\n\n### Dependencies\n- None.\n"

    with patch("generate.prd.call_claude", side_effect=mock_claude):
        run_prd_pipeline(notes, codebase=None, model="sonnet")

    assert "Existing Codebase" not in injected_prompts[1]
