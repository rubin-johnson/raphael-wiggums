from unittest.mock import patch
from understand.reducer import run_reduce

FAKE_SUMMARIES = [
    {"file": "foo.py", "purpose": "Does foo", "smells": [], "simplification_opportunities": []},
]
FAKE_REPO_MAP = "foo.py:\n  def fn()"
FAKE_UNDERSTANDING = "### Architecture Overview\nThis is a simple project.\n"


def test_run_reduce_returns_string():
    with patch("understand.reducer.call_claude", return_value=FAKE_UNDERSTANDING):
        result = run_reduce(FAKE_SUMMARIES, FAKE_REPO_MAP)
    assert isinstance(result, str)
    assert len(result) > 0


def test_run_reduce_includes_module_data_in_prompt():
    with patch("understand.reducer.call_claude", return_value=FAKE_UNDERSTANDING) as mock:
        run_reduce(FAKE_SUMMARIES, FAKE_REPO_MAP)
    prompt = mock.call_args[0][0]
    assert "foo.py" in prompt
    assert "Does foo" in prompt


def test_run_reduce_passes_retry_context_when_provided():
    with patch("understand.reducer.call_claude", return_value=FAKE_UNDERSTANDING) as mock:
        run_reduce(FAKE_SUMMARIES, FAKE_REPO_MAP, retry_context="Previous attempt missed X.")
    prompt = mock.call_args[0][0]
    assert "Previous attempt missed X." in prompt
