import json
from unittest.mock import patch
from execute.cost import parse_escalation
from understand.coherence import run_coherence_gate

REPO_MAP = "execute/supervisor.py:\n  class Supervisor:"
UNDERSTANDING = "### Architecture Overview\nThis project is good."


def _score(overall, passed):
    return json.dumps({
        "accuracy": overall, "specificity": overall, "actionability": overall,
        "overall": overall, "pass": passed,
        "issues": [] if passed else ["Too vague"],
        "missing": [] if passed else ["Supervisor complexity not mentioned"],
    })


def test_coherence_gate_passes_on_good_score():
    escalation = parse_escalation("sonnet:2")
    with patch("understand.coherence.call_claude", side_effect=[
        UNDERSTANDING,      # reduce call
        _score(8, True),    # coherence check — pass
    ]):
        result = run_coherence_gate([], REPO_MAP, escalation)
    assert result == UNDERSTANDING


def test_coherence_gate_retries_on_low_score():
    escalation = parse_escalation("sonnet:3")
    better = "### Architecture Overview\nThis project has Supervisor class in execute/supervisor.py."
    with patch("understand.coherence.call_claude", side_effect=[
        UNDERSTANDING,       # reduce attempt 1
        _score(5, False),    # coherence check — fail
        better,              # reduce attempt 2 (with retry context injected)
        _score(8, True),     # coherence check — pass
    ]) as mock:
        result = run_coherence_gate([], REPO_MAP, escalation)
    assert result == better
    assert mock.call_count == 4


def test_coherence_gate_returns_best_effort_when_exhausted():
    escalation = parse_escalation("sonnet:2")
    with patch("understand.coherence.call_claude", side_effect=[
        UNDERSTANDING,      # reduce attempt 1
        _score(4, False),   # coherence check — fail
        "attempt 2",        # reduce attempt 2
        _score(5, False),   # coherence check — fail, all attempts exhausted
    ]):
        result = run_coherence_gate([], REPO_MAP, escalation)
    assert result == "attempt 2"


def test_coherence_gate_injects_retry_context_into_second_attempt():
    escalation = parse_escalation("sonnet:2")
    with patch("understand.coherence.call_claude", side_effect=[
        UNDERSTANDING,
        _score(5, False),
        "attempt 2",
        _score(8, True),
    ]) as mock:
        run_coherence_gate([], REPO_MAP, escalation)
    # The third call is the second reduce — its prompt should mention the score/issues
    second_reduce_prompt = mock.call_args_list[2][0][0]
    assert "5" in second_reduce_prompt or "vague" in second_reduce_prompt.lower() or "Too vague" in second_reduce_prompt
