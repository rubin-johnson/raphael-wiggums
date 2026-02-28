from execute.prompt import build_story_prompt
from execute.state import StoryState


def test_prompt_contains_story_text():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    story_text = "## STORY-001 — Foo\n\nDo the thing."
    prompt = build_story_prompt(story, story_text, retry_notes=[])
    assert "STORY-001" in prompt
    assert "Do the thing." in prompt


def test_prompt_contains_retry_context_when_present():
    story = StoryState(
        id="STORY-001",
        title="Foo",
        depends_on=[],
        retry_count=1,
        retry_notes=["Wrote foo() but tests still failing at line 42"],
    )
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo the thing.", retry_notes=story.retry_notes)
    assert "PREVIOUS ATTEMPT" in prompt
    assert "line 42" in prompt


def test_prompt_no_retry_context_when_first_attempt():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo it.", retry_notes=[])
    assert "PREVIOUS ATTEMPT" not in prompt


def test_prompt_contains_success_instructions():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo it.", retry_notes=[])
    assert "commit" in prompt.lower()
    assert "pytest" in prompt.lower() or "test" in prompt.lower()


def test_prompt_contains_story_id_in_success_signal():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo it.", retry_notes=[])
    assert "STORY_COMPLETE: STORY-001" in prompt


def test_prompt_contains_retry_signal():
    story = StoryState(id="STORY-001", title="Foo", depends_on=[])
    prompt = build_story_prompt(story, "## STORY-001 — Foo\n\nDo it.", retry_notes=[])
    assert "STORY_RETRY_NEEDED: STORY-001" in prompt
