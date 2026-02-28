import json
from pathlib import Path
from typing import Optional
from generate.prd import call_claude

_PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "reduce_understanding.md"


def run_reduce(
    module_summaries: list[dict],
    repo_map: str,
    model: str = "sonnet",
    retry_context: str = "",
) -> str:
    """Aggregate per-module JSON summaries into an understanding.md document."""
    summaries_text = "\n\n".join(
        f"### {s.get('file', '?')}\n{json.dumps(s, indent=2)}"
        for s in module_summaries
    )
    retry_section = f"\n## Note from previous attempt\n{retry_context}" if retry_context else ""
    template = _PROMPT_TEMPLATE.read_text()
    prompt = template.format(
        repo_map=repo_map,
        module_summaries=summaries_text,
        retry_context=retry_section,
    )
    return call_claude(prompt, model=model)
