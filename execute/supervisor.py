import asyncio
import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from execute.state import PlanState, StoryState, StoryStatus
from execute.parser import extract_story_text
from execute.prompt import build_story_prompt
from execute.runner import run_story_agent, AgentResult, AgentOutcome
from execute import git as git_ops

console = Console()
log = logging.getLogger(__name__)


class Supervisor:
    def __init__(
        self,
        state: PlanState,
        plan_path: Path,
        target_repo: Path,
        max_concurrent: int = 3,
        max_retries: int = 3,
        pause_between: bool = False,
        model: str = "sonnet",
        budget_per_story: Optional[float] = None,
    ):
        self.state = state
        self.plan_path = plan_path
        self.plan_text = plan_path.read_text()
        self.target_repo = target_repo
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.pause_between = pause_between
        self.model = model
        self.budget_per_story = budget_per_story
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._state_file = plan_path.parent / "plan_state.json"

    async def run(self) -> None:
        console.rule("[bold blue]Sir Wiggums — Executor[/bold blue]")
        self._print_status()

        while not self.state.is_done():
            ready = self.state.ready_stories()
            if not ready:
                if any(s.status == StoryStatus.RUNNING for s in self.state.stories.values()):
                    await asyncio.sleep(2)
                    continue
                console.print("[red]No stories ready and none running. Possible unresolvable dependency.[/red]")
                break

            tasks = [asyncio.create_task(self._run_story(s)) for s in ready]
            await asyncio.gather(*tasks)

        self._print_final_summary()

    async def _run_story(self, story: StoryState) -> None:
        async with self._semaphore:
            if self.pause_between:
                console.print(f"\n[yellow]Ready to run {story.id}: {story.title}[/yellow]")
                answer = console.input("  Start this story? [Y/n]: ").strip().lower()
                if answer == "n":
                    console.print(f"  [dim]Skipping {story.id}[/dim]")
                    return

            attempt = story.retry_count + 1
            branch = f"{story.id.lower()}-attempt-{attempt}"
            self.state.mark_running(story.id, branch)
            self.state.save(self._state_file)

            console.print(f"[green]→ Launching {story.id}[/green] (attempt {attempt})")

            result = await self._launch_agent(story.id, story, attempt)
            await self._handle_result(story, result)

    async def _launch_agent(self, story_id: str, story: StoryState, attempt: int) -> AgentResult:
        loop = asyncio.get_event_loop()
        story_text = extract_story_text(self.plan_text, story_id)
        prompt = build_story_prompt(story, story_text, story.retry_notes)
        return await loop.run_in_executor(
            None,
            run_story_agent,
            story_id, prompt, self.target_repo, attempt, self.model, self.budget_per_story,
        )

    async def _handle_result(self, story: StoryState, result: AgentResult) -> None:
        if result.outcome == AgentOutcome.SUCCESS:
            merge_result = git_ops.merge_worktree_branch(self.target_repo, result.branch)
            if merge_result == git_ops.MergeResult.SUCCESS:
                self.state.mark_complete(story.id)
                console.print(f"[bold green]✓ {story.id} complete[/bold green]")
                git_ops.delete_branch(self.target_repo, result.branch)
            else:
                self.state.mark_merge_conflict(story.id)
                console.print(f"[red]✗ {story.id} merge conflict — manual review needed[/red]")

        elif result.outcome == AgentOutcome.RETRY_NEEDED:
            if story.retry_count < self.max_retries:
                note = result.retry_summary or "No summary provided by agent."
                self.state.record_retry(story.id, note)
                console.print(f"[yellow]↻ {story.id} retry {story.retry_count}/{self.max_retries}[/yellow]")
            else:
                self.state.mark_failed(story.id)
                console.print(f"[red]✗ {story.id} failed — retry limit reached[/red]")

        else:
            self.state.mark_failed(story.id)
            console.print(f"[red]✗ {story.id} hard failure[/red]")
            if result.stderr:
                console.print(f"[dim]{result.stderr[:500]}[/dim]")

        self.state.save(self._state_file)
        self._print_status()

    def _print_status(self) -> None:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Story")
        table.add_column("Status")
        table.add_column("Retries")
        for sid, s in self.state.stories.items():
            color = {
                StoryStatus.PENDING: "white",
                StoryStatus.RUNNING: "yellow",
                StoryStatus.COMPLETED: "green",
                StoryStatus.FAILED: "red",
                StoryStatus.MERGE_CONFLICT: "magenta",
            }.get(s.status, "white")
            table.add_row(sid, f"[{color}]{s.status.value}[/{color}]", str(s.retry_count))
        console.print(table)

    def _print_final_summary(self) -> None:
        console.rule("[bold]Run Complete[/bold]")
        console.print(self.state.summary())
