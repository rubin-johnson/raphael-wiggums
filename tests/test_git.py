import subprocess
import pytest
from pathlib import Path
from execute.git import merge_worktree_branch, MergeResult


def make_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_merge_clean_branch_succeeds(tmp_path):
    repo = make_repo(tmp_path)
    subprocess.run(["git", "checkout", "-b", "story-001-attempt-1"], cwd=repo, check=True, capture_output=True)
    (repo / "new_file.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add file"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)

    result = merge_worktree_branch(repo, "story-001-attempt-1")
    assert result == MergeResult.SUCCESS
    assert (repo / "new_file.py").exists()


def test_merge_conflict_detected(tmp_path):
    repo = make_repo(tmp_path)
    subprocess.run(["git", "checkout", "-b", "story-001-attempt-1"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Branch version\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "branch change"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Main version\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "main change"], cwd=repo, check=True, capture_output=True)

    result = merge_worktree_branch(repo, "story-001-attempt-1")
    assert result == MergeResult.CONFLICT


def test_repo_clean_after_conflict_abort(tmp_path):
    repo = make_repo(tmp_path)
    subprocess.run(["git", "checkout", "-b", "story-001-attempt-1"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Branch\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "b"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Main\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "m"], cwd=repo, check=True, capture_output=True)

    merge_worktree_branch(repo, "story-001-attempt-1")

    # Verify no merge in progress
    status = subprocess.run(["git", "status"], cwd=repo, capture_output=True, text=True)
    assert "merge" not in status.stdout.lower() or "nothing to commit" in status.stdout.lower()
