import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from execute.state import StoryCost


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
    cost: StoryCost = field(default_factory=StoryCost)

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


def _parse_json_output(raw: str, model: str) -> tuple[str, StoryCost]:
    """
    Parse claude --output-format json output.
    Returns (text_content, StoryCost).
    Falls back gracefully if format is unexpected.
    """
    try:
        data = json.loads(raw)
        text = data.get("result", raw)
        cost_usd = float(data.get("cost_usd", 0.0) or data.get("total_cost_usd", 0.0))
        usage = data.get("usage", {})
        return text, StoryCost(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=cost_usd,
            model=model,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return raw, StoryCost(model=model)


def run_story_agent(
    story_id: str,
    prompt: str,
    target_repo: Path,
    attempt: int,
    model: str = "sonnet",
    budget: Optional[float] = None,
    log_file: Optional[Path] = None,
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
        "--output-format", "json",
        "--worktree", branch,
    ]
    if budget is not None:
        cmd += ["--max-budget-usd", str(budget)]

    log_fh = None
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file, "w")
        log_fh.write(f"# {story_id} attempt {attempt} — model: {model}\n")
        log_fh.write(f"# cmd: {' '.join(cmd)}\n\n")

    try:
        with open(prompt_file) as stdin_f:
            proc = subprocess.run(
                cmd,
                stdin=stdin_f,
                capture_output=True,
                text=True,
                cwd=str(target_repo),
            )

        if log_fh:
            log_fh.write("## STDOUT\n")
            log_fh.write(proc.stdout)
            if proc.stderr:
                log_fh.write("\n## STDERR\n")
                log_fh.write(proc.stderr)
            log_fh.write(f"\n## EXIT CODE: {proc.returncode}\n")
    finally:
        if log_fh:
            log_fh.close()

    text, cost = _parse_json_output(proc.stdout, model)
    worktree_path = str(target_repo / ".claude" / "worktrees" / branch)

    return AgentResult(
        story_id=story_id,
        stdout=text,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        worktree_path=worktree_path,
        branch=branch,
        cost=cost,
    )
