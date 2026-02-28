import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class StoryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGE_CONFLICT = "merge_conflict"


@dataclass
class StoryCost:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""


@dataclass
class StoryState:
    id: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    status: StoryStatus = StoryStatus.PENDING
    retry_count: int = 0
    retry_notes: list[str] = field(default_factory=list)
    worktree_branch: Optional[str] = None
    cost: StoryCost = field(default_factory=StoryCost)

    def is_ready(self, completed_ids: set[str]) -> bool:
        return (
            self.status == StoryStatus.PENDING
            and all(dep in completed_ids for dep in self.depends_on)
        )


class PlanState:
    def __init__(self, stories: dict[str, StoryState]):
        self.stories = stories

    @classmethod
    def from_plan(cls, plan_path: Path) -> "PlanState":
        text = plan_path.read_text()
        stories: dict[str, StoryState] = {}

        header_pattern = re.compile(r"^## ((?:STORY|BT)-\d+) — (.+)$", re.MULTILINE)
        dep_pattern = re.compile(r"- ((?:STORY|BT)-\d+) must be complete")

        sections = re.split(r"(?=^## (?:STORY|BT)-\d+)", text, flags=re.MULTILINE)

        for section in sections:
            m = header_pattern.match(section.strip())
            if not m:
                continue
            story_id = m.group(1)
            title = m.group(2).strip()

            dep_section_match = re.search(
                r"### Dependencies\n(.*?)(?=\n###|\n---|\Z)", section, re.DOTALL
            )
            depends_on = []
            if dep_section_match:
                dep_text = dep_section_match.group(1)
                if "None" not in dep_text:
                    depends_on = dep_pattern.findall(dep_text)

            stories[story_id] = StoryState(
                id=story_id, title=title, depends_on=depends_on
            )

        return cls(stories)

    @classmethod
    def load(cls, state_file: Path, plan_path: Path) -> "PlanState":
        """Load persisted state, merging with current plan for any new stories."""
        base = cls.from_plan(plan_path)
        data = json.loads(state_file.read_text())
        for story_id, saved in data["stories"].items():
            if story_id in base.stories:
                s = base.stories[story_id]
                s.status = StoryStatus(saved["status"])
                s.retry_count = saved.get("retry_count", 0)
                s.retry_notes = saved.get("retry_notes", [])
                s.worktree_branch = saved.get("worktree_branch")
                if "cost" in saved:
                    c = saved["cost"]
                    s.cost = StoryCost(
                        input_tokens=c.get("input_tokens", 0),
                        output_tokens=c.get("output_tokens", 0),
                        cost_usd=c.get("cost_usd", 0.0),
                        model=c.get("model", ""),
                    )
        return base

    def save(self, state_file: Path) -> None:
        data = {
            "stories": {
                sid: {
                    "title": s.title,
                    "status": s.status.value,
                    "depends_on": s.depends_on,
                    "retry_count": s.retry_count,
                    "retry_notes": s.retry_notes,
                    "worktree_branch": s.worktree_branch,
                    "cost": {
                        "input_tokens": s.cost.input_tokens,
                        "output_tokens": s.cost.output_tokens,
                        "cost_usd": s.cost.cost_usd,
                        "model": s.cost.model,
                    },
                }
                for sid, s in self.stories.items()
            }
        }
        state_file.write_text(json.dumps(data, indent=2))

    def completed_ids(self) -> set[str]:
        return {sid for sid, s in self.stories.items() if s.status == StoryStatus.COMPLETED}

    def ready_stories(self) -> list[StoryState]:
        done = self.completed_ids()
        running = {sid for sid, s in self.stories.items() if s.status == StoryStatus.RUNNING}
        return [
            s for s in self.stories.values()
            if s.is_ready(done) and s.id not in running
        ]

    def record_cost(self, story_id: str, cost: StoryCost) -> None:
        self.stories[story_id].cost = cost

    def total_cost_usd(self) -> float:
        return sum(s.cost.cost_usd for s in self.stories.values())

    def total_tokens(self) -> tuple[int, int]:
        ins = sum(s.cost.input_tokens for s in self.stories.values())
        outs = sum(s.cost.output_tokens for s in self.stories.values())
        return ins, outs

    def mark_complete(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.COMPLETED

    def mark_running(self, story_id: str, branch: str) -> None:
        s = self.stories[story_id]
        s.status = StoryStatus.RUNNING
        s.worktree_branch = branch

    def mark_failed(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.FAILED

    def mark_merge_conflict(self, story_id: str) -> None:
        self.stories[story_id].status = StoryStatus.MERGE_CONFLICT

    def record_retry(self, story_id: str, note: str) -> None:
        s = self.stories[story_id]
        s.status = StoryStatus.PENDING
        s.retry_count += 1
        s.retry_notes.append(note)

    def is_done(self) -> bool:
        return all(
            s.status in (StoryStatus.COMPLETED, StoryStatus.FAILED, StoryStatus.MERGE_CONFLICT)
            for s in self.stories.values()
        )

    def summary(self) -> str:
        counts: dict[StoryStatus, int] = {}
        for s in self.stories.values():
            counts[s.status] = counts.get(s.status, 0) + 1
        parts = [f"{v} {k.value}" for k, v in counts.items()]
        return " | ".join(parts)
