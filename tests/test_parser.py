import pytest
from execute.parser import extract_story_text, extract_all_story_ids

SAMPLE_PLAN = """
## Overview

Some intro text.

---

## BT-001 — Behavioral Tests: Foo

Content for BT-001.

### Dependencies
- None.

---

## STORY-001 — Bar

Content for STORY-001.

### Dependencies
- None.

---

## STORY-002 — Baz

Content for STORY-002.

### Dependencies
- STORY-001 must be complete.

---
"""


def test_extract_story_text_returns_correct_block():
    text = extract_story_text(SAMPLE_PLAN, "STORY-001")
    assert "## STORY-001 — Bar" in text
    assert "Content for STORY-001." in text


def test_extract_story_text_does_not_include_next_story():
    text = extract_story_text(SAMPLE_PLAN, "STORY-001")
    assert "STORY-002" not in text


def test_extract_bt_story():
    text = extract_story_text(SAMPLE_PLAN, "BT-001")
    assert "BT-001" in text
    assert "Content for BT-001." in text


def test_extract_nonexistent_story_raises():
    with pytest.raises(KeyError):
        extract_story_text(SAMPLE_PLAN, "STORY-999")


def test_extract_all_story_ids():
    ids = extract_all_story_ids(SAMPLE_PLAN)
    assert ids == ["BT-001", "STORY-001", "STORY-002"]
