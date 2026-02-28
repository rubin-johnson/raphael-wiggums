from pathlib import Path
from generate.prd import call_claude

_CRITIQUE_PROMPT = Path(__file__).parent.parent / "prompts" / "critique_codebase.md"
_STORIES_PROMPT = Path(__file__).parent.parent / "prompts" / "prd_to_stories.md"


def run_critique(understanding: str, model: str = "sonnet") -> str:
    """Take understanding.md and produce a prioritized critique."""
    template = _CRITIQUE_PROMPT.read_text()
    prompt = template.format(understanding=understanding)
    return call_claude(prompt, model=model)


def run_critique_pipeline(
    understanding: str,
    model: str = "sonnet",
) -> tuple[str, str]:
    """Full critique → plan pipeline. Returns (critique_md, plan_md)."""
    critique = run_critique(understanding, model=model)
    stories_template = _STORIES_PROMPT.read_text()
    plan_prompt = stories_template.format(prd=critique, codebase_context="")
    plan = call_claude(plan_prompt, model=model)
    return critique, plan
