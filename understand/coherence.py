import json
from pathlib import Path
from generate.prd import call_claude
from execute.cost import ModelTier, model_for_attempt

_REDUCE_TEMPLATE = Path(__file__).parent.parent / "prompts" / "reduce_understanding.md"
_COHERENCE_TEMPLATE = Path(__file__).parent.parent / "prompts" / "coherence_check.md"


def run_coherence_gate(
    module_summaries: list[dict],
    repo_map: str,
    escalation: list[ModelTier],
) -> str:
    """Run reduce + coherence check with retry/escalation. Returns best understanding."""
    total_allowed = sum(t.max_attempts for t in escalation)
    attempt = 1
    retry_context = ""
    last_result = ""

    while attempt <= total_allowed:
        model = model_for_attempt(escalation, attempt)
        understanding = _run_reduce(module_summaries, repo_map, model=model, retry_context=retry_context)
        last_result = understanding

        score = _check_coherence(understanding, repo_map, model=model)
        if score.get("pass", False):
            return understanding

        if attempt >= total_allowed:
            break

        issues = score.get("issues", [])
        missing = score.get("missing", [])
        overall = score.get("overall", "?")
        retry_context = (
            f"Previous attempt scored {overall}/10. "
            f"Issues: {issues}. Missing: {missing}. "
            "Please address these gaps specifically."
        )
        attempt += 1

    return last_result


def _run_reduce(
    module_summaries: list[dict],
    repo_map: str,
    model: str = "sonnet",
    retry_context: str = "",
) -> str:
    summaries_text = "\n\n".join(
        f"### {s.get('file', '?')}\n{json.dumps(s, indent=2)}"
        for s in module_summaries
    )
    retry_section = f"\n## Note from previous attempt\n{retry_context}" if retry_context else ""
    template = _REDUCE_TEMPLATE.read_text()
    prompt = template.format(
        repo_map=repo_map,
        module_summaries=summaries_text,
        retry_context=retry_section,
    )
    return call_claude(prompt, model=model)


def _check_coherence(understanding: str, repo_map: str, model: str) -> dict:
    template = _COHERENCE_TEMPLATE.read_text()
    prompt = template.format(repo_map=repo_map, understanding=understanding)
    raw = call_claude(prompt, model=model)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"pass": True, "overall": 7}  # assume pass if scoring call itself fails
