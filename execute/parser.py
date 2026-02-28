import re


STORY_HEADER = re.compile(r"^## ((?:STORY|BT)-\d+) —", re.MULTILINE)


def extract_all_story_ids(plan_text: str) -> list[str]:
    return STORY_HEADER.findall(plan_text)


def extract_story_text(plan_text: str, story_id: str) -> str:
    """Extract the full markdown block for a story. Raises KeyError if not found."""
    pattern = re.compile(rf"^## {re.escape(story_id)} —", re.MULTILINE)
    m = pattern.search(plan_text)
    if not m:
        raise KeyError(f"Story {story_id} not found in plan")

    start = m.start()
    remaining = plan_text[start:]
    next_story = STORY_HEADER.search(remaining, 1)
    if next_story:
        return remaining[: next_story.start()].strip()
    return remaining.strip()
