import subprocess
from enum import Enum
from pathlib import Path


class MergeResult(str, Enum):
    SUCCESS = "success"
    CONFLICT = "conflict"
    ERROR = "error"


def merge_worktree_branch(repo: Path, branch: str) -> MergeResult:
    """Merge branch into current branch (main). Returns result enum."""
    result = subprocess.run(
        ["git", "merge", "--no-ff", branch, "-m", f"merge: {branch}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return MergeResult.SUCCESS

    if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
        subprocess.run(["git", "merge", "--abort"], cwd=str(repo), capture_output=True)
        return MergeResult.CONFLICT

    return MergeResult.ERROR


def delete_branch(repo: Path, branch: str) -> None:
    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=str(repo),
        capture_output=True,
    )
