from pathlib import Path
from execute.state import StoryState

TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "story_executor.md"


def build_story_prompt(story: StoryState, story_text: str, retry_notes: list[str]) -> str:
    template = TEMPLATE_PATH.read_text()

    retry_section = ""
    if retry_notes:
        notes_formatted = "\n".join(f"- {n}" for n in retry_notes)
        retry_section = f"""
## Previous Attempt Context

PREVIOUS ATTEMPT(S) left the following notes. Start from where they left off:

{notes_formatted}

The working tree may already have partial implementation from a previous attempt.
Check what exists before rewriting from scratch.
"""

    return template.format(
        story_id=story.id,
        story_text=story_text,
        retry_section=retry_section,
    )
