import click


@click.group()
def cli():
    """Raphael — PRD-to-stories pipeline and executor."""
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
@click.option("--model-escalation", default="sonnet:3", show_default=True, help="Model retry schedule, e.g. 'sonnet:3,opus:2'")
@click.option("--pause-between", is_flag=True, help="Pause for approval between stories")
@click.option("--budget-per-story", default=None, type=float, help="Max spend per story in USD")
@click.option("--log-dir", default=None, type=click.Path(), help="Directory for per-story logs and status.json")
def execute(plan_file, target_repo, max_concurrent, model_escalation, pause_between, budget_per_story, log_dir):
    """Execute stories from a plan file using Claude Code agents."""
    import asyncio
    from pathlib import Path
    from execute.state import PlanState
    from execute.supervisor import Supervisor
    from execute.cost import parse_escalation
    from execute.wiggum_log import WiggumLog

    plan_path = Path(plan_file)
    repo_path = Path(target_repo)
    state_file = plan_path.parent / "plan_state.json"

    if state_file.exists():
        state = PlanState.load(state_file, plan_path)
        click.echo("Resuming from existing state.")
    else:
        state = PlanState.from_plan(plan_path)

    wlog = WiggumLog(Path(log_dir)) if log_dir else None

    sup = Supervisor(
        state=state,
        plan_path=plan_path,
        target_repo=repo_path,
        max_concurrent=max_concurrent,
        escalation=parse_escalation(model_escalation),
        pause_between=pause_between,
        budget_per_story=budget_per_story,
        wiggum_log=wlog,
    )
    asyncio.run(sup.run())


@cli.command()
@click.argument("plan_file", type=click.Path(exists=True))
@click.option("--rewrite", is_flag=True, help="Apply LLM-suggested rewrite to plan file after confirmation")
@click.option("--model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Claude model to use")
def review(plan_file, rewrite, model):
    """Evaluate a plan and suggest improvements."""
    from pathlib import Path
    from execute.state import PlanState
    from review.reviewer import build_review_prompt, extract_rewritten_plan, summarize_state, call_claude

    plan_path = Path(plan_file)
    state_file = plan_path.parent / "plan_state.json"

    state_summary = None
    if state_file.exists():
        state = PlanState.load(state_file, plan_path)
        state_summary = summarize_state(state)
        click.echo(f"Loaded execution state: {state_summary}")

    click.echo("Reviewing plan...")
    prompt = build_review_prompt(plan_path, state_summary)
    raw = call_claude(prompt, model=model)

    click.echo("\n" + raw)

    if rewrite:
        new_plan = extract_rewritten_plan(raw)
        if new_plan is None:
            click.echo("\nLLM did not suggest a rewrite.")
        else:
            click.echo("\n--- Proposed rewrite (first 500 chars) ---")
            click.echo(new_plan[:500] + ("..." if len(new_plan) > 500 else ""))
            if click.confirm("\nApply rewrite to plan file?"):
                plan_path.write_text(new_plan)
                click.echo(f"Plan updated: {plan_path}")
            else:
                click.echo("Rewrite discarded.")


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--output-dir", default=None, type=click.Path(), help="Where to write .raphael/ output (default: <repo>/.raphael/)")
@click.option("--map-model", default="sonnet", type=click.Choice(["sonnet", "opus"]), help="Model for per-module mapping")
@click.option("--reduce-escalation", default="sonnet:2,opus:1", show_default=True, help="Escalation for reduce + coherence gate")
def understand(repo_path, output_dir, map_model, reduce_escalation):
    """Build deep structural + semantic understanding of a codebase."""
    from pathlib import Path
    from execute.cost import parse_escalation
    from understand.pipeline import run_understand

    repo = Path(repo_path)
    out = Path(output_dir) if output_dir else None
    escalation = parse_escalation(reduce_escalation)

    click.echo(f"Stage 1: Building repo map...")
    click.echo(f"Stage 2: Mapping modules (model: {map_model})...")
    click.echo(f"Stage 3: Reducing to understanding (escalation: {reduce_escalation})...")

    understanding_path = run_understand(repo, output_dir=out, map_model=map_model, escalation=escalation)
    click.echo(f"\nUnderstanding written to: {understanding_path}")
    click.echo(f"Next: raphael critique {repo_path}")


if __name__ == "__main__":
    cli()
