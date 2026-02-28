import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class AgentOutcome(str, Enum):
    SUCCESS = "success"
    RETRY_NEEDED = "retry_needed"
    HARD_FAILURE = "hard_failure"


@dataclass
class AgentResult:
    story_id: str
    stdout: str
    stderr: str
    exit_code: int
    worktree_path: str
    branch: str

    @property
    def outcome(self) -> AgentOutcome:
        if self.exit_code != 0:
            return AgentOutcome.HARD_FAILURE
        if f"STORY_COMPLETE: {self.story_id}" in self.stdout:
            return AgentOutcome.SUCCESS
        if f"STORY_RETRY_NEEDED: {self.story_id}" in self.stdout:
            return AgentOutcome.RETRY_NEEDED
        return AgentOutcome.HARD_FAILURE

    @property
    def retry_summary(self) -> str:
        marker = f"STORY_RETRY_NEEDED: {self.story_id}"
        idx = self.stdout.find(marker)
        if idx == -1:
            return ""
        return self.stdout[idx + len(marker):].strip()


def run_story_agent(
    story_id: str,
    prompt: str,
    target_repo: Path,
    attempt: int,
    model: str = "sonnet",
    budget: Optional[float] = None,
) -> AgentResult:
    """Launch a Claude Code agent for a story. Blocking."""
    branch = f"{story_id.lower()}-attempt-{attempt}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model", model,
        "--worktree", branch,
    ]
    if budget is not None:
        cmd += ["--max-budget-usd", str(budget)]

    with open(prompt_file) as stdin_f:
        proc = subprocess.run(
            cmd,
            stdin=stdin_f,
            capture_output=True,
            text=True,
            cwd=str(target_repo),
        )

    worktree_path = str(target_repo / ".claude" / "worktrees" / branch)

    return AgentResult(
        story_id=story_id,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        worktree_path=worktree_path,
        branch=branch,
    )
