import json
from pathlib import Path
from generate.prd import call_claude

_PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "understand_module.md"

EXPECTED_FIELDS = [
    "file", "purpose", "public_api", "data_flow",
    "internal_dependencies", "external_dependencies",
    "complexity_signals", "smells", "simplification_opportunities",
    "test_coverage_estimate", "lines_of_code",
]


def map_module(
    file_path: Path,
    repo_root: Path,
    repo_map: str,
    model: str = "sonnet",
) -> dict:
    """Call LLM to produce structured analysis of a single Python module."""
    rel = str(file_path.relative_to(repo_root))
    content = file_path.read_text()
    template = _PROMPT_TEMPLATE.read_text()
    prompt = template.format(filename=rel, repo_map=repo_map, content=content)

    raw = call_claude(prompt, model=model)
    try:
        result = json.loads(raw)
        result.setdefault("file", rel)
        return result
    except json.JSONDecodeError:
        return {"file": rel, "error": f"LLM returned non-JSON: {raw[:200]}"}
