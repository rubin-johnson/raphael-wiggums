"""
Observability for wiggums executor runs.

- Per-story log files: {log_dir}/STORY-001_attempt_1.log  (tail -f friendly)
- Live status file:    {log_dir}/status.json              (watch-able)
- Console Rich display showing story table

Usage:
    tail -f features/.wiggums/logs/STORY-001_attempt_1.log
    watch -n1 cat features/.wiggums/status.json
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from execute.state import PlanState, StoryStatus


class WiggumLog:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = log_dir / "run.log"
        self._status_file = log_dir / "status.json"
        self._start_time = time.time()

    def story_log_path(self, story_id: str, attempt: int) -> Path:
        return self.log_dir / f"{story_id}_attempt_{attempt}.log"

    def write_status(self, state: PlanState) -> None:
        """Write current state to status.json for external monitoring."""
        stories_out = {}
        for sid, s in state.stories.items():
            stories_out[sid] = {
                "title": s.title,
                "status": s.status.value,
                "retry_count": s.retry_count,
                "cost_usd": round(s.cost.cost_usd, 4),
                "model": s.cost.model,
                "log_files": [
                    str(self.story_log_path(sid, i + 1))
                    for i in range(max(1, s.retry_count + 1))
                    if self.story_log_path(sid, i + 1).exists()
                ],
            }

        elapsed = time.time() - self._start_time
        data = {
            "updated_at": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed),
            "total_cost_usd": round(state.total_cost_usd(), 4),
            "summary": state.summary(),
            "stories": stories_out,
        }
        self._status_file.write_text(json.dumps(data, indent=2))

    def log(self, msg: str) -> None:
        """Append to the run log."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        with open(self._run_log, "a") as f:
            f.write(line)

    @property
    def status_file(self) -> Path:
        return self._status_file

    @property
    def run_log(self) -> Path:
        return self._run_log
