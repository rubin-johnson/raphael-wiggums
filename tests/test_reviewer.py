import pytest
from pathlib import Path
from review.reviewer import build_review_prompt, extract_rewritten_plan


def test_build_review_prompt_includes_plan_text(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary=None)
    assert "STORY-001" in prompt


def test_build_review_prompt_includes_state_when_provided(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary="1 completed, 0 failed")
    assert "1 completed" in prompt


def test_build_review_prompt_no_state_says_not_started(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## STORY-001 — Foo\n\n### Dependencies\n- None.\n")
    prompt = build_review_prompt(plan, state_summary=None)
    assert "not started" in prompt.lower() or "no execution" in prompt.lower()


def test_extract_rewritten_plan_finds_block():
    raw = "Some feedback.\n===REWRITTEN_PLAN_START===\n# New Plan\n===REWRITTEN_PLAN_END==="
    result = extract_rewritten_plan(raw)
    assert result == "# New Plan"


def test_extract_rewritten_plan_returns_none_when_absent():
    raw = "Some feedback without a rewrite block."
    result = extract_rewritten_plan(raw)
    assert result is None


def test_extract_rewritten_plan_strips_whitespace():
    raw = "===REWRITTEN_PLAN_START===\n\n# Plan\n\n===REWRITTEN_PLAN_END==="
    result = extract_rewritten_plan(raw)
    assert result == "# Plan"
