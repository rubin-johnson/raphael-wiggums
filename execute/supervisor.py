import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from execute.state import PlanState, StoryState, StoryStatus, StoryCost
from execute.parser import extract_story_text
from execute.prompt import build_story_prompt
from execute.runner import run_story_agent, AgentResult, AgentOutcome
from execute.cost import ModelTier, model_for_attempt, parse_escalation
from execute.wiggum_log import WiggumLog
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
        escalation: Optional[list[ModelTier]] = None,
        pause_between: bool = False,
        budget_per_story: Optional[float] = None,
        wiggum_log: Optional[WiggumLog] = None,
    ):
        self.state = state
        self.plan_path = plan_path
        self.plan_text = plan_path.read_text()
        self.target_repo = target_repo
        self.max_concurrent = max_concurrent
        self.escalation = escalation or parse_escalation("sonnet:3")
        self.pause_between = pause_between
        self.budget_per_story = budget_per_story
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._state_file = plan_path.parent / "plan_state.json"
        self._wlog = wiggum_log
        self._shutdown = False

    async def run(self) -> None:
        console.rule("[bold blue]Sir Wiggums — Executor[/bold blue]")
        if self._wlog:
            console.print(f"[dim]Logs: {self._wlog.log_dir}[/dim]")
            console.print(f"[dim]Status: tail -f {self._wlog.run_log}[/dim]")
            console.print(f"[dim]        watch -n2 cat {self._wlog.status_file}[/dim]")
        self._print_status()

        # Graceful Ctrl-C: save state and exit cleanly
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._request_shutdown)

        active_tasks: set[asyncio.Task] = set()
        tasked_ids: set[str] = set()  # story IDs that have an active task

        while not self.state.is_done() and not self._shutdown:
            # Launch any newly-ready stories not already tasked
            for story in self.state.ready_stories():
                if self._shutdown or story.id in tasked_ids:
                    continue
                task = asyncio.create_task(self._run_story(story), name=story.id)
                active_tasks.add(task)
                tasked_ids.add(story.id)

            if not active_tasks:
                console.print("[red]Deadlock: no ready stories and none running.[/red]")
                break

            # Wait for the first task to finish, then re-evaluate ready set
            done, active_tasks = await asyncio.wait(
                active_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                tasked_ids.discard(task.get_name())
                if task.exception():
                    log.error("Story task raised: %s", task.exception())

        # Drain remaining tasks on shutdown
        if active_tasks:
            console.print("[yellow]Waiting for in-progress stories to reach a safe stopping point...[/yellow]")
            await asyncio.gather(*active_tasks, return_exceptions=True)

        self._print_final_summary()

    def _request_shutdown(self) -> None:
        self._shutdown = True
        console.print("\n[yellow]Shutdown requested — finishing current stories then stopping.[/yellow]")
        if self._wlog:
            self._wlog.log("SIGINT received — graceful shutdown initiated")

    async def _run_story(self, story: StoryState) -> None:
        async with self._semaphore:
            if self._shutdown:
                return

            if self.pause_between:
                console.print(f"\n[yellow]Ready: {story.id} — {story.title}[/yellow]")
                answer = console.input("  Start? [Y/n]: ").strip().lower()
                if answer == "n":
                    console.print(f"  [dim]Skipping {story.id}[/dim]")
                    return

            attempt = story.retry_count + 1
            branch = f"{story.id.lower()}-attempt-{attempt}"
            model = model_for_attempt(self.escalation, attempt)

            self.state.mark_running(story.id, branch)
            self._save_and_log(story.id, f"Starting attempt {attempt} on {model}")

            console.print(f"[green]→[/green] {story.id} ({model}, attempt {attempt})")

            result = await self._launch_agent(story.id, story, attempt, model)
            await self._handle_result(story, result, model)

    async def _launch_agent(
        self, story_id: str, story: StoryState, attempt: int, model: str
    ) -> AgentResult:
        loop = asyncio.get_event_loop()
        story_text = extract_story_text(self.plan_text, story_id)
        prompt = build_story_prompt(story, story_text, story.retry_notes)
        log_file = self._wlog.story_log_path(story_id, attempt) if self._wlog else None

        return await loop.run_in_executor(
            None,
            run_story_agent,
            story_id, prompt, self.target_repo, attempt, model,
            self.budget_per_story, log_file,
        )

    async def _handle_result(self, story: StoryState, result: AgentResult, model: str) -> None:
        self.state.record_cost(story.id, result.cost)

        if result.outcome == AgentOutcome.SUCCESS:
            merge_result = git_ops.merge_worktree_branch(self.target_repo, result.branch)
            if merge_result == git_ops.MergeResult.SUCCESS:
                self.state.mark_complete(story.id)
                cost_str = f"${result.cost.cost_usd:.3f}" if result.cost.cost_usd else ""
                console.print(f"[bold green]✓[/bold green] {story.id} complete {cost_str}")
                git_ops.delete_branch(self.target_repo, result.branch)
                self._save_and_log(story.id, f"Complete — {cost_str}")
            else:
                self.state.mark_merge_conflict(story.id)
                console.print(f"[red]✗[/red] {story.id} merge conflict — manual review needed")
                if self._wlog:
                    self._wlog.log(f"{story.id}: merge conflict on branch {result.branch}")

        elif result.outcome == AgentOutcome.RETRY_NEEDED:
            # Determine remaining attempts across escalation schedule
            next_attempt = story.retry_count + 2  # +2 because retry_count increments below
            next_model = model_for_attempt(self.escalation, next_attempt)
            total_used = story.retry_count + 1
            total_allowed = sum(t.max_attempts for t in self.escalation)

            if total_used < total_allowed:
                note = result.retry_summary or "No summary from agent."
                self.state.record_retry(story.id, note)
                retry_msg = f"↻ {story.id} retry {story.retry_count}/{total_allowed - 1} → {next_model}"
                console.print(f"[yellow]{retry_msg}[/yellow]")
                self._save_and_log(story.id, retry_msg)
            else:
                self.state.mark_failed(story.id)
                console.print(f"[red]✗[/red] {story.id} failed — all attempts exhausted")
                self._save_and_log(story.id, "Failed — retry limit reached")

        else:
            self.state.mark_failed(story.id)
            msg = f"✗ {story.id} hard failure (exit {result.exit_code})"
            console.print(f"[red]{msg}[/red]")
            if result.stderr:
                console.print(f"[dim]{result.stderr[:300]}[/dim]")
            self._save_and_log(story.id, msg)

        self.state.save(self._state_file)
        if self._wlog:
            self._wlog.write_status(self.state)
        self._print_status()

    def _save_and_log(self, story_id: str, msg: str) -> None:
        self.state.save(self._state_file)
        if self._wlog:
            self._wlog.log(f"{story_id}: {msg}")
            self._wlog.write_status(self.state)

    def _print_status(self) -> None:
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Story", style="bold")
        table.add_column("Status")
        table.add_column("Model")
        table.add_column("Retries")
        table.add_column("Cost", justify="right")

        for sid, s in self.state.stories.items():
            color = {
                StoryStatus.PENDING: "white",
                StoryStatus.RUNNING: "yellow",
                StoryStatus.COMPLETED: "green",
                StoryStatus.FAILED: "red",
                StoryStatus.MERGE_CONFLICT: "magenta",
            }.get(s.status, "white")
            cost_str = f"${s.cost.cost_usd:.3f}" if s.cost.cost_usd else "—"
            table.add_row(
                sid,
                f"[{color}]{s.status.value}[/{color}]",
                s.cost.model or "—",
                str(s.retry_count),
                cost_str,
            )

        console.print(table)

    def _print_final_summary(self) -> None:
        console.rule("[bold]Run Complete[/bold]")
        console.print(self.state.summary())
        total = self.state.total_cost_usd()
        ins, outs = self.state.total_tokens()
        if total:
            console.print(f"Total cost: [bold]${total:.3f}[/bold]  ({ins:,} in / {outs:,} out tokens)")
