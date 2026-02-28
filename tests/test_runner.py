from execute.runner import AgentResult, AgentOutcome


def test_agent_result_detects_success():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Some output\nSTORY_COMPLETE: STORY-001\n",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.SUCCESS


def test_agent_result_detects_retry_needed():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Partial work done.\nSTORY_RETRY_NEEDED: STORY-001\nWrote foo() but bar() unfinished.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.RETRY_NEEDED


def test_agent_result_extracts_retry_summary():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Stuff.\nSTORY_RETRY_NEEDED: STORY-001\nfoo() done, bar() needs tests.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert "foo() done" in result.retry_summary


def test_agent_result_detects_hard_failure_on_nonzero_exit():
    result = AgentResult(
        story_id="STORY-001",
        stdout="Something went wrong.",
        stderr="Error: API error",
        exit_code=1,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.HARD_FAILURE


def test_agent_result_hard_failure_when_no_signal():
    result = AgentResult(
        story_id="STORY-001",
        stdout="I did stuff but forgot to emit the signal.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.outcome == AgentOutcome.HARD_FAILURE


def test_retry_summary_empty_when_no_marker():
    result = AgentResult(
        story_id="STORY-001",
        stdout="No marker here.",
        stderr="",
        exit_code=0,
        worktree_path="/tmp/wt",
        branch="story-001-attempt-1",
    )
    assert result.retry_summary == ""
