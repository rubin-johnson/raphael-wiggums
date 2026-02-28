import json
from pathlib import Path
from execute.state import PlanState, StoryState, StoryStatus


def test_load_from_plan_md(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    assert len(state.stories) == 2
    assert "STORY-001" in state.stories
    assert "STORY-002" in state.stories


def test_dependency_parsing(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    assert state.stories["STORY-002"].depends_on == ["STORY-001"]
    assert state.stories["STORY-001"].depends_on == []


def test_ready_stories_are_dependency_free(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    ready = state.ready_stories()
    assert [s.id for s in ready] == ["STORY-001"]


def test_completing_story_unblocks_dependents(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- STORY-001 must be complete.
""")
    state = PlanState.from_plan(plan)
    state.mark_complete("STORY-001")
    ready = state.ready_stories()
    assert [s.id for s in ready] == ["STORY-002"]


def test_state_persists_to_json(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state_file = tmp_path / "plan_state.json"
    state.save(state_file)
    loaded = json.loads(state_file.read_text())
    assert "STORY-001" in loaded["stories"]


def test_state_loads_from_json(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state_file = tmp_path / "plan_state.json"
    state.save(state_file)
    state2 = PlanState.load(state_file, plan)
    assert state2.stories["STORY-001"].status == StoryStatus.PENDING


def test_retry_count_increments(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    state.record_retry("STORY-001", "Context exhausted after writing foo()")
    assert state.stories["STORY-001"].retry_count == 1
    assert len(state.stories["STORY-001"].retry_notes) == 1


def test_bt_stories_parsed(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## BT-001 — Behavioral Tests

### Dependencies
- None.

---

## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    assert "BT-001" in state.stories
    assert "STORY-001" in state.stories


def test_is_done_when_all_terminal(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    assert not state.is_done()
    state.mark_complete("STORY-001")
    assert state.is_done()


def test_parallel_independent_stories_all_ready(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("""
## STORY-001 — Foo

### Dependencies
- None.

---

## STORY-002 — Bar

### Dependencies
- None.

---

## STORY-003 — Baz

### Dependencies
- None.
""")
    state = PlanState.from_plan(plan)
    ready = state.ready_stories()
    assert len(ready) == 3
