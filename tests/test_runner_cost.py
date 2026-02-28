"""Tests for cost parsing and log file writing in runner."""
from execute.runner import _parse_json_output
from execute.state import StoryCost


def test_parse_json_output_success():
    raw = '{"result": "STORY_COMPLETE: STORY-001", "cost_usd": 0.05, "usage": {"input_tokens": 1000, "output_tokens": 200}}'
    text, cost = _parse_json_output(raw, "sonnet")
    assert text == "STORY_COMPLETE: STORY-001"
    assert cost.cost_usd == 0.05
    assert cost.input_tokens == 1000
    assert cost.output_tokens == 200
    assert cost.model == "sonnet"


def test_parse_json_output_total_cost_field():
    raw = '{"result": "some output", "total_cost_usd": 0.12, "usage": {}}'
    text, cost = _parse_json_output(raw, "opus")
    assert cost.cost_usd == 0.12


def test_parse_json_output_fallback_on_non_json():
    raw = "STORY_COMPLETE: STORY-001\nsome plain text"
    text, cost = _parse_json_output(raw, "sonnet")
    assert "STORY_COMPLETE" in text
    assert cost.cost_usd == 0.0
    assert cost.model == "sonnet"


def test_parse_json_output_fallback_on_missing_fields():
    raw = '{"result": "done"}'
    text, cost = _parse_json_output(raw, "sonnet")
    assert text == "done"
    assert cost.cost_usd == 0.0
    assert cost.input_tokens == 0
