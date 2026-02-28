from pathlib import Path
from typing import Optional

from execute.state import PlanState
from generate.prd import call_claude  # noqa: F401 — re-exported for patching in tests

_PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "review_plan.md"
_START_MARKER = "===REWRITTEN_PLAN_START==="
_END_MARKER = "===REWRITTEN_PLAN_END==="


def build_review_prompt(plan_path: Path, state_summary: Optional[str]) -> str:
    template = _PROMPT_TEMPLATE.read_text()
    plan_text = plan_path.read_text()
    state_text = state_summary if state_summary else "No execution state — plan has not been run yet."
    return template.format(plan=plan_text, state_summary=state_text)


def extract_rewritten_plan(raw: str) -> Optional[str]:
    start = raw.find(_START_MARKER)
    end = raw.find(_END_MARKER)
    if start == -1 or end == -1:
        return None
    content = raw[start + len(_START_MARKER):end]
    return content.strip() or None


def summarize_state(state: PlanState) -> str:
    counts: dict[str, int] = {}
    for s in state.stories.values():
        counts[s.status.value] = counts.get(s.status.value, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items()]
    summary = ", ".join(parts)
    total_cost = state.total_cost_usd()
    if total_cost:
        summary += f" | total cost so far: ${total_cost:.3f}"
    return summary
