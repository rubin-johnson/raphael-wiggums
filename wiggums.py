import click


@click.group()
def cli():
    """Sir Wiggums — PRD-to-stories pipeline and executor."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="features/plan.md", show_default=True, help="Output plan file")
@click.option("--codebase", "-c", type=click.Path(exists=True), default=None, help="Path to target codebase")
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Claude model to use")
def generate(input_file, output, codebase, model):
    """Convert raw notes into an implementation plan."""
    from pathlib import Path
    from generate.prd import run_prd_pipeline

    notes_path = Path(input_file)
    codebase_path = Path(codebase) if codebase else None
    output_path = Path(output)

    click.echo("Stage 1: Converting notes to PRD...")
    click.echo("Stage 2: Generating stories...")

    plan_md = run_prd_pipeline(notes_path, codebase=codebase_path, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(plan_md)
    click.echo(f"Plan written to {output_path}")
    click.echo(f"Review it, then run: wiggums execute {output_path} <target-repo>")


@cli.command()
@click.argument("plan_file", type=click.Path(exists=True))
@click.argument("target_repo", type=click.Path(exists=True))
@click.option("--max-concurrent", default=3, show_default=True, help="Max parallel agents")
@click.option("--max-retries", default=3, show_default=True, help="Max retries per story on context exhaustion")
@click.option("--pause-between", is_flag=True, help="Pause for approval between stories")
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Claude model to use")
@click.option("--budget-per-story", default=None, type=float, help="Max spend per story in USD")
def execute(plan_file, target_repo, max_concurrent, max_retries, pause_between, model, budget_per_story):
    """Execute stories from a plan file using Claude Code agents."""
    import asyncio
    from pathlib import Path
    from execute.state import PlanState
    from execute.supervisor import Supervisor

    plan_path = Path(plan_file)
    repo_path = Path(target_repo)
    state_file = plan_path.parent / "plan_state.json"

    if state_file.exists():
        state = PlanState.load(state_file, plan_path)
        click.echo("Resuming from existing state.")
    else:
        state = PlanState.from_plan(plan_path)

    sup = Supervisor(
        state=state,
        plan_path=plan_path,
        target_repo=repo_path,
        max_concurrent=max_concurrent,
        max_retries=max_retries,
        pause_between=pause_between,
        model=model,
        budget_per_story=budget_per_story,
    )
    asyncio.run(sup.run())


if __name__ == "__main__":
    cli()
